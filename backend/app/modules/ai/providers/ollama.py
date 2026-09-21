"""Ollama AI Provider for IRIS.

Communicates with local Ollama daemon via HTTP REST endpoints (/api/chat, /api/embed, /api/version).
Implements bounded retries, typed JSON schema enforcement via Pydantic v2, and complete
isolation from raw requests exceptions.
"""

import time
import math
from typing import Any, TypeVar
import requests
from pydantic import BaseModel, ValidationError

from app.modules.ai.config import AIConfig
from app.modules.ai.exceptions import (
    AIError,
    AIInvalidOutputError,
    AITimeoutError,
    AIUnavailableError,
)
from app.modules.ai.providers.base import BaseAIProvider

T = TypeVar("T", bound=BaseModel)

RETRYABLE_STATUS_CODES = {500, 502, 503, 504}


class OllamaProvider(BaseAIProvider):
    """Local Ollama provider implementation."""

    def __init__(
        self,
        config: AIConfig | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config or AIConfig()
        self._base_url = self.config.ollama_url.rstrip("/")
        self._session = session or requests.Session()

    def _post_with_retry(
        self,
        endpoint: str,
        payload: dict[str, Any],
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Execute a POST request with bounded retries and exception mapping.

        Total attempts = 1 (initial request) + self.config.max_retries.
        Raw requests exceptions must never escape this boundary.
        """
        url = f"{self._base_url}{endpoint}"
        effective_timeout = timeout or self.config.timeout_seconds
        max_retries = max(0, self.config.max_retries)
        total_attempts = 1 + max_retries

        last_error: Exception | None = None

        for attempt in range(1, total_attempts + 1):
            try:
                response = self._session.post(
                    url,
                    json=payload,
                    timeout=effective_timeout,
                )

                if response.status_code == 200:
                    try:
                        return response.json()
                    except Exception as json_err:
                        raise AIInvalidOutputError(
                            f"Ollama returned unparseable JSON response: {json_err}"
                        ) from json_err

                # Non-200 responses
                if response.status_code in RETRYABLE_STATUS_CODES and attempt < total_attempts:
                    time.sleep(0.25)
                    continue

                if response.status_code == 404:
                    raise AIUnavailableError(
                        f"Ollama endpoint or model not found (HTTP 404): {response.text}"
                    )

                raise AIUnavailableError(
                    f"Ollama server returned error status {response.status_code}: {response.text}"
                )

            except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout, requests.exceptions.Timeout) as timeout_err:
                last_error = timeout_err
                if attempt < total_attempts:
                    time.sleep(0.25)
                    continue
                raise AITimeoutError(
                    f"Ollama request to {endpoint} timed out after {effective_timeout}s: {timeout_err}"
                ) from timeout_err

            except requests.exceptions.ConnectionError as conn_err:
                last_error = conn_err
                if attempt < total_attempts:
                    time.sleep(0.25)
                    continue
                raise AIUnavailableError(
                    f"Unable to connect to Ollama at {self._base_url}: {conn_err}"
                ) from conn_err

            except (AIError, AIInvalidOutputError, AIUnavailableError, AITimeoutError):
                raise

            except Exception as other_err:
                raise AIError(f"Unexpected error communicating with Ollama: {other_err}") from other_err

        if last_error:
            raise AIUnavailableError(f"Ollama request failed after {total_attempts} attempts: {last_error}")
        raise AIUnavailableError(f"Ollama request failed after {total_attempts} attempts.")

    def generate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool | None = None,
    ) -> str:
        """Generate unstructured text from prompt."""
        options: dict[str, Any] = {
            "temperature": temperature if temperature is not None else 0.0,
        }
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        payload: dict[str, Any] = {
            "model": self.config.generation_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": options,
            "think": think if think is not None else False,
        }

        data = self._post_with_retry("/api/chat", payload)
        message = data.get("message")
        if not isinstance(message, dict) or "content" not in message:
            raise AIInvalidOutputError("Ollama chat response did not contain expected message.content")

        content = message["content"]
        if not isinstance(content, str):
            raise AIInvalidOutputError(f"Expected message content to be str, got {type(content).__name__}")

        return content

    def generate_structured(
        self,
        prompt: str,
        schema: type[T],
        temperature: float | None = None,
        max_tokens: int | None = None,
        think: bool | None = None,
    ) -> T:
        """Generate structured JSON adhering to the Pydantic model and return validated instance."""
        options: dict[str, Any] = {
            "temperature": temperature if temperature is not None else 0.0,
        }
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        payload: dict[str, Any] = {
            "model": self.config.generation_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": schema.model_json_schema(),
            "options": options,
            "think": think if think is not None else False,
        }

        data = self._post_with_retry("/api/chat", payload)
        message = data.get("message")
        if not isinstance(message, dict) or "content" not in message:
            raise AIInvalidOutputError("Ollama structured response missing message.content")

        raw_content = message["content"]
        if not isinstance(raw_content, str) or not raw_content.strip():
            raise AIInvalidOutputError("Ollama structured response content was empty or not a string")

        try:
            return schema.model_validate_json(raw_content)
        except (ValidationError, ValueError) as val_err:
            raise AIInvalidOutputError(
                f"Ollama output failed validation against schema {schema.__name__}: {val_err}"
            ) from val_err

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for input texts."""
        if not texts:
            return []

        payload = {
            "model": self.config.embedding_model,
            "input": texts,
        }

        data = self._post_with_retry("/api/embed", payload)
        embeddings = data.get("embeddings")

        if not isinstance(embeddings, list):
            raise AIInvalidOutputError(
                f"Ollama embed endpoint returned invalid format, expected list: {type(embeddings).__name__}"
            )

        if len(embeddings) != len(texts):
            raise AIInvalidOutputError(
                f"Embedding count mismatch: input had {len(texts)} strings, Ollama returned {len(embeddings)}"
            )

        expected_dim: int | None = None
        for row_idx, vector in enumerate(embeddings):
            if not isinstance(vector, list) or not vector:
                raise AIInvalidOutputError(f"Embedding {row_idx} must be a non-empty list.")
            if expected_dim is None:
                expected_dim = len(vector)
            elif len(vector) != expected_dim:
                raise AIInvalidOutputError(
                    f"Embedding dimension mismatch inside Ollama response: expected {expected_dim}, got {len(vector)} at row {row_idx}."
                )
            for col_idx, value in enumerate(vector):
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise AIInvalidOutputError(
                        f"Embedding value [{row_idx}][{col_idx}] is not numeric: {value!r}."
                    )
                if not math.isfinite(float(value)):
                    raise AIInvalidOutputError(
                        f"Embedding value [{row_idx}][{col_idx}] is not finite: {value!r}."
                    )

        return [[float(v) for v in vector] for vector in embeddings]

    def health_check(self) -> bool:
        """Lightweight check to determine whether Ollama daemon is reachable."""
        try:
            url = f"{self._base_url}/api/version"
            res = self._session.get(url, timeout=2.0)
            return res.status_code == 200
        except Exception:
            return False
