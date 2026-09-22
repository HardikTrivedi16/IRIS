import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure a clean in-memory store per test session (no Supabase env vars set).
#
# We set these to empty strings rather than deleting them. app/config.py calls
# load_dotenv() at import time, and load_dotenv(override=False) only fills in
# variables that are ABSENT from the environment. If we deleted these, a
# populated backend/.env (which exists on a real developer machine, though not
# in CI) would be reloaded here and silently switch the test session out of
# demo mode. An empty string counts as "already set", so load_dotenv leaves it
# alone, and config.py maps "" -> None (demo mode) as intended.
for var in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_JWT_SECRET"):
    os.environ[var] = ""

# By default, test sessions run in explicit demo mode
os.environ["IRIS_DEMO_MODE"] = "true"


@pytest.fixture()
def client():
    from app.main import app
    from app.config import get_settings
    from app.engine_service import get_dataset, get_engine
    from app.fact_registry import build_fact_registry
    from app.store import get_store
    import app.store.department_store as dept_store_module
    import app.security as security_module

    get_settings.cache_clear()
    get_dataset.cache_clear()
    get_engine.cache_clear()
    build_fact_registry.cache_clear()
    get_store.cache_clear()

    # Reset the department store singleton for test isolation
    dept_store_module._dept_store = None
    import app.store.grievance_store as grievance_store_module
    grievance_store_module._memory_store = None

    # Reset JWKS cache so tests don't share stale state
    security_module._jwks_cache["keys"] = None
    security_module._jwks_cache["expires_at"] = 0.0

    return TestClient(app)
