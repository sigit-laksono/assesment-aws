"""
Agentic AWS Assessment — Readiness Checklist (Requirement 13.1).

One pure function that checks whether a registered capability is
agent-ready: input schema declared, output schema declared, non-empty
Read-Only Allowlist, and a non-interactive handler (does not call the
built-in `input()`). Used as a test fixture across the whole registry,
not a runtime component.

ponytail: `handler` isn't a field on `CapabilityDescriptor` (agentic/models.py)
— only the registry's `RegisteredCapability` (descriptor + handler) has both,
and Requirement 13.1 explicitly requires checking the handler for
interactivity. So this function takes the registered entry (descriptor +
handler) rather than a bare descriptor. The "non-interactive handler" check
is a simple source-text scan for a literal `input(` call in the handler's
`collect` method — good enough to catch an accidentally-reintroduced
`input()` prompt without building a full call-graph analyzer.
"""

from __future__ import annotations

import inspect
from typing import Any

from agentic.registry import RegisteredCapability


def assert_capability_ready(entry: RegisteredCapability) -> list[str]:
    """
    Return every readiness failure message for one registered capability.
    An empty list means the capability is agent-ready.
    """
    failures: list[str] = []
    descriptor = entry.descriptor
    cap_id = descriptor.capability_id

    if not descriptor.input_schema_ref:
        failures.append(f"{cap_id}: missing input_schema_ref")
    if not descriptor.output_schema_ref:
        failures.append(f"{cap_id}: missing output_schema_ref")
    if not descriptor.allowed_operations:
        failures.append(f"{cap_id}: allowed_operations is empty")
    if _handler_is_interactive(entry.handler):
        failures.append(f"{cap_id}: handler appears to call input() (interactive)")

    return failures


def _handler_is_interactive(handler: Any) -> bool:
    """Scan the handler's `collect` source for a literal `input(` call."""
    collect_fn = getattr(handler, "collect", handler)
    try:
        source = inspect.getsource(collect_fn)
    except (OSError, TypeError):
        return False
    return "input(" in source


if __name__ == "__main__":
    # ponytail: minimal runnable self-check; full coverage lands in the
    # dedicated test in tests/test_readiness_checklist.py.
    from agentic.ec2_collector import EC2InventoryCollector
    from agentic.ec2_contract import register_ec2_inventory
    from agentic.registry import CapabilityRegistryImpl

    registry = CapabilityRegistryImpl()
    register_ec2_inventory(registry, EC2InventoryCollector())
    entry = registry.resolve("ec2.inventory", "1.0.0")
    assert not isinstance(entry, list)
    assert assert_capability_ready(entry) == []
    print("assert_capability_ready() self-check passed")
