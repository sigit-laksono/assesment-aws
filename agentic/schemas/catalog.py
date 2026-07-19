"""
Schema Catalog — loads and manages versioned JSON Schemas.

Maps (schema_id, version) pairs to loaded JSON Schema documents.
Rejects unknown schema/version combinations with a StructuredError
listing supported versions (Req 2.5, 3.1).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from agentic.models import SemVer, StructuredError


# Base directory where schemas are stored
_SCHEMAS_DIR = Path(__file__).parent


class SchemaCatalog:
    """
    Loads checked-in JSON Schema documents and provides lookup by
    (schema_id, version). Thread-safe after construction.
    """

    def __init__(self) -> None:
        # registry: schema_id -> {version_str -> schema_dict}
        self._registry: dict[str, dict[str, dict[str, Any]]] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Discover and load all schema files under the schemas directory."""
        for schema_dir in _SCHEMAS_DIR.iterdir():
            if not schema_dir.is_dir() or schema_dir.name.startswith("_"):
                continue
            schema_id = schema_dir.name
            versions: dict[str, dict[str, Any]] = {}
            for version_file in schema_dir.glob("*.json"):
                version_str = version_file.stem  # e.g. "1.0.0"
                try:
                    SemVer.parse(version_str)
                except ValueError:
                    continue
                with open(version_file, "r", encoding="utf-8") as f:
                    versions[version_str] = json.load(f)
            if versions:
                self._registry[schema_id] = versions

    def get_schema(
        self, schema_id: str, version: str
    ) -> dict[str, Any]:
        """
        Retrieve the JSON Schema for a given schema_id and version.

        Raises ValueError with a StructuredError-compatible message
        if the schema_id or version is unknown.
        """
        versions = self._registry.get(schema_id)
        if versions is None:
            supported_schemas = sorted(self._registry.keys())
            raise ValueError(
                f"Unknown schema_id '{schema_id}'. "
                f"Supported schemas: {supported_schemas}"
            )

        schema = versions.get(version)
        if schema is None:
            supported_versions = sorted(versions.keys())
            raise ValueError(
                f"Unknown version '{version}' for schema '{schema_id}'. "
                f"Supported versions: {supported_versions}"
            )
        return schema

    def supported_schemas(self) -> Mapping[str, tuple[str, ...]]:
        """Return all supported schema IDs with their available versions."""
        return {
            schema_id: tuple(sorted(versions.keys()))
            for schema_id, versions in sorted(self._registry.items())
        }

    def has_schema(self, schema_id: str, version: str) -> bool:
        """Check if a schema_id/version combination is registered."""
        versions = self._registry.get(schema_id)
        if versions is None:
            return False
        return version in versions

    def get_supported_versions(self, schema_id: str) -> tuple[str, ...]:
        """Return supported versions for a schema_id, or empty tuple."""
        versions = self._registry.get(schema_id)
        if versions is None:
            return ()
        return tuple(sorted(versions.keys()))

    def check_major_compatibility(
        self, schema_id: str, old_version: str, new_version: str
    ) -> bool:
        """
        Check if two versions are major-compatible.
        Returns True if they share the same major version.
        """
        old = SemVer.parse(old_version)
        new = SemVer.parse(new_version)
        return old.major == new.major

    def make_unsupported_error(
        self, schema_id: str, version: str
    ) -> StructuredError:
        """
        Create a StructuredError for an unsupported schema/version,
        including supported versions in the message (Req 2.5).
        """
        supported = self.get_supported_versions(schema_id)
        if not supported:
            safe_message = (
                f"Unknown schema '{schema_id}'. "
                f"Supported schemas: {sorted(self._registry.keys())}"
            )
        else:
            safe_message = (
                f"Unsupported version '{version}' for schema '{schema_id}'. "
                f"Supported versions: {list(supported)}"
            )
        return StructuredError(
            schema_id="structured-error",
            schema_version="1.0.0",
            code="UNSUPPORTED_SCHEMA_VERSION",
            category="unsupported",
            retryable=False,
            safe_message=safe_message,
        )
