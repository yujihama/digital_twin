"""Alternative agent policies (rule-based, etc.) used for ablation experiments.

The default LLM-backed agents live in :mod:`oct.agent`. This package contains
non-LLM policies that share the same :class:`oct.agent.Agent` interface so they
can be dropped into the existing runner / dispatcher without modification.

See ``docs/09_ablation_plan.md`` for the experimental design that motivates
these agents.
"""

from oct.agents.rb_min import (
    RBMinAccountantAgent,
    RBMinAgent,
    RBMinApproverAgent,
    RBMinBuyerAgent,
    RBMinVendorAgent,
    build_rb_min_agents,
)

__all__ = [
    "RBMinAccountantAgent",
    "RBMinAgent",
    "RBMinApproverAgent",
    "RBMinBuyerAgent",
    "RBMinVendorAgent",
    "build_rb_min_agents",
]
