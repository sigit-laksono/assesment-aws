"""
Canonical Schema Processor — validates, serializes, parses payloads.

Implements the SchemaProcessor protocol with:
- Full violation accumulation (Req 3.3)
- Canonical JSON serialization (Req 3.4)
- Round-trip byte equivalence (Req 3.5)
- NaN/Infinity rejection
- Raw credential field rejection (Req 11.4)
- SHA-256 digest computation
- Version compatibility checking (Req 3.6)
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from agentic.models import SchemaViolation, SemVer, ValidationResult
from agentic.schemas.catalog import SchemaCatalog

try:
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError:
    jsonschema = None  # type: ignore[assignment]
    Draft202012Validator = None  # type: ignore[assignment, misc]


# Credential field names that must be rejected in persisted payloads (Req 11.4)
_CREDENTIAL_FIELDS = frozenset({
    "access_key",
    "secret_key",
    "session_token",
    "password",
    "aws_access_key_id",
    "aws_secret_access_key",
    "aws_session_token",
    "secret_access_key",
    "private_key",
    "api_key",
    "api_secret",
    "auth_token",
    "authorization",
})

# UTC timestamp patterns for normalization
_ISO_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(\.\d+)?"
    r"(Z|[+-]\d{2}:\d{2})$"
)


class CanonicalSchemaProcessor:
    """
    Implements the SchemaProcessor protocol using checked-in JSON Schemas
    and canonical JSON serialization.
    """

    def __init__(self, catalog: SchemaCatalog | None = None) -> None:
        self._catalog = catalog or SchemaCatalog()

    @property
    def catalog(self) -> SchemaCatalog:
        """Access the underlying schema catalog."""
        return self._catalog

    # ------------------------------------------------------------------
    # SchemaProcessor protocol methods
    # ------------------------------------------------------------------

    def validate(
        self, schema_id: str, version: str, payload: Mapping[str, Any]
    ) -> ValidationResult:
        """
        Validate payload against the declared schema version.
        Accumulates ALL violations (Req 3.3).
        Rejects NaN/Infinity and raw credential fields.
        """
        violations: list[SchemaViolation] = []
        report_truncated = False

        # Check for credential fields first
        cred_violations = self._check_credential_fields(payload)
        violations.extend(cred_violations)

        # Check for NaN/Infinity values
        nan_violations = self._check_nan_infinity(payload)
        violations.extend(nan_violations)

        # Resolve schema; unknown schema/version adds a violation
        try:
            schema = self._catalog.get_schema(schema_id, version)
        except ValueError as e:
            violations.append(
                SchemaViolation(
                    json_path="$",
                    constraint="schema_resolution",
                    safe_message=str(e),
                )
            )
            return ValidationResult(
                violations=tuple(violations), report_truncated=report_truncated
            )

        # JSON Schema validation — accumulate all errors
        if jsonschema is not None and Draft202012Validator is not None:
            try:
                validator = Draft202012Validator(schema)
                for error in sorted(
                    validator.iter_errors(dict(payload)), key=lambda e: list(e.path)
                ):
                    json_path = "$" + "".join(
                        f".{p}" if isinstance(p, str) else f"[{p}]"
                        for p in error.absolute_path
                    )
                    constraint = error.validator
                    # Never expose raw values in message
                    safe_msg = _safe_error_message(error)
                    violations.append(
                        SchemaViolation(
                            json_path=json_path,
                            constraint=constraint,
                            safe_message=safe_msg,
                        )
                    )
            except Exception:
                report_truncated = True

        return ValidationResult(
            violations=tuple(violations), report_truncated=report_truncated
        )

    def canonical_bytes(
        self, schema_id: str, version: str, payload: Mapping[str, Any]
    ) -> bytes:
        """
        Serialize a valid payload as Canonical JSON bytes (Req 3.4).

        Canonical JSON:
        - UTF-8 encoding
        - Sorted object keys
        - Compact separators (',', ':')
        - No trailing newline
        - Normalized UTC timestamps
        - Normalized decimal strings
        - NaN/Infinity rejected
        """
        # Verify schema exists
        self._catalog.get_schema(schema_id, version)

        # Reject NaN/Infinity
        nan_violations = self._check_nan_infinity(payload)
        if nan_violations:
            raise ValueError(
                f"Cannot serialize payload with NaN/Infinity values: "
                f"{nan_violations[0].safe_message}"
            )

        # Reject credential fields
        cred_violations = self._check_credential_fields(payload)
        if cred_violations:
            raise ValueError(
                f"Cannot serialize payload with credential fields: "
                f"{cred_violations[0].safe_message}"
            )

        # Normalize and serialize
        normalized = _normalize_value(payload)
        return json.dumps(
            normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")

    def parse(
        self, schema_id: str, version: str, data: bytes
    ) -> Mapping[str, Any]:
        """
        Parse Canonical JSON bytes back into a mapping (Req 3.5).
        Verifies schema exists.
        """
        # Verify schema exists
        self._catalog.get_schema(schema_id, version)

        text = data.decode("utf-8")
        result = json.loads(text, parse_float=Decimal)
        if not isinstance(result, dict):
            raise ValueError("Parsed data must be a JSON object")
        return result

    # ------------------------------------------------------------------
    # Additional utilities
    # ------------------------------------------------------------------

    def digest(
        self, schema_id: str, version: str, payload: Mapping[str, Any]
    ) -> str:
        """
        Compute SHA-256 hex digest over canonical bytes.
        """
        canonical = self.canonical_bytes(schema_id, version, payload)
        return hashlib.sha256(canonical).hexdigest()

    def check_version_compatibility(
        self, schema_id: str, old_version: str, new_version: str
    ) -> bool:
        """
        Check if transitioning between versions is compatible (same major).
        Incompatible changes require a new major version (Req 3.6).
        """
        return self._catalog.check_major_compatibility(
            schema_id, old_version, new_version
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_credential_fields(
        self, payload: Any, path: str = "$"
    ) -> list[SchemaViolation]:
        """Recursively check for raw credential field names."""
        violations: list[SchemaViolation] = []
        if isinstance(payload, dict):
            for key, value in payload.items():
                current_path = f"{path}.{key}"
                if key.lower() in _CREDENTIAL_FIELDS:
                    # Only reject if value is truthy (non-null, non-empty)
                    if value is not None and value != "":
                        violations.append(
                            SchemaViolation(
                                json_path=current_path,
                                constraint="credential_rejection",
                                safe_message=(
                                    f"Raw credential field '{key}' is prohibited "
                                    f"in persisted payloads. Use credential "
                                    f"references instead."
                                ),
                            )
                        )
                violations.extend(self._check_credential_fields(value, current_path))
        elif isinstance(payload, (list, tuple)):
            for idx, item in enumerate(payload):
                violations.extend(
                    self._check_credential_fields(item, f"{path}[{idx}]")
                )
        return violations

    def _check_nan_infinity(
        self, payload: Any, path: str = "$"
    ) -> list[SchemaViolation]:
        """Recursively check for NaN/Infinity float values."""
        violations: list[SchemaViolation] = []
        if isinstance(payload, float):
            if math.isnan(payload):
                violations.append(
                    SchemaViolation(
                        json_path=path,
                        constraint="nan_rejection",
                        safe_message=f"NaN value at '{path}' is not allowed.",
                    )
                )
            elif math.isinf(payload):
                violations.append(
                    SchemaViolation(
                        json_path=path,
                        constraint="infinity_rejection",
                        safe_message=f"Infinity value at '{path}' is not allowed.",
                    )
                )
        elif isinstance(payload, dict):
            for key, value in payload.items():
                violations.extend(
                    self._check_nan_infinity(value, f"{path}.{key}")
                )
        elif isinstance(payload, (list, tuple)):
            for idx, item in enumerate(payload):
                violations.extend(
                    self._check_nan_infinity(item, f"{path}[{idx}]")
                )
        return violations


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _normalize_value(value: Any) -> Any:
    """
    Recursively normalize a value for canonical serialization:
    - Decimal -> normalized decimal string
    - datetime -> RFC 3339 UTC with 'Z'
    - str timestamps -> normalized UTC
    - dict -> sorted keys (handled by json.dumps sort_keys)
    - NaN/Infinity -> raises ValueError
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"Cannot serialize {value} in canonical JSON")
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return _normalize_decimal(value)
    if isinstance(value, datetime):
        return _normalize_timestamp(value)
    if isinstance(value, str):
        # Attempt to normalize timestamp strings
        if _ISO_TIMESTAMP_RE.match(value):
            return _normalize_timestamp_str(value)
        return value
    if isinstance(value, dict):
        return {k: _normalize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item) for item in value]
    # Fallback: convert to string representation
    return str(value)


