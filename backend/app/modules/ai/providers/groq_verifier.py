"""Groq Verification Provider for IRIS.

Uses the official Groq Python SDK to perform secondary fidelity verification
using openai/gpt-oss-120b. Enforces structured JSON output and strict isolation
from raw Groq SDK / network exceptions.
"""

import json
import time
from typing import Any
from pydantic import BaseModel, ValidationError

from app.modules.ai.config import AIConfig
from app.modules.ai.exceptions import (
    AIError,
    AIInvalidOutputError,
    AITimeoutError,
    AIUnavailableError,
    AIVerificationError,
)
from app.modules.ai.prompts.verification import (
    VERIFICATION_SYSTEM_PROMPT,
    build_verification_prompt,
)
from app.modules.ai.providers.verifier_base import BaseVerificationProvider
from app.modules.ai.schemas import VerificationResult


class GroqVerifier(BaseVerificationProvider):
    """Secondary verification provider using Groq API and openai/gpt-oss-120b."""

    def __init__(
        self,
        config: AIConfig | None = None,
        client: Any | None = None,
    ) -> None:
        self.config = config or AIConfig()
        self.provider_name = "groq"
        self._injected_client = client
        self._client = client

    def _get_client(self) -> Any:
        """Lazily obtain or construct the Groq client.

        Zero network requests are executed during client instantiation.
        """
        if self._client is not None:
            return self._client

        api_key = self.config.groq_api_key
        if not api_key:
            raise AIUnavailableError(
                "Groq verification is enabled but GROQ_API_KEY is not configured."
            )

        try:
            from groq import Groq
            self._client = Groq(api_key=api_key, timeout=self.config.verifier_timeout_seconds)
            return self._client
        except ImportError as imp_err:
            raise AIUnavailableError(
                f"Groq SDK is not installed: {imp_err}"
            ) from imp_err
        except Exception as init_err:
            raise AIUnavailableError(
                f"Failed to initialize Groq client: {init_err}"
            ) from init_err

    def verify(
        self,
        task_type: str,
        authoritative_input: Any,
        local_output: Any,
        output_schema: type[BaseModel] | None = None,
    ) -> VerificationResult:
        """Verify that local_output faithfully represents authoritative_input using Groq."""
        client = self._get_client()

        user_prompt = build_verification_prompt(
            task_type=task_type,
            authoritative_input=authoritative_input,
            local_output=local_output,
            output_schema=output_schema,
        )

        model_name = self.config.verifier_model or "openai/gpt-oss-120b"
        max_retries = max(0, self.config.verifier_max_retries)
        total_attempts = 1 + max_retries
        last_error: Exception | None = None

        for attempt in range(1, total_attempts + 1):
            try:
                # Bounded single inference call with structured JSON response
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": VERIFICATION_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                )

                choices = getattr(response, "choices", None)
                if not choices or len(choices) == 0:
                    raise AIInvalidOutputError("Groq returned empty completion choices.")

                raw_content = choices[0].message.content
                if not raw_content or not raw_content.strip():
                    raise AIInvalidOutputError("Groq completion content was empty.")

                # Parse and validate against VerificationResult schema
                try:
                    parsed_dict = json.loads(raw_content)
                except json.JSONDecodeError as json_err:
                    raise AIInvalidOutputError(
                        f"Groq output could not be decoded as JSON: {json_err}"
                    ) from json_err

                parsed_dict["verifier_provider"] = self.provider_name
                parsed_dict["verifier_model"] = model_name
                parsed_dict["raw_response"] = raw_content

                try:
                    return VerificationResult.model_validate(parsed_dict)
                except ValidationError as val_err:
                    raise AIInvalidOutputError(
                        f"Groq verifier output failed schema validation: {val_err}"
                    ) from val_err

            except (AIInvalidOutputError, AIVerificationError):
                raise

            except Exception as exc:
                last_error = exc
                err_type_name = type(exc).__name__

                # Check for rate limits or temporary connection errors to retry
                is_timeout = "timeout" in err_type_name.lower() or "timeout" in str(exc).lower()
                is_conn = "connection" in err_type_name.lower() or "connect" in str(exc).lower()
                is_rate_limit = "ratelimit" in err_type_name.lower() or "429" in str(exc)

                if (is_timeout or is_conn or is_rate_limit) and attempt < total_attempts:
                    time.sleep(0.5)
                    continue

                if is_timeout:
                    raise AITimeoutError(
                        f"Groq verification timed out after {self.config.verifier_timeout_seconds}s: {exc}"
                    ) from exc

                if is_conn or is_rate_limit:
                    raise AIUnavailableError(
                        f"Groq verification service unavailable ({err_type_name}): {exc}"
                    ) from exc

                # Any other Groq SDK or network exception converted to AIError
                raise AIUnavailableError(
                    f"Groq verification failed ({err_type_name}): {exc}"
                ) from exc

        if last_error:
            raise AIUnavailableError(
                f"Groq verification failed after {total_attempts} attempts: {last_error}"
            )
        raise AIUnavailableError(f"Groq verification failed after {total_attempts} attempts.")
