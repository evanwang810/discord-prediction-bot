import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from typing import Literal

from db import connect
from market import shares_for_credits, prices, SHARE_PAYOUT
from config import TRADE_COOLDOWN_SECONDS


class TradeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="trade", description="Buy YES or NO shares on a market.")
    @app_commands.describe(
        market_id="ID of the market (see /markets)",
        outcome="Which side to buy",
        amount="How much to spend in the server's currency",
    )
    @app_commands.guild_only()
    async def trade(
        self,
        interaction: discord.Interaction,
        market_id: int,
        outcome: Literal["yes", "no"],
        amount: app_commands.Range[int, 1, 1_000_000_000],
    ):
        gid, uid = interaction.guild_id, interaction.user.id
        now = datetime.now(timezone.utc)

        async with connect() as db:
            async with db.execute(
                "SELECT a.balance, a.last_trade_at, s.currency_name, s.tax_percent "
                "FROM accounts a JOIN servers s ON a.guild_id = s.guild_id "
                "WHERE a.guild_id = ? AND a.user_id = ?",
                (gid, uid),
            ) as cur:
                acc = await cur.fetchone()
            if not acc:
                await interaction.response.send_message(
                    "You don't have an account. Run `/create` first.", ephemeral=True
                )
                return

            if acc["last_trade_at"]:
                last = datetime.fromisoformat(acc["last_trade_at"])
                elapsed = (now - last).total_seconds()
                if elapsed < TRADE_COOLDOWN_SECONDS:
                    remaining = int(TRADE_COOLDOWN_SECONDS - elapsed)
                    m, s = divmod(remaining, 60)
                    await interaction.response.send_message(
                        f"Trade cooldown — wait **{m}m {s}s** before your next trade.",
                        ephemeral=True,
                    )
                    return

            if acc["balance"] < amount:
                await interaction.response.send_message(
                    f"Insufficient balance. You have {acc['balance']} {acc['currency_name']}.",
                    ephemeral=True,
                )
                return

            async with db.execute(
                "SELECT market_id, status, liquidity, yes_shares, no_shares "
                "FROM markets WHERE guild_id = ? AND market_id = ?",
                (gid, market_id),
            ) as cur:
                m = await cur.fetchone()
            if not m:
                await interaction.response.send_message("Market not found.", ephemeral=True)
                return
            if m["status"] != "open":
                await interaction.response.send_message(
                    "That market is not open for trading.", ephemeral=True
                )
                return

            y, n, b = m["yes_shares"], m["no_shares"], m["liquidity"]
            p_yes_before, p_no_before = prices(y, n, b)
            price_at = p_yes_before if outcome == "yes" else p_no_before

            tax = int(amount * acc["tax_percent"] / 100)
            spend = amount - tax
            if spend <= 0:
                await interaction.response.send_message(
                    "Amount is too small — the transaction tax would eat all of it.",
                    ephemeral=True,
                )
                return

            shares = shares_for_credits(y, n, b, outcome, float(spend))
            if shares <= 0:
                await interaction.response.send_message(
                    "That amount can't buy any shares at the current price.", ephemeral=True
                )
                return

            new_y = y + shares if outcome == "yes" else y
            new_n = n + shares if outcome == "no" else n

            now_iso = now.isoformat()
            await db.execute(
                "UPDATE accounts SET balance = balance - ?, last_trade_at = ? "
                "WHERE guild_id = ? AND user_id = ?",
                (amount, now_iso, gid, uid),
            )
            await db.execute(
                "UPDATE markets SET yes_shares = ?, no_shares = ? WHERE market_id = ?",
                (new_y, new_n, market_id),
            )
            await db.execute(
                "INSERT INTO positions (guild_id, user_id, market_id, yes_shares, no_shares) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(guild_id, user_id, market_id) DO UPDATE SET "
                "yes_shares = yes_shares + excluded.yes_shares, "
                "no_shares = no_shares + excluded.no_shares",
                (gid, uid, market_id,
                 shares if outcome == "yes" else 0.0,
                 shares if outcome == "no" else 0.0),
            )
            p_yes_after, p_no_after = prices(new_y, new_n, b)
            await db.execute(
                "INSERT INTO trades (guild_id, user_id, market_id, outcome, shares, cost, "
                "price_at_trade, price_after, tax_paid, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (gid, uid, market_id, outcome, shares, amount, price_at,
                 p_yes_after, tax, now_iso),
            )
            await db.commit()

        cur_name = acc["currency_name"]
        avg_price = spend / shares
        tax_line = f" (incl. **{tax} {cur_name}** tax)" if tax > 0 else ""
        await interaction.response.send_message(
            f"Bought **{shares:.2f}** {outcome.upper()} shares on `#{market_id}` for "
            f"**{amount} {cur_name}**{tax_line} (avg `{avg_price:.2f} {cur_name}/share`).\n"
            f"Implied price before: YES `{p_yes_before*100:.1f}%` / NO `{p_no_before*100:.1f}%`\n"
            f"Implied price after:  YES `{p_yes_after*100:.1f}%` / NO `{p_no_after*100:.1f}%`\n"
            f"Each winning share pays **{SHARE_PAYOUT} {cur_name}** on resolution.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(TradeCog(bot))
