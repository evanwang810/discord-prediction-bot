"""LMSR (Logarithmic Market Scoring Rule) math for binary YES/NO markets.

Each winning share pays SHARE_PAYOUT credits on resolution. The "subsidy" is the
maximum amount the market maker can lose, which equals SHARE_PAYOUT * b * ln(2).
We pick b from a credit-denominated subsidy so admins specify a meaningful number.
"""
import math

SHARE_PAYOUT = 100
LN2 = math.log(2)


def _shifted(y, n, b):
    m = max(y, n)
    return m, math.exp((y - m) / b), math.exp((n - m) / b)


def lmsr_cost(y, n, b):
    m, ey, en = _shifted(y, n, b)
    return m + b * math.log(ey + en)


def prices(y, n, b):
    """(p_yes, p_no), implied probabilities summing to 1."""
    _, ey, en = _shifted(y, n, b)
    s = ey + en
    return ey / s, en / s


def price_credits(y, n, b):
    """(yes_credits, no_credits) — credits per share."""
    py, pn = prices(y, n, b)
    return py * SHARE_PAYOUT, pn * SHARE_PAYOUT


def shares_for_credits(y, n, b, side, credits):
    """How many `side` shares `credits` worth of currency buys at the current state."""
    if credits <= 0:
        return 0.0
    budget = credits / SHARE_PAYOUT
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


def credits_for_shares(y, n, b, side, shares):
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
    return max(0.0, refund_budget * SHARE_PAYOUT)


def subsidy_to_b(subsidy):
    """Convert a credits subsidy into the LMSR liquidity parameter."""
    if subsidy <= 0:
        return 1.0
    return subsidy / (SHARE_PAYOUT * LN2)
