"""Net worth = balance + open positions valued at current market price."""
from db import connect
from market import prices, SHARE_PAYOUT


async def guild_net_worths(db, guild_id: int) -> dict[int, float]:
    async with db.execute(
        "SELECT user_id, balance FROM accounts WHERE guild_id = ?", (guild_id,)
    ) as cur:
        net = {r["user_id"]: float(r["balance"]) for r in await cur.fetchall()}
    async with db.execute(
        "SELECT p.user_id, p.yes_shares, p.no_shares, "
        "m.yes_shares AS my, m.no_shares AS mn, m.liquidity "
        "FROM positions p JOIN markets m ON p.market_id = m.market_id "
        "WHERE p.guild_id = ? AND m.status = 'open' "
        "AND (p.yes_shares > 0 OR p.no_shares > 0)",
        (guild_id,),
    ) as cur:
        for p in await cur.fetchall():
            if p["user_id"] not in net:
                continue
            py, pn = prices(p["my"], p["mn"], p["liquidity"])
            net[p["user_id"]] += (p["yes_shares"] * py + p["no_shares"] * pn) * SHARE_PAYOUT
    return net
