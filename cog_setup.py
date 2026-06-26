import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from db import connect
from config import (DEFAULT_CURRENCY, DEFAULT_BALANCE, DEFAULT_SUBSIDY,
                    MAX_OPEN_MARKETS, TRADE_COOLDOWN_SECONDS, DAILY_TRADE_LIMIT)
from permissions import is_admin_or_owner


def build_guide(currency=DEFAULT_CURRENCY, balance=DEFAULT_BALANCE):
    embed = discord.Embed(
        color=discord.Color.from_rgb(87, 242, 135),
        description=(f"## Setup complete\nThis server is ready to go. Currency is "
                     f"`{currency}` and new accounts start with **{balance}**. "
                     f"Here is how to run everything."))
    embed.add_field(
        name="1. Let people join",
        value=("Everyone runs `/create` and picks a username to get their starting "
               "balance. If you turn referrals on, they can also name whoever invited "
               "them and that person earns a bonus."),
        inline=False)
    embed.add_field(
        name="2. Open a market (admin)",
        value=("`/settings create_market question:\"Will it rain Friday?\"` opens a "
               "YES/NO market. Optional `subsidy:` controls how steady the price is "
               "(higher = harder to swing, default 5000). Up to "
               f"{MAX_OPEN_MARKETS} markets can be open at once."),
        inline=False)
    embed.add_field(
        name="3. People trade",
        value=("`/buy <id> <yes|no> <amount>` buys shares with currency. "
               "`/sell <id> <yes|no> <amount>` cashes that many credits back out "
               "(blank amount sells the whole side). `/markets` lists everything, "
               "`/odds <id>` shows the price graph, `/portfolio` shows holdings and "
               "rank, `/leaderboard` ranks everyone. Limit: one trade per "
               f"{TRADE_COOLDOWN_SECONDS}s and {DAILY_TRADE_LIMIT} per day each."),
        inline=False)
    embed.add_field(
        name="4. Close and resolve (admin)",
        value=("`/settings close_market <id>` stops trading without paying out yet. "
               "`/settings resolve <id> <yes|no>` pays every winning share its payout "
               "and closes the market for good. Resolving is final, so double check the "
               "outcome."),
        inline=False)
    embed.add_field(
        name="Economy controls (admin)",
        value=("`/settings currency`, `/settings starting_balance`, "
               "`/settings share_payout` (markets start at half this), "
               "`/settings tax` (per-trade %), `/settings inflation` (free credits every "
               "N days), `/settings referral`, `/settings initial_subsidy`, "
               "`/settings grant @user <amount>` to give or take credits, and "
               "`/settings show` to view it all."),
        inline=False)
    embed.set_footer(text="You and any server admin can run admin commands. "
                          "Every command also works with ! instead of /. Try /commands anytime.")
    return embed


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
                        embed=build_guide(), ephemeral=True)
                    return
            await db.execute(
                "INSERT INTO servers (guild_id, currency_name, starting_balance, "
                "inflation_amount, inflation_days, initial_subsidy, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (gid, DEFAULT_CURRENCY, DEFAULT_BALANCE, 0, 7, DEFAULT_SUBSIDY,
                 datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()
        await interaction.response.send_message(embed=build_guide(), ephemeral=True)

    @app_commands.command(name="guide", description="Show the admin setup and command guide.")
    @app_commands.guild_only()
    async def guide(self, interaction: discord.Interaction):
        async with connect() as db:
            async with db.execute(
                "SELECT currency_name, starting_balance FROM servers WHERE guild_id = ?",
                (interaction.guild_id,)
            ) as cur:
                s = await cur.fetchone()
        if not s:
            await interaction.response.send_message(
                "Server isn't set up yet. Run `/setup`.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=build_guide(s["currency_name"], s["starting_balance"]), ephemeral=True)


async def setup(bot):
    await bot.add_cog(SetupCog(bot))
