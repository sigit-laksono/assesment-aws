"""
Assessment Profiles — Pre-built profile artifacts.

Exports factory functions for instantiating baseline assessment profiles.
"""

from agentic.profiles.monthly_standard_v1 import create_monthly_standard_v1

__all__ = [
    "create_monthly_standard_v1",
]
