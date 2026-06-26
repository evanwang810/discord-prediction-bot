import asyncio
import discord
from discord.ext import commands

from config import TOKEN, SYNC_GUILD_IDS
from db import init_db
from inflation import inflation_loop
from snapshots import snapshot_loop

COGS = ["cog_setup", "cog_accounts", "cog_markets", "cog_trade", "cog_settings",
        "cog_info"]


class PredictionBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True          # member lookups for !transfer by name, etc.
        intents.message_content = True  # required for ! prefix commands
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        await init_db()
        for ext in COGS:
            await self.load_extension(ext)
            print(f"Loaded {ext}")
        if SYNC_GUILD_IDS:
            # Instant per-server sync. Clear remote globals so they don't show
            # up as duplicates alongside the guild copies.
            for gid in SYNC_GUILD_IDS:
                g = discord.Object(id=gid)
                self.tree.copy_global_to(guild=g)
                cmds = await self.tree.sync(guild=g)
                print(f"Synced {len(cmds)} commands to guild {gid}: "
                      f"{', '.join(sorted(c.name for c in cmds))}")
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
        else:
            cmds = await self.tree.sync()
            print(f"Synced {len(cmds)} global commands (can take up to 1h to appear): "
                  f"{', '.join(sorted(c.name for c in cmds))}")
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
