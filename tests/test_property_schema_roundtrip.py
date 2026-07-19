# Feature: agentic-aws-assessment, Property 4: Canonical schema processing round-trips
"""
Property-based test for canonical schema processing round-trips.

Validates: Requirements 3.2, 3.3, 3.4, 3.5

Properties tested:
1. Round-trip byte equivalence: canonical_bytes(parse(canonical_bytes(p))) == canonical_bytes(p)
2. Sorted keys at every nesting level in canonical output
3. Compact separators (no extra whitespace)
4. Invalid payloads always produce non-empty violations
5. NaN/Infinity rejection by both validate() and canonical_bytes()
6. Credential field rejection
"""

from __future__ import annotations

import json
import math
from typing import Any

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from agentic.schemas.processor import CanonicalSchemaProcessor, _CREDENTIAL_FIELDS


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

VALID_CATEGORIES = [
    "validation",
    "unsupported",
    "permission-denied",
    "throttled",
    "transient",
    "guard-violation",
    "internal",
    "conflict",
]

# Safe string strategy that avoids credential field names and NaN/Infinity
_safe_text = st.text(
    alphabet=st.characters(
        categories=("L", "N", "P", "S", "Z"),
        exclude_characters="\x00",
    ),
    min_size=1,
    max_size=50,
)

# Non-empty code string
_code_text = st.text(
    alphabet=st.characters(categories=("L", "N"), exclude_characters="\x00"),
    min_size=1,
    max_size=30,
)

# Safe message (can be empty)
_safe_message_text = st.text(
    alphabet=st.characters(
        categories=("L", "N", "P", "S", "Z"),
        exclude_characters="\x00",
    ),
    min_size=0,
    max_size=100,
)


@st.composite
def valid_structured_error_payloads(draw: st.DrawFn) -> dict[str, Any]:
    """Generate valid structured-error payloads for round-trip testing."""
    code = draw(_code_text)
    category = draw(st.sampled_from(VALID_CATEGORIES))
    retryable = draw(st.booleans())
    safe_message = draw(_safe_message_text)

    payload: dict[str, Any] = {
        "schema_id": "structured-error",
        "schema_version": "1.0.0",
        "code": code,
        "category": category,
        "retryable": retryable,
        "safe_message": safe_message,
    }

    # Optionally add nullable fields
    if draw(st.booleans()):
        payload["capability_id"] = draw(st.one_of(st.none(), _safe_text))
    if draw(st.booleans()):
        payload["account_id"] = draw(st.one_of(st.none(), _safe_text))
    if draw(st.booleans()):
        payload["region_scope"] = draw(st.one_of(st.none(), _safe_text))
    if draw(st.booleans()):
        num_violations = draw(st.integers(min_value=0, max_value=3))
        violations = []
        for _ in range(num_violations):
            violations.append({
                "json_path": "$." + draw(_code_text),
                "constraint": draw(_code_text),
                "safe_message": draw(_safe_message_text),
            })
        payload["violations"] = violations

    return payload


@st.composite
def invalid_structured_error_payloads(draw: st.DrawFn) -> dict[str, Any]:
    """Generate payloads missing required fields or with wrong types."""
    # Pre-generated invalid category values that are NOT in the valid set
    INVALID_CATEGORIES = [
        "invalid", "unknown", "error", "warning", "critical",
        "timeout", "network", "auth", "forbidden", "not-found",
    ]

    defect_type = draw(st.sampled_from([
        "missing_code",
        "missing_category",
        "wrong_type_retryable",
        "invalid_category",
        "missing_schema_id",
        "missing_safe_message",
        "empty_code",
    ]))

    payload: dict[str, Any] = {
        "schema_id": "structured-error",
        "schema_version": "1.0.0",
        "code": "VALID_CODE",
        "category": "internal",
        "retryable": False,
        "safe_message": "test message",
    }

    if defect_type == "missing_code":
        del payload["code"]
    elif defect_type == "missing_category":
        del payload["category"]
    elif defect_type == "wrong_type_retryable":
        payload["retryable"] = draw(st.one_of(
            st.text(min_size=1, max_size=10),
            st.integers(),
            st.lists(st.booleans(), max_size=2),
        ))
    elif defect_type == "invalid_category":
        payload["category"] = draw(st.sampled_from(INVALID_CATEGORIES))
    elif defect_type == "missing_schema_id":
        del payload["schema_id"]
    elif defect_type == "missing_safe_message":
        del payload["safe_message"]
    elif defect_type == "empty_code":
        payload["code"] = ""  # minLength 1 violated

    return payload


