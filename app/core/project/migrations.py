from __future__ import annotations

from copy import deepcopy
from typing import Callable, Mapping, Any

CURRENT_PROJECT_SCHEMA_VERSION = 2


def _v1_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(payload)
    migrated.setdefault("settings", {})
    migrated["schema_version"] = 2
    return migrated


_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    1: _v1_to_v2,
}


def migrate_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(dict(payload))
    raw_version = migrated.get("schema_version", 1)
    if not isinstance(raw_version, int):
        raise ValueError("project schema_version must be an integer")
    if raw_version > CURRENT_PROJECT_SCHEMA_VERSION:
        raise ValueError(
            f"future project schema {raw_version} is not supported by this build "
            f"(current {CURRENT_PROJECT_SCHEMA_VERSION})"
        )
    if raw_version < 1:
        raise ValueError(f"unsupported project schema version: {raw_version}")
    version = raw_version
    while version < CURRENT_PROJECT_SCHEMA_VERSION:
        migration = _MIGRATIONS.get(version)
        if migration is None:
            raise ValueError(f"missing migration from project schema {version}")
        migrated = migration(migrated)
        next_version = migrated.get("schema_version")
        if not isinstance(next_version, int) or next_version <= version:
            raise ValueError(f"migration from project schema {version} did not advance the version")
        version = next_version
    return migrated
