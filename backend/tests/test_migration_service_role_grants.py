"""Regression: the backend's service_role must be able to use user_profiles.

0003 granted user_profiles to `authenticated` only, so on a fresh Supabase
project the backend's service-role PostgREST calls returned 403. The fix is a
forward migration (0003 is already applied and must not be edited).
"""
from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"


def _grants(table: str, role: str) -> set[str]:
    privileges: set[str] = set()
    for path in sorted(MIGRATIONS.glob("*.sql")):
        sql = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8")).lower()
        for m in re.finditer(r"\bgrant\s+([a-z ,]+?)\s+on\s+(?:table\s+)?([\w.]+)\s+to\s+([^;]+);", sql):
            privs, target, roles = m.groups()
            if target.split(".")[-1] == table and role in [r.strip() for r in roles.split(",")]:
                privileges |= {p.strip() for p in privs.split(",")}
    return privileges


def test_service_role_can_read_create_and_update_profiles():
    assert {"select", "insert", "update"} <= _grants("user_profiles", "service_role")


def test_service_role_is_not_given_delete_on_profiles():
    assert "delete" not in _grants("user_profiles", "service_role")


def test_historical_0003_is_unmodified_in_intent():
    text = (MIGRATIONS / "0003_auth_sla_bottlenecks.sql").read_text(encoding="utf-8")
    assert "GRANT SELECT, INSERT, UPDATE ON public.user_profiles TO authenticated;" in text
    assert "user_profiles TO service_role" not in text
