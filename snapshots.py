"""Daily net-worth snapshots powering the /portfolio graph.

A snapshot is taken once a day by the background loop, and also right after a
user trades (so the graph reflects activity immediately). We keep at most
SNAPSHOT_KEEP_DAYS of history per user so the table can't grow without bound.
"""
import asyncio
from datetime import datetime, timezone, timedelta

from db import connect
from market import prices

SNAPSHOT_CHECK_INTERVAL = 3600
SNAPSHOT_KEEP_DAYS = 90


async def _user_net_worth(db, guild_id, user_id):
    async with db.execute(
        "SELECT balance FROM accounts WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    nw = float(row["balance"])
    async with db.execute(
        "SELECT p.yes_shares, p.no_shares, m.yes_shares AS my, m.no_shares AS mn, "
        "m.liquidity, m.payout FROM positions p JOIN markets m ON p.market_id = m.market_id "
        "WHERE p.guild_id = ? AND p.user_id = ? AND m.status = 'open' "
        "AND (p.yes_shares > 0 OR p.no_shares > 0)", (guild_id, user_id)
    ) as cur:
        for p in await cur.fetchall():
            py, pn = prices(p["my"], p["mn"], p["liquidity"])
            nw += (p["yes_shares"] * py + p["no_shares"] * pn) * p["payout"]
    return nw


async def update_user_snapshot(db, guild_id, user_id):
    """Upsert today's snapshot for one user. Caller commits. Used after a trade."""
    nw = await _user_net_worth(db, guild_id, user_id)
    if nw is None:
        return
    today = datetime.now(timezone.utc).date().isoformat()
    await db.execute(
        "INSERT OR REPLACE INTO snapshots (guild_id, user_id, snap_date, net_worth) "
        "VALUES (?, ?, ?, ?)", (guild_id, user_id, today, nw))


async def snapshot_once():
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    cutoff = (now - timedelta(days=SNAPSHOT_KEEP_DAYS)).date().isoformat()
    async with connect() as db:
        async with db.execute("SELECT guild_id FROM servers") as cur:
            guilds = [r["guild_id"] for r in await cur.fetchall()]
        for gid in guilds:
            async with db.execute(
                "SELECT user_id FROM accounts WHERE guild_id = ?", (gid,)
            ) as cur:
                uids = [r["user_id"] for r in await cur.fetchall()]
            for uid in uids:
                await update_user_snapshot(db, gid, uid)
        await db.execute("DELETE FROM snapshots WHERE snap_date < ?", (cutoff,))
        await db.commit()
        # Flush the WAL back into the main file so it can't grow unbounded.
        await db.execute("PRAGMA wal_checkpoint(TRUNCATE)")


async def snapshot_loop(bot):
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await snapshot_once()
        except Exception as e:
            print(f"[snapshots] error: {e}")
        await asyncio.sleep(SNAPSHOT_CHECK_INTERVAL)
