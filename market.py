"""LMSR (Logarithmic Market Scoring Rule) math for binary YES/NO markets.

Each winning share pays `payout` credits on resolution (default 100). A fresh
50/50 market therefore starts at payout/2 credits per share, so the winning
payout is always exactly 2x the starting price. `payout` is captured per market
at creation, so changing the server setting only affects new markets.

The "subsidy" is the maximum the market maker can lose, = payout * b * ln(2);
we derive b from a credit-denominated subsidy so admins specify a real number.
"""
import math

SHARE_PAYOUT = 100  # default; per-market payout is passed explicitly
LN2 = math.log(2)


def _shifted(y, n, b):
    m = max(y, n)
    return m, math.exp((y - m) / b), math.exp((n - m) / b)


def lmsr_cost(y, n, b):
    m, ey, en = _shifted(y, n, b)
    return m + b * math.log(ey + en)


def prices(y, n, b):
    """(p_yes, p_no), implied probabilities summing to 1 — independent of payout."""
    _, ey, en = _shifted(y, n, b)
    s = ey + en
    return ey / s, en / s


def price_credits(y, n, b, payout=SHARE_PAYOUT):
    """(yes_credits, no_credits) — credits per share."""
    py, pn = prices(y, n, b)
    return py * payout, pn * payout


def market_cap(y, n, b, payout=SHARE_PAYOUT):
    """Total current value of all outstanding shares, in credits."""
    py, pn = prices(y, n, b)
    return (y * py + n * pn) * payout


def shares_for_credits(y, n, b, side, credits, payout=SHARE_PAYOUT):
    """How many `side` shares `credits` worth of currency buys at the current state."""
    if credits <= 0:
        return 0.0
    budget = credits / payout
    m, ey, en = _shifted(y, n, b)
    s = ey + en
    r = math.exp(budget / b)
    if side == "yes":
        inner = r * s - en
        if inner <= 0:
            return 0.0
        return m - y + b * math.log(inner)
    else:
        inner = r * s - ey
        if inner <= 0:
            return 0.0
        return m - n + b * math.log(inner)


def credits_for_shares(y, n, b, side, shares, payout=SHARE_PAYOUT):
    """Credits refunded for selling `shares` of `side` back to the market maker.

    Symmetric inverse of buying: the refund equals the drop in the LMSR cost
    function caused by removing the shares, scaled to credits.
    """
    if shares <= 0:
        return 0.0
    if side == "yes":
        refund_budget = lmsr_cost(y, n, b) - lmsr_cost(y - shares, n, b)
    else:
        refund_budget = lmsr_cost(y, n, b) - lmsr_cost(y, n - shares, b)
    return max(0.0, refund_budget * payout)


def subsidy_to_b(subsidy, payout=SHARE_PAYOUT):
    """Convert a credits subsidy into the LMSR liquidity parameter."""
    if subsidy <= 0:
        return 1.0
    return subsidy / (payout * LN2)
