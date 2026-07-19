"""
Tests for Schema Catalog and Canonical JSON Processor.

Validates Requirements: 2.1, 2.2, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 11.4
"""

from __future__ import annotations

import json
import math
from decimal import Decimal

import pytest

from agentic.models import SemVer
from agentic.schemas.catalog import SchemaCatalog
from agentic.schemas.processor import CanonicalSchemaProcessor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def catalog() -> SchemaCatalog:
    return SchemaCatalog()


@pytest.fixture
def processor() -> CanonicalSchemaProcessor:
    return CanonicalSchemaProcessor()


# ---------------------------------------------------------------------------
# Schema Catalog Tests (Req 3.1)
# ---------------------------------------------------------------------------


class TestSchemaCatalog:
    """Tests for the Schema Catalog loading and lookup."""

    def test_catalog_loads_all_expected_schemas(self, catalog: SchemaCatalog) -> None:
        """Req 3.1: Schema Catalog provides Semantic Version identifiers."""
        supported = catalog.supported_schemas()
        expected_schemas = [
            "invocation-request",
            "invocation-result",
            "structured-error",
            "evidence",
            "capability-manifest",
            "assessment-profile",
            "completeness-report",
            "drift-report",
        ]
        for schema_id in expected_schemas:
            assert schema_id in supported, f"Missing schema: {schema_id}"
            assert "1.0.0" in supported[schema_id]

    def test_get_schema_returns_valid_json_schema(self, catalog: SchemaCatalog) -> None:
        """Verify loaded schema is a valid JSON Schema document."""
        schema = catalog.get_schema("invocation-request", "1.0.0")
        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema

    def test_get_schema_unknown_id_raises(self, catalog: SchemaCatalog) -> None:
        """Req 2.5: Unsupported schema returns supported versions."""
        with pytest.raises(ValueError, match="Unknown schema_id"):
            catalog.get_schema("nonexistent-schema", "1.0.0")

    def test_get_schema_unknown_version_raises(self, catalog: SchemaCatalog) -> None:
        """Req 2.5: Unknown version lists supported versions."""
        with pytest.raises(ValueError, match="Supported versions"):
            catalog.get_schema("invocation-request", "99.0.0")

    def test_has_schema_positive(self, catalog: SchemaCatalog) -> None:
        assert catalog.has_schema("evidence", "1.0.0") is True

    def test_has_schema_negative(self, catalog: SchemaCatalog) -> None:
        assert catalog.has_schema("evidence", "99.0.0") is False

    def test_make_unsupported_error_includes_versions(
        self, catalog: SchemaCatalog
    ) -> None:
        """Req 2.5: StructuredError includes supported versions."""
        error = catalog.make_unsupported_error("invocation-request", "99.0.0")
        assert error.category == "unsupported"
        assert error.code == "UNSUPPORTED_SCHEMA_VERSION"
        assert "1.0.0" in error.safe_message

    def test_major_compatibility_same_major(self, catalog: SchemaCatalog) -> None:
        """Req 3.6: Same major version is compatible."""
        assert catalog.check_major_compatibility("evidence", "1.0.0", "1.1.0") is True

    def test_major_compatibility_different_major(self, catalog: SchemaCatalog) -> None:
        """Req 3.6: Different major version is incompatible."""
        assert catalog.check_major_compatibility("evidence", "1.0.0", "2.0.0") is False


# ---------------------------------------------------------------------------
# Validation Tests (Req 3.2, 3.3)
# ---------------------------------------------------------------------------


