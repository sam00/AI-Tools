"""Model pricing → translate token savings into dollar savings.

Prices are USD per 1M input tokens (the side TokenTrim reduces). They are
intentionally easy to override via :func:`set_price` or the
``TOKENTRIM_INPUT_PRICE_PER_MTOK`` env var, since provider pricing changes often.

The goal is an honest, transparent cost estimate — not a hardcoded marketing
number. If a model is unknown, a conservative default is used and labelled as
such by callers.
"""

from __future__ import annotations

import os

# USD per 1,000,000 input tokens. Brand-free tiers — override freely via
# set_price(), the TOKENTRIM_INPUT_PRICE_PER_MTOK env var, or by registering
# your own names. Provider pricing changes often, so these are defaults only.
_INPUT_PRICE_PER_MTOK: dict[str, float] = {
    "economy": 0.30,
    "standard": 3.00,
    "premium": 15.00,
}

_DEFAULT_PRICE_PER_MTOK = 2.50  # conservative mid-tier default for unknown models


def _normalize(model: str) -> str:
    return model.lower().strip()


def input_price_per_mtok(model: str) -> float:
    """Return USD per 1M input tokens for ``model`` (env override wins)."""
    override = os.getenv("TOKENTRIM_INPUT_PRICE_PER_MTOK")
    if override:
        try:
            return float(override)
        except ValueError:
            pass
    return _INPUT_PRICE_PER_MTOK.get(_normalize(model), _DEFAULT_PRICE_PER_MTOK)


def cost_for_tokens(tokens: int, model: str = "default") -> float:
    """USD cost of ``tokens`` input tokens for ``model``."""
    return (tokens / 1_000_000.0) * input_price_per_mtok(model)


def set_price(model: str, usd_per_mtok: float) -> None:
    """Register or override the price for a model."""
    _INPUT_PRICE_PER_MTOK[model.lower().strip()] = usd_per_mtok
