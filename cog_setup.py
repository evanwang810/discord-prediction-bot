import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from db import connect
from config import DEFAULT_CURRENCY, DEFAULT_BALANCE, DEFAULT_SUBSIDY, OWNER_ID


def is_admin_or_owner(interaction: discord.Interaction) -> bool:
    if interaction.user.id == OWNER_ID:
        return True
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and perms.administrator)


class SetupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup", description="Initialize the prediction market bot on this server.")
    @app_commands.guild_only()
    async def setup(self, interaction: discord.Interaction):
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin permission required.", ephemeral=True)
            return
        gid = interaction.guild_id
        async with connect() as db:
            async with db.execute("SELECT 1 FROM servers WHERE guild_id = ?", (gid,)) as cur:
                if await cur.fetchone():
                    await interaction.response.send_message(
                        "This server is already set up. See `/settings show`.",
                        ephemeral=True,
                    )
                    return
            await db.execute(
                "INSERT INTO servers (guild_id, currency_name, starting_balance, "
                "inflation_amount, inflation_days, initial_subsidy, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (gid, DEFAULT_CURRENCY, DEFAULT_BALANCE, 0, 7, DEFAULT_SUBSIDY,
                 datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()
        await interaction.response.send_message(
            f"Bot initialized.\n"
            f"- Currency: `{DEFAULT_CURRENCY}`\n"
            f"- Starting balance: `{DEFAULT_BALANCE}`\n"
            f"- Initial market subsidy: `{DEFAULT_SUBSIDY}`\n"
            f"- Inflation: off\n\n"
            f"Users can now run `/create`. Admins manage everything via `/settings`.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(SetupCog(bot))