# JSON-like values without NaN/Infinity/credentials for nesting tests
_json_leaf = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-1000, max_value=1000),
    st.text(
        alphabet=st.characters(categories=("L", "N"), exclude_characters="\x00"),
        min_size=0,
        max_size=20,
    ),
)

# Safe key names that are not credential fields
_safe_key = st.text(
    alphabet=st.characters(categories=("L", "N"), exclude_characters="\x00"),
    min_size=1,
    max_size=15,
).filter(lambda k: k.lower() not in _CREDENTIAL_FIELDS)


_json_value = st.recursive(
    _json_leaf,
    lambda children: st.one_of(
        st.lists(children, max_size=3),
        st.dictionaries(_safe_key, children, max_size=3),
    ),
    max_leaves=10,
)


@st.composite
def nan_infinity_payloads(draw: st.DrawFn) -> dict[str, Any]:
    """Generate payloads that contain NaN or Infinity at random positions."""
    bad_value = draw(st.sampled_from([
        float("nan"),
        float("inf"),
        float("-inf"),
    ]))

    # Build a valid base payload with the bad value injected
    injection_point = draw(st.sampled_from([
        "top_level",
        "nested_dict",
        "nested_list",
    ]))

    payload: dict[str, Any] = {
        "schema_id": "structured-error",
        "schema_version": "1.0.0",
        "code": "TEST",
        "category": "internal",
        "retryable": False,
        "safe_message": "test",
    }

    if injection_point == "top_level":
        payload["bad_field"] = bad_value
    elif injection_point == "nested_dict":
        payload["nested"] = {"inner": bad_value}
    elif injection_point == "nested_list":
        payload["items"] = [bad_value]

    return payload


@st.composite
def credential_payloads(draw: st.DrawFn) -> dict[str, Any]:
    """Generate payloads with raw credential field names."""
    cred_field = draw(st.sampled_from(sorted(_CREDENTIAL_FIELDS)))
    # Value must be non-null, non-empty for detection
    cred_value = draw(st.text(
        alphabet=st.characters(categories=("L", "N"), exclude_characters="\x00"),
        min_size=1,
        max_size=30,
    ))

    injection = draw(st.sampled_from(["top_level", "nested"]))

    payload: dict[str, Any] = {
        "schema_id": "structured-error",
        "schema_version": "1.0.0",
        "code": "TEST",
        "category": "internal",
        "retryable": False,
        "safe_message": "test",
    }

    if injection == "top_level":
        payload[cred_field] = cred_value
    else:
        payload["nested"] = {cred_field: cred_value}

    return payload


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------

processor = CanonicalSchemaProcessor()


