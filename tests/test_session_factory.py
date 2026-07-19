"""
Tests for SessionFactoryImpl and GuardedSessionImpl.

Covers:
- Ambient credential session creation (no role_ref)
- Cross-account AssumeRole with deterministic session name
- Bounded session name length (≤64 chars)
- GuardedSession allows operations in the allowlist
- GuardedSession blocks operations NOT in the allowlist (fail closed)
- Raw temporary credentials are not stored/exposed
- External ID value is not persisted (only a boolean flag)
- Identity metadata is available for Evidence

Requirements: 6.3, 11.4, 11.6
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agentic.models import AccountTarget, StructuredError
from agentic.session import (
    GuardedSessionImpl,
    GuardViolationError,
    SessionFactoryImpl,
    SessionIdentity,
    _build_session_name,
    _RETRY_CONFIG,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def allowed_ops() -> set[str]:
    """Standard set of allowed operations for tests."""
    return {"ec2:DescribeInstances", "sts:GetCallerIdentity", "s3:ListBuckets"}


@pytest.fixture
def mock_boto3_session() -> MagicMock:
    """A mock boto3 session for testing without AWS access."""
    return MagicMock()


@pytest.fixture
def sample_identity() -> SessionIdentity:
    """A sample identity for ambient session tests."""
    return SessionIdentity(account_id="123456789012")


@pytest.fixture
def cross_account_identity() -> SessionIdentity:
    """A sample identity for cross-account session tests."""
    return SessionIdentity(
        account_id="987654321098",
        role_arn="arn:aws:iam::987654321098:role/AssessmentRole",
        session_name="agentic-run12345-98765432",
        external_id_present=True,
    )


# ---------------------------------------------------------------------------
# SessionIdentity Tests
# ---------------------------------------------------------------------------


class TestSessionIdentity:
    """Tests for the SessionIdentity dataclass."""

    def test_identity_is_frozen(self) -> None:
        """SessionIdentity is immutable."""
        identity = SessionIdentity(account_id="123456789012")
        with pytest.raises(Exception):  # FrozenInstanceError
            identity.account_id = "other"  # type: ignore[misc]

    def test_default_values(self) -> None:
        """SessionIdentity defaults match the no-cross-account case."""
        identity = SessionIdentity(account_id="123456789012")
        assert identity.account_id == "123456789012"
        assert identity.role_arn is None
        assert identity.session_name is None
        assert identity.external_id_present is False

    def test_cross_account_identity(self) -> None:
        """SessionIdentity can hold cross-account metadata."""
        identity = SessionIdentity(
            account_id="987654321098",
            role_arn="arn:aws:iam::987654321098:role/MyRole",
            session_name="agentic-abcdefgh-98765432",
            external_id_present=True,
        )
        assert identity.role_arn == "arn:aws:iam::987654321098:role/MyRole"
        assert identity.session_name == "agentic-abcdefgh-98765432"
        assert identity.external_id_present is True


# ---------------------------------------------------------------------------
# Session Name Tests
# ---------------------------------------------------------------------------


class TestSessionName:
    """Tests for deterministic, bounded session name generation."""

    def test_deterministic_session_name(self) -> None:
        """Same run_id and account_id always produce the same session name."""
        name1 = _build_session_name("run-abc-12345678", "123456789012")
        name2 = _build_session_name("run-abc-12345678", "123456789012")
        assert name1 == name2

    def test_session_name_format(self) -> None:
        """Session name follows agentic-{run_id[:8]}-{account_id[:8]} format."""
        name = _build_session_name("run-abcdef-12345678", "123456789012")
        assert name == "agentic-run-abcd-12345678"

    def test_session_name_bounded_64_chars(self) -> None:
        """Session name never exceeds 64 characters (STS limit)."""
        long_run_id = "a" * 200
        long_account_id = "9" * 200
        name = _build_session_name(long_run_id, long_account_id)
        assert len(name) <= 64

    def test_session_name_with_short_inputs(self) -> None:
        """Short run_id and account_id still produce valid names."""
        name = _build_session_name("ab", "cd")
        assert name == "agentic-ab-cd"
        assert len(name) <= 64

    def test_session_name_uses_first_8_chars(self) -> None:
        """Session name uses exactly first 8 chars of each input."""
        name = _build_session_name("12345678extra", "abcdefghextra")
        assert name == "agentic-12345678-abcdefgh"


# ---------------------------------------------------------------------------
# GuardedSessionImpl Tests
# ---------------------------------------------------------------------------


class TestGuardedSession:
    """Tests for GuardedSessionImpl operation allowlist enforcement."""

    def test_allows_operations_in_allowlist(
        self, mock_boto3_session: MagicMock, allowed_ops: set[str], sample_identity: SessionIdentity
    ) -> None:
        """Operations in the allowlist are dispatched through boto3."""
        mock_client = MagicMock()
        mock_client.describe_instances.return_value = {"Reservations": []}
        mock_boto3_session.client.return_value = mock_client

        guarded = GuardedSessionImpl(
            session=mock_boto3_session,
            allowed_operations=allowed_ops,
            identity=sample_identity,
        )

        result = guarded.call("ec2", "DescribeInstances", Filters=[])
        mock_boto3_session.client.assert_called_once_with("ec2", config=_RETRY_CONFIG)
        # Real boto3 clients expose snake_case methods, not the PascalCase
        # IAM-action-style operation name used in the allowlist key.
        mock_client.describe_instances.assert_called_once_with(Filters=[])

    def test_blocks_operations_not_in_allowlist(
        self, mock_boto3_session: MagicMock, allowed_ops: set[str], sample_identity: SessionIdentity
    ) -> None:
        """Operations NOT in the allowlist raise GuardViolationError."""
        guarded = GuardedSessionImpl(
            session=mock_boto3_session,
            allowed_operations=allowed_ops,
            identity=sample_identity,
        )

        with pytest.raises(GuardViolationError) as exc_info:
            guarded.call("ec2", "TerminateInstances", InstanceIds=["i-123"])

        error = exc_info.value.error
        assert error.category == "guard-violation"
        assert error.retryable is False
        assert "TerminateInstances" in error.safe_message

        # Verify the boto3 client was NEVER called
        mock_boto3_session.client.assert_not_called()

    def test_fail_closed_empty_allowlist(
        self, mock_boto3_session: MagicMock, sample_identity: SessionIdentity
    ) -> None:
        """With an empty allowlist, ALL operations are blocked (fail closed)."""
        guarded = GuardedSessionImpl(
            session=mock_boto3_session,
            allowed_operations=set(),
            identity=sample_identity,
        )

        with pytest.raises(GuardViolationError):
            guarded.call("ec2", "DescribeInstances")

        mock_boto3_session.client.assert_not_called()

    def test_guard_violation_error_has_structured_error(
        self, mock_boto3_session: MagicMock, sample_identity: SessionIdentity
    ) -> None:
        """GuardViolationError wraps a StructuredError with correct fields."""
        guarded = GuardedSessionImpl(
            session=mock_boto3_session,
            allowed_operations={"sts:GetCallerIdentity"},
            identity=sample_identity,
        )

        with pytest.raises(GuardViolationError) as exc_info:
            guarded.call("rds", "DeleteDBInstance")

        error = exc_info.value.error
        assert isinstance(error, StructuredError)
        assert error.code == "GUARD_VIOLATION"
        assert error.category == "guard-violation"
        assert error.retryable is False
        assert error.account_id == "123456789012"

    def test_identity_metadata_available(
        self, mock_boto3_session: MagicMock, allowed_ops: set[str], cross_account_identity: SessionIdentity
    ) -> None:
        """GuardedSession exposes identity metadata for Evidence."""
        guarded = GuardedSessionImpl(
            session=mock_boto3_session,
            allowed_operations=allowed_ops,
            identity=cross_account_identity,
        )

        assert guarded.identity.account_id == "987654321098"
        assert guarded.identity.role_arn == "arn:aws:iam::987654321098:role/AssessmentRole"
        assert guarded.identity.session_name == "agentic-run12345-98765432"
        assert guarded.identity.external_id_present is True

    def test_allowed_operations_are_frozen(
        self, mock_boto3_session: MagicMock, allowed_ops: set[str], sample_identity: SessionIdentity
    ) -> None:
        """Allowed operations are immutable after construction."""
        guarded = GuardedSessionImpl(
            session=mock_boto3_session,
            allowed_operations=allowed_ops,
            identity=sample_identity,
        )

        assert isinstance(guarded.allowed_operations, frozenset)
        assert guarded.allowed_operations == frozenset(allowed_ops)


# ---------------------------------------------------------------------------
# SessionFactoryImpl Tests
# ---------------------------------------------------------------------------


class TestSessionFactory:
    """Tests for SessionFactoryImpl credential handling and session creation."""

    @patch("agentic.session.boto3.session.Session")
    def test_ambient_credential_session(self, mock_session_cls: MagicMock) -> None:
        """Ambient credential session uses default boto3 session (no role_ref)."""
        mock_session_cls.return_value = MagicMock()

        factory = SessionFactoryImpl(
            run_id="test-run-12345678",
            allowed_operations={"ec2:DescribeInstances"},
        )
        target = AccountTarget(account_id="123456789012", role_ref=None)
        guarded = factory.for_account(target)

        # Session was created with no explicit credentials
        mock_session_cls.assert_called_once_with()

        # Identity reflects ambient session
        assert guarded.identity.account_id == "123456789012"
        assert guarded.identity.role_arn is None
        assert guarded.identity.session_name is None
        assert guarded.identity.external_id_present is False

    @patch("agentic.session.boto3.client")
    @patch("agentic.session.boto3.session.Session")
    def test_cross_account_assume_role(
        self, mock_session_cls: MagicMock, mock_boto3_client: MagicMock
    ) -> None:
        """Cross-account targets use STS AssumeRole with deterministic session name."""
        # Mock STS response
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "ASIA_TEMP_KEY",
                "SecretAccessKey": "temp_secret",
                "SessionToken": "temp_token",
            }
        }
        mock_boto3_client.return_value = mock_sts
        mock_session_cls.return_value = MagicMock()

        factory = SessionFactoryImpl(
            run_id="run-abcdef-12345",
            allowed_operations={"ec2:DescribeInstances"},
        )
        target = AccountTarget(
            account_id="987654321098",
            role_ref="arn:aws:iam::987654321098:role/AssessmentRole",
        )
        guarded = factory.for_account(target)

        # STS AssumeRole was called
        mock_boto3_client.assert_called_once_with("sts")
        call_kwargs = mock_sts.assume_role.call_args[1]
        assert call_kwargs["RoleArn"] == "arn:aws:iam::987654321098:role/AssessmentRole"
        assert call_kwargs["RoleSessionName"] == "agentic-run-abcd-98765432"

        # Session was created with temporary credentials (passed through, not stored)
        mock_session_cls.assert_called_once_with(
            aws_access_key_id="ASIA_TEMP_KEY",
            aws_secret_access_key="temp_secret",
            aws_session_token="temp_token",
        )

        # Identity has cross-account metadata
        assert guarded.identity.account_id == "987654321098"
        assert guarded.identity.role_arn == "arn:aws:iam::987654321098:role/AssessmentRole"
        assert guarded.identity.session_name == "agentic-run-abcd-98765432"

    @patch("agentic.session.boto3.client")
    @patch("agentic.session.boto3.session.Session")
    def test_external_id_present_flag_recorded(
        self, mock_session_cls: MagicMock, mock_boto3_client: MagicMock
    ) -> None:
        """External ID presence is recorded as boolean, value is NOT stored."""
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "ASIA_TEMP",
                "SecretAccessKey": "secret",
                "SessionToken": "token",
            }
        }
        mock_boto3_client.return_value = mock_sts
        mock_session_cls.return_value = MagicMock()

        factory = SessionFactoryImpl(
            run_id="run-12345678",
            allowed_operations={"sts:GetCallerIdentity"},
            external_id_supplier=lambda: "super-secret-external-id-12345",
        )
        target = AccountTarget(
            account_id="111222333444",
            role_ref="arn:aws:iam::111222333444:role/CrossRole",
        )
        guarded = factory.for_account(target)

        # The boolean flag is True
        assert guarded.identity.external_id_present is True

        # The actual external ID value is NOT stored anywhere on the identity
        identity_dict = {
            "account_id": guarded.identity.account_id,
            "role_arn": guarded.identity.role_arn,
            "session_name": guarded.identity.session_name,
            "external_id_present": guarded.identity.external_id_present,
        }
        # No field contains the external ID value
        for value in identity_dict.values():
            if isinstance(value, str):
                assert "super-secret-external-id-12345" not in value

    @patch("agentic.session.boto3.client")
    @patch("agentic.session.boto3.session.Session")
    def test_external_id_not_present(
        self, mock_session_cls: MagicMock, mock_boto3_client: MagicMock
    ) -> None:
        """When no external_id_supplier is provided, flag is False."""
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "ASIA_KEY",
                "SecretAccessKey": "secret",
                "SessionToken": "token",
            }
        }
        mock_boto3_client.return_value = mock_sts
        mock_session_cls.return_value = MagicMock()

        factory = SessionFactoryImpl(
            run_id="run-99887766",
            allowed_operations=set(),
            external_id_supplier=None,
        )
        target = AccountTarget(
            account_id="555666777888",
            role_ref="arn:aws:iam::555666777888:role/Role",
        )
        guarded = factory.for_account(target)

        assert guarded.identity.external_id_present is False

    @patch("agentic.session.boto3.session.Session")
    def test_no_raw_credentials_stored_on_factory(
        self, mock_session_cls: MagicMock
    ) -> None:
        """SessionFactoryImpl does not store raw credentials in any attribute."""
        factory = SessionFactoryImpl(
            run_id="test-run-id",
            allowed_operations={"ec2:DescribeInstances"},
        )

        # Check that factory has no credential attributes
        factory_attrs = vars(factory)
        for attr_name, attr_value in factory_attrs.items():
            if isinstance(attr_value, str):
                assert "AKIA" not in attr_value
                assert "aws_secret" not in attr_value.lower()
                assert "session_token" not in attr_value.lower()

    @patch("agentic.session.boto3.client")
    @patch("agentic.session.boto3.session.Session")
    def test_no_raw_credentials_stored_on_guarded_session(
        self, mock_session_cls: MagicMock, mock_boto3_client: MagicMock
    ) -> None:
        """GuardedSessionImpl does not expose raw credentials in identity."""
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "ASIATEMP123456",
                "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "SessionToken": "FwoGZXIvYXdzEBYaDH...",
            }
        }
        mock_boto3_client.return_value = mock_sts
        mock_session_cls.return_value = MagicMock()

        factory = SessionFactoryImpl(
            run_id="run-sectest-001",
            allowed_operations={"sts:GetCallerIdentity"},
        )
        target = AccountTarget(
            account_id="999888777666",
            role_ref="arn:aws:iam::999888777666:role/SecureRole",
        )
        guarded = factory.for_account(target)

        # Identity does not contain any credential material
        identity = guarded.identity
        assert "ASIATEMP123456" not in str(identity)
        assert "wJalrXUtnFEMI" not in str(identity)
        assert "FwoGZXIvYXdz" not in str(identity)

    @patch("agentic.session.boto3.session.Session")
    def test_factory_passes_allowed_operations_to_guarded_session(
        self, mock_session_cls: MagicMock
    ) -> None:
        """Factory correctly passes the allowed_operations to the GuardedSession."""
        mock_session_cls.return_value = MagicMock()
        ops = {"ec2:DescribeInstances", "s3:ListBuckets"}

        factory = SessionFactoryImpl(run_id="test-run", allowed_operations=ops)
        target = AccountTarget(account_id="123456789012")
        guarded = factory.for_account(target)

        assert guarded.allowed_operations == frozenset(ops)