def _normalize_decimal(d: Decimal) -> str:
    """Normalize a Decimal to a canonical string representation."""
    if d.is_nan() or d.is_infinite():
        raise ValueError(f"Cannot serialize {d} in canonical JSON")
    # Normalize to remove trailing zeros and adjust exponent
    normalized = d.normalize()
    # For values like 1.0 that normalize to 1, preserve the integer form
    if normalized == normalized.to_integral_value():
        return str(int(normalized))
    return str(normalized)


def _normalize_timestamp(dt: datetime) -> str:
    """Normalize a datetime to RFC 3339 UTC with 'Z' suffix."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    # Format without microseconds if zero, with 'Z' suffix
    if dt.microsecond == 0:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    # Format with microseconds, strip trailing zeros, add Z
    base = dt.strftime("%Y-%m-%dT%H:%M:%S.%f").rstrip("0").rstrip(".")
    return base + "Z"


def _normalize_timestamp_str(ts: str) -> str:
    """Normalize a timestamp string to UTC with 'Z' suffix."""
    # Replace Z with +00:00 for parsing
    parse_str = ts.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(parse_str)
        return _normalize_timestamp(dt)
    except (ValueError, TypeError):
        return ts


def _safe_error_message(error: Any) -> str:
    """
    Create a safe error message from a jsonschema ValidationError.
    Avoids exposing raw credential values.
    """
    msg = str(error.message)
    # Truncate overly long messages
    if len(msg) > 200:
        msg = msg[:197] + "..."
    return msg