class TestCanonicalSchemaRoundTrip:
    """Property 4: Canonical schema processing round-trips."""

    @given(payload=valid_structured_error_payloads())
    @settings(max_examples=100)
    def test_roundtrip_byte_equivalence(self, payload: dict[str, Any]) -> None:
        """
        Req 3.5: For any valid payload,
        canonical_bytes(parse(canonical_bytes(payload))) produces
        byte-identical output to canonical_bytes(payload).
        """
        # First serialization
        first_bytes = processor.canonical_bytes(
            "structured-error", "1.0.0", payload
        )

        # Parse back
        parsed = processor.parse("structured-error", "1.0.0", first_bytes)

        # Second serialization
        second_bytes = processor.canonical_bytes(
            "structured-error", "1.0.0", parsed
        )

        # Must be byte-equivalent
        assert first_bytes == second_bytes, (
            f"Round-trip failed:\n"
            f"  first:  {first_bytes!r}\n"
            f"  second: {second_bytes!r}"
        )

    @given(payload=valid_structured_error_payloads())
    @settings(max_examples=100)
    def test_sorted_keys_at_all_levels(self, payload: dict[str, Any]) -> None:
        """
        Req 3.4: Canonical bytes always have sorted object keys
        at every nesting level.
        """
        canonical = processor.canonical_bytes(
            "structured-error", "1.0.0", payload
        )
        parsed = json.loads(canonical)
        _assert_keys_sorted(parsed)

    @given(payload=valid_structured_error_payloads())
    @settings(max_examples=100)
    def test_compact_separators(self, payload: dict[str, Any]) -> None:
        """
        Req 3.4: No extra whitespace in serialized output.
        Compact separators use ',' and ':' without spaces.
        """
        canonical = processor.canonical_bytes(
            "structured-error", "1.0.0", payload
        )
        text = canonical.decode("utf-8")

        # After a colon separating key from value there should be no space
        # The pattern ": " only appears in compact JSON inside string values
        # We verify by re-serializing with compact separators and comparing
        reparsed = json.loads(text)
        expected = json.dumps(
            reparsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        assert text == expected, (
            f"Non-compact output detected:\n"
            f"  actual:   {text!r}\n"
            f"  expected: {expected!r}"
        )

    @given(payload=invalid_structured_error_payloads())
    @settings(max_examples=100)
    def test_invalid_payloads_produce_violations(
        self, payload: dict[str, Any]
    ) -> None:
        """
        Req 3.3: Invalid payloads always produce non-empty violations list.
        """
        result = processor.validate("structured-error", "1.0.0", payload)
        assert not result.is_valid, (
            f"Expected validation failure for payload: {payload}"
        )
        assert len(result.violations) > 0, (
            f"Expected non-empty violations for invalid payload: {payload}"
        )

    @given(payload=nan_infinity_payloads())
    @settings(max_examples=100)
    def test_nan_infinity_rejected(self, payload: dict[str, Any]) -> None:
        """
        NaN/Infinity rejection: Any payload containing NaN or Infinity is
        rejected by both validate() and canonical_bytes().
        """
        # validate() should detect NaN/Infinity
        result = processor.validate("structured-error", "1.0.0", payload)
        assert not result.is_valid, (
            f"Expected NaN/Infinity to be rejected by validate(): {payload}"
        )
        nan_inf_violations = [
            v for v in result.violations
            if "nan" in v.constraint or "infinity" in v.constraint
        ]
        assert len(nan_inf_violations) > 0, (
            "Expected nan/infinity violation constraint"
        )

        # canonical_bytes() should raise ValueError
        try:
            processor.canonical_bytes("structured-error", "1.0.0", payload)
            assert False, "Expected ValueError for NaN/Infinity in canonical_bytes()"
        except ValueError:
            pass  # Expected

    @given(payload=credential_payloads())
    @settings(max_examples=100)
    def test_credential_rejection(self, payload: dict[str, Any]) -> None:
        """
        Credential rejection: Any payload with raw credential field names
        is rejected by both validate() and canonical_bytes().
        """
        # validate() should detect credential fields
        result = processor.validate("structured-error", "1.0.0", payload)
        assert not result.is_valid, (
            f"Expected credential field to be rejected: {payload}"
        )
        cred_violations = [
            v for v in result.violations
            if "credential" in v.constraint
        ]
        assert len(cred_violations) > 0, (
            "Expected credential_rejection violation"
        )

        # canonical_bytes() should raise ValueError
        try:
            processor.canonical_bytes("structured-error", "1.0.0", payload)
            assert False, "Expected ValueError for credential fields"
        except ValueError:
            pass  # Expected


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_keys_sorted(value: Any) -> None:
    """Recursively assert all dict keys are sorted at every level."""
    if isinstance(value, dict):
        keys = list(value.keys())
        assert keys == sorted(keys), f"Keys not sorted: {keys}"
        for v in value.values():
            _assert_keys_sorted(v)
    elif isinstance(value, list):
        for item in value:
            _assert_keys_sorted(item)
