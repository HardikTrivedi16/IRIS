"""
Tests for Fail-Closed Security and Persistence Behavior.

Verifies:
  1. In production (IRIS_DEMO_MODE=false) without Supabase Auth configured,
     any protected endpoint fails closed with HTTP 500 (misconfiguration alert),
     NEVER silently falling back to a demo user.
  2. In production (IRIS_DEMO_MODE=false) with auth configured, missing or
     invalid Bearer tokens fail closed with HTTP 401.
  3. In production (IRIS_DEMO_MODE=false) without Supabase configured,
     get_department_store() fails closed with StoreError, NEVER silently
     falling back to the volatile in-memory store.
  4. In explicit demo mode (IRIS_DEMO_MODE=true), requests succeed as demo user.
"""
import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.store.department_store import get_department_store
from app.store.base import StoreError


def test_production_fails_closed_when_auth_unconfigured(monkeypatch):
    """
    If IRIS_DEMO_MODE=false and Supabase is not configured, protected endpoints
    must fail closed with 500 (misconfiguration), NOT return demo user.
    """
    monkeypatch.setenv("IRIS_DEMO_MODE", "false")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    get_settings.cache_clear()

    client = TestClient(app, raise_server_exceptions=False)
    try:
        # Government endpoint requires auth
        r = client.get("/api/v1/department/applications")
        assert r.status_code == 500
        detail = r.json().get("detail", "").lower()
        assert "misconfigured" in detail or "unavailable" in detail
    finally:
        get_settings.cache_clear()


def test_production_fails_closed_missing_token_when_auth_configured(monkeypatch):
    """
    If IRIS_DEMO_MODE=false and Supabase is configured, request without token
    must fail closed with 401.
    """
    monkeypatch.setenv("IRIS_DEMO_MODE", "false")
    monkeypatch.setenv("SUPABASE_URL", "https://mockproject.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "mock-service-role-key")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "super-secret-jwt-key-for-tests-32-chars-long")
    get_settings.cache_clear()

    client = TestClient(app, raise_server_exceptions=False)
    try:
        r = client.get("/api/v1/department/applications")
        assert r.status_code == 401
        assert "missing" in r.json().get("detail", "").lower()
    finally:
        get_settings.cache_clear()


def test_production_fails_closed_invalid_token(monkeypatch):
    """
    If IRIS_DEMO_MODE=false and Supabase is configured, invalid Bearer token
    must fail closed with 401.
    """
    monkeypatch.setenv("IRIS_DEMO_MODE", "false")
    monkeypatch.setenv("SUPABASE_URL", "https://mockproject.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "mock-service-role-key")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "super-secret-jwt-key-for-tests-32-chars-long")
    get_settings.cache_clear()

    client = TestClient(app, raise_server_exceptions=False)
    try:
        r = client.get(
            "/api/v1/department/applications",
            headers={"Authorization": "Bearer not-a-valid-jwt-token"},
        )
        assert r.status_code == 401
        assert "invalid" in r.json().get("detail", "").lower()
    finally:
        get_settings.cache_clear()


def test_production_department_store_fails_closed_when_supabase_unconfigured(monkeypatch):
    """
    In production (IRIS_DEMO_MODE=false), get_department_store() must raise
    StoreError if Supabase is unconfigured, preventing silent RAM data loss.
    """
    monkeypatch.setenv("IRIS_DEMO_MODE", "false")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    get_settings.cache_clear()

    try:
        with pytest.raises(StoreError, match="cannot initialize in production without persistence"):
            get_department_store()
    finally:
        get_settings.cache_clear()


def test_demo_mode_allows_access_with_warning(monkeypatch):
    """
    When explicit IRIS_DEMO_MODE=true, access is permitted and demo user returned.
    """
    monkeypatch.setenv("IRIS_DEMO_MODE", "true")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    get_settings.cache_clear()

    client = TestClient(app)
    try:
        r = client.get("/api/v1/department/applications")
        assert r.status_code == 200
    finally:
        get_settings.cache_clear()
