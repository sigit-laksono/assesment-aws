"""
Agentic AWS Assessment — Session Factory and Guarded Session.

Implements:
- SessionFactoryImpl: Creates guarded sessions per account using ambient
  credentials or declared role references (STS AssumeRole). (Req 6.3, 11.4, 11.6)
- GuardedSessionImpl: Drop-in boundary that intercepts every SDK operation
  and checks it against the resolved capability allowlist before dispatch.
- SessionIdentity: Identity metadata for Evidence and security audit.

Security invariants:
- No raw credentials (access_key, secret_key, session_token) are stored.
- External ID value is NEVER persisted — only a boolean flag.
- Session names are deterministic and bounded (≤64 chars).
- Unknown operations fail closed with a non-retryable StructuredError.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import re

import boto3
import boto3.session
from botocore.config import Config

from agentic.models import AccountTarget, StructuredError

try:
    # botocore.xform_name is the same helper botocore itself uses to derive
    # client method names (e.g. "DescribeDBInstances" -> "describe_db_instances")
    # from API operation names, so it's the authoritative conversion. It's an
    # internal/undocumented API (no __all__ entry, not part of boto3's public
    # docs) — fall back to a hand-rolled converter if the import ever breaks.
    from botocore import xform_name as _xform_operation_name
except ImportError:  # pragma: no cover - defensive fallback
    def _xform_operation_name(operation: str) -> str:
        # ponytail: minimal CamelCase -> snake_case fallback mirroring
        # botocore's own regex-based approach, for use only if the internal
        # botocore.xform_name helper is ever removed/renamed upstream.
        s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", operation)
        s2 = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s1)
        return s2.lower()

# ponytail: rely on botocore's built-in standard retry mode instead of a
# custom retry loop/backoff. 3 attempts covers transient throttling/5xx.
_RETRY_CONFIG = Config(retries={"max_attempts": 3, "mode": "standard"})


# ---------------------------------------------------------------------------
# Identity Metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionIdentity:
    """
    Identity metadata for Evidence and security audit.

    Contains account context and optional cross-account role information.
    The external_id_present flag records whether an external ID was supplied
    for the AssumeRole call WITHOUT persisting the actual value.
    """

    account_id: str
    role_arn: str | None = None
    session_name: str | None = None
    external_id_present: bool = False


# ---------------------------------------------------------------------------
# Guarded Session Implementation
# ---------------------------------------------------------------------------


class GuardedSessionImpl:
    """
    Session boundary that intercepts every SDK operation and checks it
    against the resolved capability allowlist before dispatch.

    Operations not in the allowlist are rejected with a non-retryable
    StructuredError (guard-violation). All operations fail closed.
    """

    def __init__(
        self,
        session: boto3.session.Session,
        allowed_operations: set[str],
        identity: SessionIdentity,
    ) -> None:
        self._session = session
        self._allowed_operations = frozenset(allowed_operations)
        self._identity = identity

    @property
    def identity(self) -> SessionIdentity:
        """Return identity metadata for Evidence and audit."""
        return self._identity

    @property
    def allowed_operations(self) -> frozenset[str]:
        """Return the immutable set of allowed operations."""
        return self._allowed_operations

    def call(self, service: str, operation: str, **kwargs: Any) -> Any:
        """
        Execute an AWS SDK operation only if it appears in the allowlist.
        Unknown or non-member operations fail closed with a guard-violation error.
        """
        operation_key = f"{service}:{operation}"

        if operation_key not in self._allowed_operations:
            raise GuardViolationError(
                StructuredError(
                    code="GUARD_VIOLATION",
                    category="guard-violation",
                    retryable=False,
                    safe_message=(
                        f"Operation '{operation_key}' is not in the "
                        f"capability allowlist. Fail closed."
                    ),
                    account_id=self._identity.account_id,
                )
            )

        # Dispatch through boto3 client. `operation` is the PascalCase IAM
        # action name (matches the allowlist key), but real boto3 clients
        # expose snake_case methods — convert before getattr().
        client = self._session.client(service, config=_RETRY_CONFIG)
        method_name = _xform_operation_name(operation)
        api_method = getattr(client, method_name)
        return api_method(**kwargs)


# ---------------------------------------------------------------------------
# Guard Violation Error
# ---------------------------------------------------------------------------


class GuardViolationError(Exception):
    """
    Raised when a GuardedSession rejects an operation not in the allowlist.
    Wraps a StructuredError with category='guard-violation' and retryable=False.
    """

    def __init__(self, error: StructuredError) -> None:
        self.error = error
        super().__init__(error.safe_message)


# ---------------------------------------------------------------------------
# Session Factory Implementation
# ---------------------------------------------------------------------------


def _build_session_name(run_id: str, account_id: str) -> str:
    """
    Generate a deterministic, bounded session name for STS AssumeRole.

    Format: "agentic-{run_id[:8]}-{account_id[:8]}"
    STS session name max length is 64 characters.
    """
    name = f"agentic-{run_id[:8]}-{account_id[:8]}"
    # Ensure the session name is bounded at 64 chars (STS limit)
    return name[:64]


class SessionFactoryImpl:
    """
    Creates guarded sessions per account. Uses ambient SDK credential
    resolution or declared role references for cross-account access.

    Persisted requests contain no access key, secret, or session token.
    Cross-account targets use STS AssumeRole with a deterministic,
    bounded session name derived from run/account.
    """

    def __init__(
        self,
        run_id: str,
        allowed_operations: set[str] | None = None,
        external_id_supplier: Any | None = None,
    ) -> None:
        """
        Initialize SessionFactory.

        Args:
            run_id: The assessment run identifier.
            allowed_operations: Set of allowed operations for the security guard.
                If None, defaults to an empty set (all operations blocked).
            external_id_supplier: Optional callable that returns the external ID
                for AssumeRole. The factory records only whether it was supplied,
                NEVER the value itself.
        """
        self._run_id = run_id
        self._allowed_operations: set[str] = allowed_operations or set()
        self._external_id_supplier = external_id_supplier

    def for_account(self, target: AccountTarget) -> GuardedSessionImpl:
        """
        Create a guarded session for the specified account target.
        Uses ambient credentials or declared role reference.
        """
        if target.role_ref is not None:
            return self._create_cross_account_session(target)
        else:
            return self._create_ambient_session(target)

    def _create_ambient_session(self, target: AccountTarget) -> GuardedSessionImpl:
        """Create a session using ambient SDK credentials (no AssumeRole)."""
        session = boto3.session.Session()
        identity = SessionIdentity(
            account_id=target.account_id,
            role_arn=None,
            session_name=None,
            external_id_present=False,
        )
        return GuardedSessionImpl(
            session=session,
            allowed_operations=self._allowed_operations,
            identity=identity,
        )

    def _create_cross_account_session(
        self, target: AccountTarget
    ) -> GuardedSessionImpl:
        """
        Create a session using STS AssumeRole for cross-account access.

        The role ARN is constructed from the role_ref. A deterministic
        session name is generated. External ID presence is recorded but
        the value itself is NEVER stored.
        """
        role_arn = target.role_ref  # role_ref is already a full ARN or reference
        session_name = _build_session_name(self._run_id, target.account_id)

        # Determine if external ID is supplied (record boolean only)
        external_id_present = False
        assume_role_kwargs: dict[str, Any] = {
            "RoleArn": role_arn,
            "RoleSessionName": session_name,
        }

        if self._external_id_supplier is not None:
            external_id_value = self._external_id_supplier()
            if external_id_value:
                external_id_present = True
                assume_role_kwargs["ExternalId"] = external_id_value

        # Call STS AssumeRole using ambient credentials
        sts_client = boto3.client("sts")
        response = sts_client.assume_role(**assume_role_kwargs)

        # Extract temporary credentials for session creation ONLY —
        # these are NOT stored on any persisted model.
        credentials = response["Credentials"]
        session = boto3.session.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
        )

        # Build identity metadata (no raw credentials, no external ID value)
        identity = SessionIdentity(
            account_id=target.account_id,
            role_arn=role_arn,
            session_name=session_name,
            external_id_present=external_id_present,
        )

        return GuardedSessionImpl(
            session=session,
            allowed_operations=self._allowed_operations,
            identity=identity,
        )
