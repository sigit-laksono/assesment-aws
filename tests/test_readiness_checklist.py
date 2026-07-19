"""
Readiness checklist test (Task 8.1).

Runs `assert_capability_ready()` against every capability registered in
the Capability Registry — `ec2.inventory` (Task 2) plus all 25 legacy
capabilities migrated in Task 6 — and asserts the failure list is empty
for each.

**Validates: Requirements 13.1**
"""

from __future__ import annotations

import pytest

from agentic.ec2_collector import EC2InventoryCollector
from agentic.ec2_contract import register_ec2_inventory
from agentic.legacy_contracts import register_all_legacy_capabilities
from agentic.readiness import assert_capability_ready
from agentic.registry import CapabilityRegistryImpl, RegisteredCapability


@pytest.fixture
def full_registry() -> CapabilityRegistryImpl:
    registry = CapabilityRegistryImpl()
    register_ec2_inventory(registry, EC2InventoryCollector())
    register_all_legacy_capabilities(registry)
    return registry


def test_every_registered_capability_is_ready(full_registry: CapabilityRegistryImpl) -> None:
    manifest = full_registry.snapshot()
    assert len(manifest.capabilities) >= 26  # ec2.inventory + 25 legacy capabilities

    for descriptor in manifest.capabilities:
        entry = full_registry.resolve(descriptor.capability_id, str(descriptor.version))
        assert isinstance(entry, RegisteredCapability)
        assert assert_capability_ready(entry) == []
