import asyncio
from datetime import datetime, timedelta, timezone
from db import connect
from config import INFLATION_CHECK_INTERVAL


async def apply_inflation_once():
    now = datetime.now(timezone.utc)
    async with connect() as db:
        async with db.execute(
            "SELECT guild_id, inflation_amount, inflation_days FROM servers WHERE inflation_amount > 0"
        ) as cur:
            servers = await cur.fetchall()
        for row in servers:
            cutoff = (now - timedelta(days=row["inflation_days"])).isoformat()
            await db.execute(
                "UPDATE accounts SET balance = balance + ?, last_inflation = ? "
                "WHERE guild_id = ? AND last_inflation < ?",
                (row["inflation_amount"], now.isoformat(), row["guild_id"], cutoff),
            )
        await db.commit()


async def inflation_loop(bot):
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await apply_inflation_once()
        except Exception as e:
            print(f"[inflation] error: {e}")
        await asyncio.sleep(INFLATION_CHECK_INTERVAL)
