"""Daily net-worth snapshots powering the /portfolio graph."""
import asyncio
from datetime import datetime, timezone

from db import connect
from networth import guild_net_worths

SNAPSHOT_CHECK_INTERVAL = 3600


async def snapshot_once():
    today = datetime.now(timezone.utc).date().isoformat()
    async with connect() as db:
        async with db.execute("SELECT guild_id FROM servers") as cur:
            guilds = [r["guild_id"] for r in await cur.fetchall()]
        for gid in guilds:
            net = await guild_net_worths(db, gid)
            for uid, worth in net.items():
                await db.execute(
                    "INSERT OR REPLACE INTO snapshots (guild_id, user_id, snap_date, net_worth) "
                    "VALUES (?, ?, ?, ?)",
                    (gid, uid, today, worth),
                )
        await db.commit()


async def snapshot_loop(bot):
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await snapshot_once()
        except Exception as e:
            print(f"[snapshots] error: {e}")
        await asyncio.sleep(SNAPSHOT_CHECK_INTERVAL)
