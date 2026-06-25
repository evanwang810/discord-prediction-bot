import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from typing import Literal, Optional

from db import connect
from market import shares_for_credits, credits_for_shares, prices, SHARE_PAYOUT
from config import TRADE_COOLDOWN_SECONDS, DAILY_TRADE_LIMIT


class TradeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _precheck(self, db, ctx, now):
        """Fetch the caller's account; enforce cooldown and daily trade limit.

        Returns the account row, or None after replying with the reason.
        """
        gid, uid = ctx.guild.id, ctx.author.id
        async with db.execute(
            "SELECT a.balance, a.last_trade_at, s.currency_name, s.tax_percent "
            "FROM accounts a JOIN servers s ON a.guild_id = s.guild_id "
            "WHERE a.guild_id = ? AND a.user_id = ?", (gid, uid)
        ) as cur:
            acc = await cur.fetchone()
        if not acc:
            await ctx.send("You don't have an account. Run `/create` first.", ephemeral=True)
            return None
        if acc["last_trade_at"]:
            elapsed = (now - datetime.fromisoformat(acc["last_trade_at"])).total_seconds()
            if elapsed < TRADE_COOLDOWN_SECONDS:
                wait = int(TRADE_COOLDOWN_SECONDS - elapsed)
                await ctx.send(f"Trade cooldown — wait **{wait}s** before your next trade.",
                               ephemeral=True)
                return None
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        async with db.execute(
            "SELECT COUNT(*) AS c FROM trades WHERE guild_id = ? AND user_id = ? "
            "AND created_at >= ?", (gid, uid, day_start)
        ) as cur:
            used = (await cur.fetchone())["c"]
        if used >= DAILY_TRADE_LIMIT:
            await ctx.send(f"Daily trade limit reached (**{DAILY_TRADE_LIMIT}** per day). "
                           f"Try again tomorrow (UTC).", ephemeral=True)
            return None
        return acc

    async def _open_market(self, db, ctx, market_id):
        async with db.execute(
            "SELECT market_id, status, liquidity, yes_shares, no_shares "
            "FROM markets WHERE guild_id = ? AND market_id = ?", (ctx.guild.id, market_id)
        ) as cur:
            m = await cur.fetchone()
        if not m:
            await ctx.send("Market not found.", ephemeral=True)
            return None
        if m["status"] != "open":
            await ctx.send("That market is not open for trading.", ephemeral=True)
            return None
        return m

    @commands.hybrid_command(name="buy", description="Buy YES or NO shares on a market.")
    @app_commands.describe(market_id="ID of the market (see /markets)",
                           outcome="Which side to buy",
                           amount="How much to spend in the server's currency")
    @commands.guild_only()
    async def buy(self, ctx: commands.Context, market_id: int,
                  outcome: Literal["yes", "no"],
                  amount: commands.Range[int, 1, 1_000_000_000]):
        gid, uid = ctx.guild.id, ctx.author.id
        now = datetime.now(timezone.utc)
        async with connect() as db:
            acc = await self._precheck(db, ctx, now)
            if acc is None:
                return
            if acc["balance"] < amount:
                await ctx.send(f"Insufficient balance. You have {acc['balance']} "
                               f"{acc['currency_name']}.", ephemeral=True)
                return
            m = await self._open_market(db, ctx, market_id)
            if m is None:
                return

            y, n, b = m["yes_shares"], m["no_shares"], m["liquidity"]
            p_yes_before, p_no_before = prices(y, n, b)
            price_at = p_yes_before if outcome == "yes" else p_no_before
            tax = int(amount * acc["tax_percent"] / 100)
            spend = amount - tax
            if spend <= 0:
                await ctx.send("Amount is too small — the tax would eat all of it.",
                               ephemeral=True)
                return
            shares = shares_for_credits(y, n, b, outcome, float(spend))
            if shares <= 0:
                await ctx.send("That amount can't buy any shares at the current price.",
                               ephemeral=True)
                return

            new_y = y + shares if outcome == "yes" else y
            new_n = n + shares if outcome == "no" else n
            now_iso = now.isoformat()
            await db.execute(
                "UPDATE accounts SET balance = balance - ?, last_trade_at = ? "
                "WHERE guild_id = ? AND user_id = ?", (amount, now_iso, gid, uid))
            await db.execute(
                "UPDATE markets SET yes_shares = ?, no_shares = ? WHERE market_id = ?",
                (new_y, new_n, market_id))
            await db.execute(
                "INSERT INTO positions (guild_id, user_id, market_id, yes_shares, no_shares) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(guild_id, user_id, market_id) DO UPDATE SET "
                "yes_shares = yes_shares + excluded.yes_shares, "
                "no_shares = no_shares + excluded.no_shares",
                (gid, uid, market_id, shares if outcome == "yes" else 0.0,
                 shares if outcome == "no" else 0.0))
            p_yes_after, p_no_after = prices(new_y, new_n, b)
            await db.execute(
                "INSERT INTO trades (guild_id, user_id, market_id, outcome, shares, cost, "
                "kind, price_at_trade, price_after, tax_paid, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'buy', ?, ?, ?, ?)",
                (gid, uid, market_id, outcome, shares, amount, price_at, p_yes_after, tax, now_iso))
            await db.commit()

        cur_name = acc["currency_name"]
        tax_line = f" (incl. **{tax} {cur_name}** tax)" if tax > 0 else ""
        await ctx.send(
            f"{ctx.author.mention} bought **{shares:.2f}** {outcome.upper()} shares on "
            f"`#{market_id}` for **{amount} {cur_name}**{tax_line} "
            f"(avg `{spend/shares:.2f} {cur_name}/share`).\n"
            f"Implied price before: YES `{p_yes_before*100:.1f}%` / NO `{p_no_before*100:.1f}%`\n"
            f"Implied price after:  YES `{p_yes_after*100:.1f}%` / NO `{p_no_after*100:.1f}%`\n"
            f"Each winning share pays **{SHARE_PAYOUT} {cur_name}** on resolution.")

    @commands.hybrid_command(name="sell", description="Sell shares you hold back to the market.")
    @app_commands.describe(market_id="ID of the market (see /markets)",
                           outcome="Which side to sell",
                           shares="How many shares to sell (leave blank to sell all)")
    @commands.guild_only()
    async def sell(self, ctx: commands.Context, market_id: int,
                   outcome: Literal["yes", "no"],
                   shares: Optional[commands.Range[float, 0.0001, 1_000_000_000.0]] = None):
        gid, uid = ctx.guild.id, ctx.author.id
        now = datetime.now(timezone.utc)
        async with connect() as db:
            acc = await self._precheck(db, ctx, now)
            if acc is None:
                return
            m = await self._open_market(db, ctx, market_id)
            if m is None:
                return
            async with db.execute(
                "SELECT yes_shares, no_shares FROM positions "
                "WHERE guild_id = ? AND user_id = ? AND market_id = ?", (gid, uid, market_id)
            ) as cur:
                pos = await cur.fetchone()
            held = (pos["yes_shares"] if outcome == "yes" else pos["no_shares"]) if pos else 0.0
            if held <= 0:
                await ctx.send(f"You don't hold any {outcome.upper()} shares on `#{market_id}`.",
                               ephemeral=True)
                return
            sell_shares = held if shares is None else float(shares)
            if sell_shares > held + 1e-9:
                await ctx.send(f"You only hold **{held:.2f}** {outcome.upper()} shares.",
                               ephemeral=True)
                return
            sell_shares = min(sell_shares, held)

            y, n, b = m["yes_shares"], m["no_shares"], m["liquidity"]
            p_yes_before, p_no_before = prices(y, n, b)
            price_at = p_yes_before if outcome == "yes" else p_no_before
            gross = credits_for_shares(y, n, b, outcome, sell_shares)
            tax = int(gross * acc["tax_percent"] / 100)
            payout = int(round(gross - tax))
            if payout <= 0:
                await ctx.send("Those shares aren't worth anything at the current price.",
                               ephemeral=True)
                return

            new_y = max(0.0, y - sell_shares) if outcome == "yes" else y
            new_n = max(0.0, n - sell_shares) if outcome == "no" else n
            now_iso = now.isoformat()
            await db.execute(
                "UPDATE accounts SET balance = balance + ?, last_trade_at = ? "
                "WHERE guild_id = ? AND user_id = ?", (payout, now_iso, gid, uid))
            await db.execute(
                "UPDATE markets SET yes_shares = ?, no_shares = ? WHERE market_id = ?",
                (new_y, new_n, market_id))
            await db.execute(
                "UPDATE positions SET yes_shares = yes_shares - ?, no_shares = no_shares - ? "
                "WHERE guild_id = ? AND user_id = ? AND market_id = ?",
                (sell_shares if outcome == "yes" else 0.0,
                 sell_shares if outcome == "no" else 0.0, gid, uid, market_id))
            p_yes_after, p_no_after = prices(new_y, new_n, b)
            await db.execute(
                "INSERT INTO trades (guild_id, user_id, market_id, outcome, shares, cost, "
                "kind, price_at_trade, price_after, tax_paid, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'sell', ?, ?, ?, ?)",
                (gid, uid, market_id, outcome, sell_shares, payout, price_at,
                 p_yes_after, tax, now_iso))
            await db.commit()

        cur_name = acc["currency_name"]
        tax_line = f" (after **{tax} {cur_name}** tax)" if tax > 0 else ""
        await ctx.send(
            f"{ctx.author.mention} sold **{sell_shares:.2f}** {outcome.upper()} shares on "
            f"`#{market_id}` for **{payout} {cur_name}**{tax_line}.\n"
            f"Implied price before: YES `{p_yes_before*100:.1f}%` / NO `{p_no_before*100:.1f}%`\n"
            f"Implied price after:  YES `{p_yes_after*100:.1f}%` / NO `{p_no_after*100:.1f}%`")


async def setup(bot):
    await bot.add_cog(TradeCog(bot))
