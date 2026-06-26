import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from typing import Literal, Optional

from db import connect
from market import subsidy_to_b
from permissions import is_admin_or_owner
from config import MAX_OPEN_MARKETS


async def _server_exists(guild_id: int) -> bool:
    async with connect() as db:
        async with db.execute("SELECT 1 FROM servers WHERE guild_id = ?", (guild_id,)) as cur:
            return bool(await cur.fetchone())


class SettingsCog(commands.GroupCog, name="settings", description="Server admin settings"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message("Admin permission required.", ephemeral=True)
            return False
        if not await _server_exists(interaction.guild_id):
            await interaction.response.send_message(
                "Server isn't set up. Run `/setup` first.", ephemeral=True
            )
            return False
        return True

    @app_commands.command(name="show", description="Show this server's configuration.")
    @app_commands.guild_only()
    async def show(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        async with connect() as db:
            async with db.execute(
                "SELECT * FROM servers WHERE guild_id = ?", (interaction.guild_id,)
            ) as cur:
                s = await cur.fetchone()
            async with db.execute(
                "SELECT COUNT(*) AS n FROM markets WHERE guild_id = ? AND status = 'open'",
                (interaction.guild_id,),
            ) as cur:
                open_n = (await cur.fetchone())["n"]
        infl = (
            "off"
            if s["inflation_amount"] == 0
            else f"+{s['inflation_amount']} every {s['inflation_days']} day(s)"
        )
        embed = discord.Embed(color=discord.Color.from_rgb(88, 101, 242),
                              description="## Server settings")
        embed.add_field(name="Currency", value=s["currency_name"], inline=True)
        embed.add_field(name="Starting balance", value=str(s["starting_balance"]), inline=True)
        embed.add_field(name="Initial subsidy", value=str(s["initial_subsidy"]), inline=True)
        embed.add_field(name="Transaction tax", value=f"{s['tax_percent']}%", inline=True)
        embed.add_field(name="Referrals",
                        value=("on, bonus " + str(s["referral_bonus"])
                               if s["referral_enabled"] else "off"), inline=True)
        embed.add_field(name="Inflation", value=infl, inline=True)
        embed.add_field(name="Share payout",
                        value=f"{s['share_payout']} (start {s['share_payout'] // 2})", inline=True)
        embed.add_field(name="Open markets", value=str(open_n), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="currency", description="Rename the server currency.")
    @app_commands.guild_only()
    async def currency(self, interaction: discord.Interaction,
                       name: app_commands.Range[str, 1, 32]):
        if not await self._guard(interaction):
            return
        async with connect() as db:
            await db.execute(
                "UPDATE servers SET currency_name = ? WHERE guild_id = ?",
                (name, interaction.guild_id),
            )
            await db.commit()
        await interaction.response.send_message(f"Currency renamed to `{name}`.", ephemeral=True)

    @app_commands.command(name="starting_balance", description="Set starting balance for new accounts.")
    @app_commands.guild_only()
    async def starting_balance(self, interaction: discord.Interaction,
                               amount: app_commands.Range[int, 0, 1_000_000_000]):
        if not await self._guard(interaction):
            return
        async with connect() as db:
            await db.execute(
                "UPDATE servers SET starting_balance = ? WHERE guild_id = ?",
                (amount, interaction.guild_id),
            )
            await db.commit()
        await interaction.response.send_message(
            f"Starting balance set to `{amount}`.", ephemeral=True
        )

    @app_commands.command(name="initial_subsidy", description="Set the default subsidy used to seed new markets.")
    @app_commands.guild_only()
    async def initial_subsidy(self, interaction: discord.Interaction,
                              amount: app_commands.Range[int, 1, 1_000_000_000]):
        if not await self._guard(interaction):
            return
        async with connect() as db:
            await db.execute(
                "UPDATE servers SET initial_subsidy = ? WHERE guild_id = ?",
                (amount, interaction.guild_id),
            )
            await db.commit()
        await interaction.response.send_message(
            f"Initial subsidy set to `{amount}`. Higher = lower volatility "
            f"(prices move less per trade).",
            ephemeral=True,
        )

    @app_commands.command(name="tax", description="Set the transaction tax on trades (percent, 0 disables).")
    @app_commands.guild_only()
    async def tax(self, interaction: discord.Interaction,
                  percent: app_commands.Range[float, 0, 50]):
        if not await self._guard(interaction):
            return
        async with connect() as db:
            await db.execute(
                "UPDATE servers SET tax_percent = ? WHERE guild_id = ?",
                (percent, interaction.guild_id),
            )
            await db.commit()
        msg = (
            "Transaction tax disabled."
            if percent == 0
            else f"Transaction tax set to `{percent}%` of each trade."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="referral", description="Enable referral bonuses and set the amount.")
    @app_commands.describe(enabled="Turn referral bonuses on or off",
                           bonus="Credits the referrer earns per new signup")
    @app_commands.guild_only()
    async def referral(self, interaction: discord.Interaction, enabled: bool,
                       bonus: app_commands.Range[int, 0, 1_000_000_000] = 500):
        if not await self._guard(interaction):
            return
        async with connect() as db:
            await db.execute(
                "UPDATE servers SET referral_enabled = ?, referral_bonus = ? WHERE guild_id = ?",
                (1 if enabled else 0, bonus, interaction.guild_id))
            await db.commit()
        msg = (f"Referrals **enabled**. Referrers earn `{bonus}` per signup."
               if enabled else "Referrals **disabled**.")
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="share_payout", description="Set what a winning share pays (new markets).")
    @app_commands.describe(amount="Credits a winning share pays; new markets start at half this")
    @app_commands.guild_only()
    async def share_payout(self, interaction: discord.Interaction,
                           amount: app_commands.Range[int, 2, 1_000_000_000]):
        if not await self._guard(interaction):
            return
        async with connect() as db:
            await db.execute(
                "UPDATE servers SET share_payout = ? WHERE guild_id = ?",
                (amount, interaction.guild_id))
            await db.commit()
        await interaction.response.send_message(
            f"Share payout set to `{amount}`. New markets will start at "
            f"`{amount // 2}`/share (winning payout is always 2x the start). "
            f"Existing markets keep their original payout.",
            ephemeral=True)

    @app_commands.command(name="inflation", description="Set automatic credit inflation. Amount=0 disables it.")
    @app_commands.guild_only()
    async def inflation(self, interaction: discord.Interaction,
                        amount: app_commands.Range[int, 0, 1_000_000_000],
                        days: app_commands.Range[int, 1, 365]):
        if not await self._guard(interaction):
            return
        async with connect() as db:
            await db.execute(
                "UPDATE servers SET inflation_amount = ?, inflation_days = ? WHERE guild_id = ?",
                (amount, days, interaction.guild_id),
            )
            await db.commit()
        msg = (
            "Inflation disabled."
            if amount == 0
            else f"Inflation set to +{amount} every {days} day(s)."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="create_market", description="Open a new YES/NO market.")
    @app_commands.describe(
        question="What is the market asking?",
        subsidy="Optional credit subsidy for this market (blank = server default)",
    )
    @app_commands.guild_only()
    async def create_market(
        self,
        interaction: discord.Interaction,
        question: app_commands.Range[str, 4, 256],
        subsidy: Optional[app_commands.Range[int, 1, 1_000_000_000]] = None,
    ):
        if not await self._guard(interaction):
            return
        async with connect() as db:
            async with db.execute(
                "SELECT COUNT(*) AS n FROM markets WHERE guild_id = ? AND status = 'open'",
                (interaction.guild_id,),
            ) as cur:
                open_n = (await cur.fetchone())["n"]
            if open_n >= MAX_OPEN_MARKETS:
                await interaction.response.send_message(
                    f"You already have {MAX_OPEN_MARKETS} open markets (the limit). "
                    f"Close or resolve one first with `/settings close_market` or "
                    f"`/settings resolve`.", ephemeral=True)
                return
            async with db.execute(
                "SELECT initial_subsidy, currency_name, share_payout FROM servers "
                "WHERE guild_id = ?", (interaction.guild_id,),
            ) as cur:
                srv = await cur.fetchone()
            sub = subsidy if subsidy is not None else srv["initial_subsidy"]
            payout = srv["share_payout"]
            b = subsidy_to_b(sub, payout)
            cur = await db.execute(
                "INSERT INTO markets (guild_id, question, status, liquidity, subsidy, "
                "payout, created_at) VALUES (?, ?, 'open', ?, ?, ?, ?)",
                (interaction.guild_id, question, b, sub, payout,
                 datetime.now(timezone.utc).isoformat()),
            )
            mid = cur.lastrowid
            await db.commit()
        await interaction.response.send_message(
            f"Opened market `#{mid}`: {question}\n"
            f"Subsidy: **{sub} {srv['currency_name']}**, starting price "
            f"**{payout // 2} {srv['currency_name']}/share**, winning shares pay "
            f"**{payout}**.",
            ephemeral=True,
        )

    @app_commands.command(name="close_market", description="Stop trading on a market (no payout yet).")
    @app_commands.guild_only()
    async def close_market(self, interaction: discord.Interaction, market_id: int):
        if not await self._guard(interaction):
            return
        async with connect() as db:
            async with db.execute(
                "SELECT status FROM markets WHERE market_id = ? AND guild_id = ?",
                (market_id, interaction.guild_id),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                await interaction.response.send_message("Market not found.", ephemeral=True)
                return
            if row["status"] != "open":
                await interaction.response.send_message(
                    f"Market is already `{row['status']}`.", ephemeral=True
                )
                return
            await db.execute(
                "UPDATE markets SET status = 'closed' WHERE market_id = ?", (market_id,)
            )
            await db.commit()
        await interaction.response.send_message(
            f"Market `#{market_id}` closed. Use `/settings resolve` to pay out winners.",
            ephemeral=True,
        )

    @app_commands.command(name="resolve", description="Resolve a market and pay out winners.")
    @app_commands.guild_only()
    async def resolve(self, interaction: discord.Interaction,
                      market_id: int, outcome: Literal["yes", "no"]):
        if not await self._guard(interaction):
            return
        now = datetime.now(timezone.utc).isoformat()
        async with connect() as db:
            async with db.execute(
                "SELECT status, payout FROM markets WHERE market_id = ? AND guild_id = ?",
                (market_id, interaction.guild_id),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                await interaction.response.send_message("Market not found.", ephemeral=True)
                return
            if row["status"] == "resolved":
                await interaction.response.send_message("Market already resolved.", ephemeral=True)
                return
            share_payout = row["payout"]
            col = "yes_shares" if outcome == "yes" else "no_shares"
            async with db.execute(
                f"SELECT user_id, {col} AS shares FROM positions "
                f"WHERE guild_id = ? AND market_id = ? AND {col} > 0",
                (interaction.guild_id, market_id),
            ) as cur:
                winners = await cur.fetchall()
            total_paid = 0
            paid_count = 0
            for w in winners:
                payout = int(round(w["shares"] * share_payout))
                if payout <= 0:
                    continue
                await db.execute(
                    "UPDATE accounts SET balance = balance + ? "
                    "WHERE guild_id = ? AND user_id = ?",
                    (payout, interaction.guild_id, w["user_id"]),
                )
                total_paid += payout
                paid_count += 1
            await db.execute(
                "UPDATE markets SET status = 'resolved', outcome = ?, resolved_at = ? "
                "WHERE market_id = ?",
                (outcome, now, market_id),
            )
            await db.commit()
        await interaction.response.send_message(
            f"Market `#{market_id}` resolved **{outcome.upper()}**. "
            f"Paid out **{total_paid}** to **{paid_count}** holder(s).",
            ephemeral=True,
        )

    @app_commands.command(name="grant", description="Give or take credits (negative to remove).")
    @app_commands.guild_only()
    async def grant(self, interaction: discord.Interaction,
                    user: discord.Member, amount: int):
        if not await self._guard(interaction):
            return
        async with connect() as db:
            async with db.execute(
                "SELECT balance FROM accounts WHERE guild_id = ? AND user_id = ?",
                (interaction.guild_id, user.id),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                await interaction.response.send_message(
                    f"{user.mention} has no account here.", ephemeral=True
                )
                return
            new_balance = max(0, row["balance"] + amount)
            actual = new_balance - row["balance"]
            await db.execute(
                "UPDATE accounts SET balance = ? WHERE guild_id = ? AND user_id = ?",
                (new_balance, interaction.guild_id, user.id),
            )
            await db.commit()
        verb = "Granted" if actual >= 0 else "Removed"
        prep = "to" if actual >= 0 else "from"
        await interaction.response.send_message(
            f"{verb} **{abs(actual)}** credits {prep} {user.mention}. "
            f"New balance: **{new_balance}**.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(SettingsCog(bot))