class TestValidation:
    """Tests for payload validation against schema."""

    def test_valid_structured_error_passes(self, processor: CanonicalSchemaProcessor) -> None:
        """Req 3.2: Valid payload passes validation."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "VALIDATION_FAILED",
            "category": "validation",
            "retryable": False,
            "safe_message": "Request is invalid",
        }
        result = processor.validate("structured-error", "1.0.0", payload)
        assert result.is_valid

    def test_invalid_payload_accumulates_all_violations(
        self, processor: CanonicalSchemaProcessor
    ) -> None:
        """Req 3.3: Return EVERY detected violation."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "invalid-version",
            "code": "",  # minLength 1 violated
            "category": "unknown-category",  # enum violated
            "retryable": "not-bool",  # type violated
            "safe_message": "ok",
        }
        result = processor.validate("structured-error", "1.0.0", payload)
        assert not result.is_valid
        # Should have multiple violations (pattern, minLength, enum, type)
        assert len(result.violations) >= 3

    def test_violation_contains_json_path_and_constraint(
        self, processor: CanonicalSchemaProcessor
    ) -> None:
        """Req 3.3: Each violation has json_path, constraint, safe_message."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST",
            "category": "INVALID",  # not in enum
            "retryable": False,
            "safe_message": "test",
        }
        result = processor.validate("structured-error", "1.0.0", payload)
        assert not result.is_valid
        violation = result.violations[0]
        assert violation.json_path
        assert violation.constraint
        assert violation.safe_message

    def test_unknown_schema_version_returns_violation(
        self, processor: CanonicalSchemaProcessor
    ) -> None:
        """Req 2.5: Unknown version returns violation."""
        result = processor.validate("invocation-request", "99.0.0", {})
        assert not result.is_valid
        assert any("schema_resolution" in v.constraint for v in result.violations)

    def test_nan_value_rejected(self, processor: CanonicalSchemaProcessor) -> None:
        """NaN values are rejected during validation."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST",
            "category": "internal",
            "retryable": False,
            "safe_message": "test",
            "some_field": float("nan"),
        }
        result = processor.validate("structured-error", "1.0.0", payload)
        assert not result.is_valid
        assert any("nan" in v.constraint for v in result.violations)

    def test_infinity_value_rejected(self, processor: CanonicalSchemaProcessor) -> None:
        """Infinity values are rejected during validation."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST",
            "category": "internal",
            "retryable": False,
            "safe_message": "test",
            "some_field": float("inf"),
        }
        result = processor.validate("structured-error", "1.0.0", payload)
        assert not result.is_valid
        assert any("infinity" in v.constraint for v in result.violations)


# ---------------------------------------------------------------------------
# Credential Rejection Tests (Req 11.4)
# ---------------------------------------------------------------------------


class TestCredentialRejection:
    """Tests for raw credential field rejection."""

    def test_access_key_rejected(self, processor: CanonicalSchemaProcessor) -> None:
        """Req 11.4: Raw access_key is rejected."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST",
            "category": "internal",
            "retryable": False,
            "safe_message": "test",
            "access_key": "AKIAIOSFODNN7EXAMPLE",
        }
        result = processor.validate("structured-error", "1.0.0", payload)
        assert not result.is_valid
        assert any("credential" in v.constraint for v in result.violations)

    def test_secret_key_rejected(self, processor: CanonicalSchemaProcessor) -> None:
        """Req 11.4: Raw secret_key is rejected."""
        payload = {
            "schema_id": "invocation-request",
            "schema_version": "1.0.0",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        }
        result = processor.validate("invocation-request", "1.0.0", payload)
        assert not result.is_valid
        assert any("credential" in v.constraint for v in result.violations)

    def test_password_rejected(self, processor: CanonicalSchemaProcessor) -> None:
        """Req 11.4: Raw password is rejected."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST",
            "category": "internal",
            "retryable": False,
            "safe_message": "test",
            "password": "my-secret-password",
        }
        result = processor.validate("structured-error", "1.0.0", payload)
        assert not result.is_valid
        assert any("credential" in v.constraint for v in result.violations)

    def test_null_credential_not_rejected(
        self, processor: CanonicalSchemaProcessor
    ) -> None:
        """Null credential references are acceptable (Req 11.4)."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST",
            "category": "internal",
            "retryable": False,
            "safe_message": "test",
            "access_key": None,
        }
        result = processor.validate("structured-error", "1.0.0", payload)
        # Credential check should NOT fire for null values
        assert not any("credential" in v.constraint for v in result.violations)

    def test_nested_credential_rejected(
        self, processor: CanonicalSchemaProcessor
    ) -> None:
        """Req 11.4: Nested credential fields are also rejected."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST",
            "category": "internal",
            "retryable": False,
            "safe_message": "test",
            "nested": {"session_token": "FwoGZXIvYXdzEBY..."},
        }
        result = processor.validate("structured-error", "1.0.0", payload)
        assert not result.is_valid
        assert any("credential" in v.constraint for v in result.violations)


# ---------------------------------------------------------------------------
# Canonical Bytes Tests (Req 3.4)
# ---------------------------------------------------------------------------


class TestCanonicalBytes:
    """Tests for canonical JSON serialization."""

    def test_sorted_keys(self, processor: CanonicalSchemaProcessor) -> None:
        """Req 3.4: Sorted object keys."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST",
            "category": "internal",
            "retryable": False,
            "safe_message": "test",
        }
        canonical = processor.canonical_bytes("structured-error", "1.0.0", payload)
        parsed = json.loads(canonical)
        keys = list(parsed.keys())
        assert keys == sorted(keys)

    def test_compact_separators(self, processor: CanonicalSchemaProcessor) -> None:
        """Req 3.4: Compact separators (no spaces)."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST",
            "category": "internal",
            "retryable": False,
            "safe_message": "test",
        }
        canonical = processor.canonical_bytes("structured-error", "1.0.0", payload)
        text = canonical.decode("utf-8")
        # Should not have ": " or ", " (compact separators)
        assert '" :' not in text
        assert '": ' not in text or '":' in text

    def test_no_trailing_newline(self, processor: CanonicalSchemaProcessor) -> None:
        """Req 3.4: No trailing newline."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST",
            "category": "internal",
            "retryable": False,
            "safe_message": "test",
        }
        canonical = processor.canonical_bytes("structured-error", "1.0.0", payload)
        assert not canonical.endswith(b"\n")

    def test_nan_raises_on_serialize(self, processor: CanonicalSchemaProcessor) -> None:
        """NaN rejected during serialization."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST",
            "category": "internal",
            "retryable": False,
            "safe_message": "test",
            "value": float("nan"),
        }
        with pytest.raises(ValueError, match="NaN"):
            processor.canonical_bytes("structured-error", "1.0.0", payload)

    def test_infinity_raises_on_serialize(
        self, processor: CanonicalSchemaProcessor
    ) -> None:
        """Infinity rejected during serialization."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST",
            "category": "internal",
            "retryable": False,
            "safe_message": "test",
            "value": float("inf"),
        }
        with pytest.raises(ValueError, match="NaN|Infinity"):
            processor.canonical_bytes("structured-error", "1.0.0", payload)

    def test_credential_field_raises_on_serialize(
        self, processor: CanonicalSchemaProcessor
    ) -> None:
        """Req 11.4: Credential fields raise during serialization."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST",
            "category": "internal",
            "retryable": False,
            "safe_message": "test",
            "password": "secret123",
        }
        with pytest.raises(ValueError, match="credential"):
            processor.canonical_bytes("structured-error", "1.0.0", payload)

    def test_timestamp_normalization(
        self, processor: CanonicalSchemaProcessor
    ) -> None:
        """Req 3.4: UTC timestamps normalized."""
        payload = {
            "schema_id": "drift-report",
            "schema_version": "1.0.0",
            "left_run_id": "run-1",
            "right_run_id": "run-2",
            "target_overlap": [],
            "compared_at": "2024-01-15T10:30:00+00:00",
        }
        canonical = processor.canonical_bytes("drift-report", "1.0.0", payload)
        text = canonical.decode("utf-8")
        # Should be normalized to Z suffix
        assert "2024-01-15T10:30:00Z" in text

    def test_decimal_normalization(
        self, processor: CanonicalSchemaProcessor
    ) -> None:
        """Req 3.4: Decimal strings normalized."""
        payload = {
            "schema_id": "completeness-report",
            "schema_version": "1.0.0",
            "items": [],
            "total_applicable": 10,
            "total_completed": 8,
            "ratio": Decimal("0.80000"),
        }
        canonical = processor.canonical_bytes(
            "completeness-report", "1.0.0", payload
        )
        text = canonical.decode("utf-8")
        # Decimal should be normalized (trailing zeros removed)
        assert '"0.8"' in text or '"ratio":"0.8"' in text


# ---------------------------------------------------------------------------
# Parse and Round-Trip Tests (Req 3.5)
# ---------------------------------------------------------------------------


class TestParseAndRoundTrip:
    """Tests for parsing and round-trip byte equivalence."""

    def test_parse_returns_mapping(self, processor: CanonicalSchemaProcessor) -> None:
        """Parse returns a valid mapping."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST",
            "category": "internal",
            "retryable": False,
            "safe_message": "test",
        }
        canonical = processor.canonical_bytes("structured-error", "1.0.0", payload)
        parsed = processor.parse("structured-error", "1.0.0", canonical)
        assert isinstance(parsed, dict)
        assert parsed["schema_id"] == "structured-error"
        assert parsed["code"] == "TEST"

    def test_round_trip_byte_equivalence(
        self, processor: CanonicalSchemaProcessor
    ) -> None:
        """Req 3.5: parse(canonical_bytes(x)) -> re-serialize produces same bytes."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST_ROUNDTRIP",
            "category": "validation",
            "retryable": True,
            "safe_message": "round trip test",
            "violations": [
                {
                    "json_path": "$.field",
                    "constraint": "required",
                    "safe_message": "missing",
                }
            ],
        }
        # First serialization
        first_bytes = processor.canonical_bytes("structured-error", "1.0.0", payload)
        # Parse back
        parsed = processor.parse("structured-error", "1.0.0", first_bytes)
        # Second serialization
        second_bytes = processor.canonical_bytes("structured-error", "1.0.0", parsed)
        # Must be byte-equivalent
        assert first_bytes == second_bytes

    def test_parse_unknown_schema_raises(
        self, processor: CanonicalSchemaProcessor
    ) -> None:
        """Parse rejects unknown schema."""
        with pytest.raises(ValueError):
            processor.parse("nonexistent", "1.0.0", b'{"key": "value"}')


# ---------------------------------------------------------------------------
# SHA-256 Digest Tests
# ---------------------------------------------------------------------------


class TestDigest:
    """Tests for SHA-256 digest computation."""

    def test_digest_is_hex_string(self, processor: CanonicalSchemaProcessor) -> None:
        """Digest returns a hex string."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST",
            "category": "internal",
            "retryable": False,
            "safe_message": "test",
        }
        digest = processor.digest("structured-error", "1.0.0", payload)
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_digest_deterministic(self, processor: CanonicalSchemaProcessor) -> None:
        """Same payload always produces same digest."""
        payload = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST",
            "category": "internal",
            "retryable": False,
            "safe_message": "test",
        }
        d1 = processor.digest("structured-error", "1.0.0", payload)
        d2 = processor.digest("structured-error", "1.0.0", payload)
        assert d1 == d2

    def test_digest_changes_with_content(
        self, processor: CanonicalSchemaProcessor
    ) -> None:
        """Different payloads produce different digests."""
        payload1 = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST1",
            "category": "internal",
            "retryable": False,
            "safe_message": "first",
        }
        payload2 = {
            "schema_id": "structured-error",
            "schema_version": "1.0.0",
            "code": "TEST2",
            "category": "internal",
            "retryable": False,
            "safe_message": "second",
        }
        d1 = processor.digest("structured-error", "1.0.0", payload1)
        d2 = processor.digest("structured-error", "1.0.0", payload2)
        assert d1 != d2


# ---------------------------------------------------------------------------
# Version Compatibility Tests (Req 3.6)
# ---------------------------------------------------------------------------


class TestVersionCompatibility:
    """Tests for version compatibility checking."""

    def test_same_major_is_compatible(
        self, processor: CanonicalSchemaProcessor
    ) -> None:
        """Req 3.6: Same major version is compatible."""
        assert (
            processor.check_version_compatibility("evidence", "1.0.0", "1.2.3")
            is True
        )

    def test_different_major_is_incompatible(
        self, processor: CanonicalSchemaProcessor
    ) -> None:
        """Req 3.6: Different major version is incompatible."""
        assert (
            processor.check_version_compatibility("evidence", "1.0.0", "2.0.0")
            is False
        )
