"""Domain-specific agent personas for the purchase-approval prototype.

Each persona module exports a `make_agent()` factory returning an `Agent`
configured with role-appropriate prompt and action schema. Kept under a
separate package so the generic `oct.agent` module stays environment-agnostic.
"""
