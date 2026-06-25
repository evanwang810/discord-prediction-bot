import asyncio
import discord
from discord.ext import commands

from config import TOKEN
from db import init_db
from inflation import inflation_loop
from snapshots import snapshot_loop

COGS = ["cog_setup", "cog_accounts", "cog_markets", "cog_trade", "cog_settings",
        "cog_info", "cog_say"]


class PredictionBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await init_db()
        for ext in COGS:
            await self.load_extension(ext)
        await self.tree.sync()
        self._bg_tasks = [
            asyncio.create_task(inflation_loop(self)),
            asyncio.create_task(snapshot_loop(self)),
        ]

    async def on_ready(self):
        print(f"Logged in as {self.user} ({self.user.id})")


def main():
    if not TOKEN:
        raise SystemExit(
            "DISCORD_BOT_TOKEN is not set. Put it in a .env file or your environment."
        )
    PredictionBot().run(TOKEN)


if __name__ == "__main__":
    main()
