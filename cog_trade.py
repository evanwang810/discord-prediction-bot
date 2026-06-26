import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from typing import Literal, Optional

from db import connect
from market import (shares_for_credits, credits_for_shares,
                    shares_for_target_credits, prices)
from config import TRADE_COOLDOWN_SECONDS, DAILY_TRADE_LIMIT
from views import ConfirmView
from snapshots import update_user_snapshot

GREEN = discord.Color.from_rgb(87, 242, 135)
BLURPLE = discord.Color.from_rgb(88, 101, 242)
GREY = discord.Color.from_rgb(148, 155, 164)


class TradeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _precheck(self, db, ctx, now):
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
                await ctx.send(f"Trade cooldown. Wait {wait}s before your next trade.",
                               ephemeral=True)
                return None
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        async with db.execute(
            "SELECT COUNT(*) AS c FROM trades WHERE guild_id = ? AND user_id = ? "
            "AND created_at >= ?", (gid, uid, day_start)
        ) as cur:
            used = (await cur.fetchone())["c"]
        if used >= DAILY_TRADE_LIMIT:
            await ctx.send(f"Daily trade limit reached ({DAILY_TRADE_LIMIT} per day). "
                           f"Try again tomorrow (UTC).", ephemeral=True)
            return None
        return acc

    async def _market(self, db, guild_id, market_id):
        async with db.execute(
            "SELECT status, liquidity, yes_shares, no_shares, payout "
            "FROM markets WHERE guild_id = ? AND market_id = ?", (guild_id, market_id)
        ) as cur:
            return await cur.fetchone()

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
            cur_name = acc["currency_name"]
            if acc["balance"] < amount:
                await ctx.send(f"Not enough {cur_name}. You have {acc['balance']}.",
                               ephemeral=True)
                return
            m = await self._market(db, gid, market_id)
            if not m or m["status"] != "open":
                await ctx.send("That market isn't open for trading.", ephemeral=True)
                return
            y, n, b, payout = m["yes_shares"], m["no_shares"], m["liquidity"], m["payout"]
            tax = int(amount * acc["tax_percent"] / 100)
            spend = amount - tax
            shares = shares_for_credits(y, n, b, outcome, float(spend), payout)
            if shares <= 0:
                await ctx.send("That amount is too small to buy any shares.", ephemeral=True)
                return

        max_gain = shares * payout - amount
        confirm = discord.Embed(color=GREY, description=(
            f"## Confirm buy\n"
            f"Buy **{shares:.2f}** {outcome.upper()} shares on `#{market_id}`?"))
        confirm.add_field(name="Cost", value=f"{amount} {cur_name}", inline=True)
        confirm.add_field(name="If it wins", value=f"+{max_gain:.0f} {cur_name}", inline=True)
        if tax > 0:
            confirm.add_field(name="Tax", value=f"{tax} {cur_name}", inline=True)
        confirm.set_footer(text="Final fill is at the live price when you confirm.")
        view = ConfirmView(uid)
        msg = await ctx.send(embed=confirm, view=view)
        await view.wait()
        if not view.value:
            note = "Cancelled." if view.value is False else "Confirmation timed out."
            await msg.edit(content=note, embed=None, view=None)
            return

        now = datetime.now(timezone.utc)
        async with connect() as db:
            async with db.execute(
                "SELECT a.balance, s.tax_percent FROM accounts a "
                "JOIN servers s ON a.guild_id = s.guild_id "
                "WHERE a.guild_id = ? AND a.user_id = ?", (gid, uid)
            ) as cur:
                a2 = await cur.fetchone()
            m = await self._market(db, gid, market_id)
            if not m or m["status"] != "open":
                await msg.edit(content="Market closed before you confirmed.",
                               embed=None, view=None)
                return
            if a2["balance"] < amount:
                await msg.edit(content="Your balance changed; not enough to cover this.",
                               embed=None, view=None)
                return
            y, n, b, payout = m["yes_shares"], m["no_shares"], m["liquidity"], m["payout"]
            tax = int(amount * a2["tax_percent"] / 100)
            spend = amount - tax
            shares = shares_for_credits(y, n, b, outcome, float(spend), payout)
            new_y = y + shares if outcome == "yes" else y
            new_n = n + shares if outcome == "no" else n
            now_iso = now.isoformat()
            await db.execute("UPDATE accounts SET balance = balance - ?, last_trade_at = ? "
                             "WHERE guild_id = ? AND user_id = ?", (amount, now_iso, gid, uid))
            await db.execute("UPDATE markets SET yes_shares = ?, no_shares = ? "
                             "WHERE guild_id = ? AND market_id = ?", (new_y, new_n, gid, market_id))
            await db.execute(
                "INSERT INTO positions (guild_id, user_id, market_id, yes_shares, no_shares) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(guild_id, user_id, market_id) DO UPDATE SET "
                "yes_shares = yes_shares + excluded.yes_shares, "
                "no_shares = no_shares + excluded.no_shares",
                (gid, uid, market_id, shares if outcome == "yes" else 0.0,
                 shares if outcome == "no" else 0.0))
            p_yes, p_no = prices(new_y, new_n, b)
            await db.execute(
                "INSERT INTO trades (guild_id, user_id, market_id, outcome, shares, cost, "
                "kind, price_at_trade, price_after, tax_paid, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'buy', ?, ?, ?, ?)",
                (gid, uid, market_id, outcome, shares, amount,
                 p_yes if outcome == "yes" else p_no, p_yes, tax, now_iso))
            await update_user_snapshot(db, gid, uid)
            await db.commit()

        result = discord.Embed(color=GREEN, description=(
            f"## Bought {outcome.upper()} on #{market_id}\n"
            f"{ctx.author.mention} bought **{shares:.2f}** shares for **{amount} {cur_name}**."))
        result.add_field(name="Avg price", value=f"{spend/shares:.2f} {cur_name}", inline=True)
        result.add_field(name="New odds", value=f"YES {p_yes*100:.0f}% / NO {p_no*100:.0f}%",
                         inline=True)
        result.add_field(name="Pays per win", value=f"{payout} {cur_name}", inline=True)
        await msg.edit(content=None, embed=result, view=None)

    @commands.hybrid_command(name="sell", description="Sell a position for a currency amount.")
    @app_commands.describe(market_id="ID of the market (see /markets)",
                           outcome="Which side to sell",
                           amount="Currency to cash out (leave blank to sell the whole side)")
    @commands.guild_only()
    async def sell(self, ctx: commands.Context, market_id: int,
                   outcome: Literal["yes", "no"],
                   amount: Optional[commands.Range[int, 1, 1_000_000_000]] = None):
        gid, uid = ctx.guild.id, ctx.author.id
        now = datetime.now(timezone.utc)
        async with connect() as db:
            acc = await self._precheck(db, ctx, now)
            if acc is None:
                return
            cur_name = acc["currency_name"]
            m = await self._market(db, gid, market_id)
            if not m or m["status"] != "open":
                await ctx.send("That market isn't open for trading.", ephemeral=True)
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
            y, n, b, payout = m["yes_shares"], m["no_shares"], m["liquidity"], m["payout"]
            if amount is None:
                sell_shares = held
            else:
                sell_shares = shares_for_target_credits(y, n, b, outcome, float(amount),
                                                         payout, held)
            gross = credits_for_shares(y, n, b, outcome, sell_shares, payout)
            tax = int(gross * acc["tax_percent"] / 100)
            net = int(round(gross - tax))
            if sell_shares <= 0 or net <= 0:
                await ctx.send("That position isn't worth anything right now.", ephemeral=True)
                return

        confirm = discord.Embed(color=GREY, description=(
            f"## Confirm sell\n"
            f"Cash out **{net} {cur_name}** from your {outcome.upper()} position "
            f"on `#{market_id}`?"))
        confirm.add_field(name="Shares sold", value=f"{sell_shares:.2f}", inline=True)
        if tax > 0:
            confirm.add_field(name="Tax", value=f"{tax} {cur_name}", inline=True)
        confirm.set_footer(text="Final amount is at the live price when you confirm.")
        view = ConfirmView(uid)
        msg = await ctx.send(embed=confirm, view=view)
        await view.wait()
        if not view.value:
            note = "Cancelled." if view.value is False else "Confirmation timed out."
            await msg.edit(content=note, embed=None, view=None)
            return

        now = datetime.now(timezone.utc)
        async with connect() as db:
            async with db.execute(
                "SELECT tax_percent FROM servers WHERE guild_id = ?", (gid,)
            ) as cur:
                tax_pct = (await cur.fetchone())["tax_percent"]
            m = await self._market(db, gid, market_id)
            if not m or m["status"] != "open":
                await msg.edit(content="Market closed before you confirmed.",
                               embed=None, view=None)
                return
            async with db.execute(
                "SELECT yes_shares, no_shares FROM positions "
                "WHERE guild_id = ? AND user_id = ? AND market_id = ?", (gid, uid, market_id)
            ) as cur:
                pos = await cur.fetchone()
            held = (pos["yes_shares"] if outcome == "yes" else pos["no_shares"]) if pos else 0.0
            if held <= 0:
                await msg.edit(content="You no longer hold those shares.", embed=None, view=None)
                return
            y, n, b, payout = m["yes_shares"], m["no_shares"], m["liquidity"], m["payout"]
            if amount is None:
                sell_shares = held
            else:
                sell_shares = min(held, shares_for_target_credits(
                    y, n, b, outcome, float(amount), payout, held))
            gross = credits_for_shares(y, n, b, outcome, sell_shares, payout)
            tax = int(gross * tax_pct / 100)
            net = int(round(gross - tax))
            new_y = max(0.0, y - sell_shares) if outcome == "yes" else y
            new_n = max(0.0, n - sell_shares) if outcome == "no" else n
            now_iso = now.isoformat()
            await db.execute("UPDATE accounts SET balance = balance + ?, last_trade_at = ? "
                             "WHERE guild_id = ? AND user_id = ?", (net, now_iso, gid, uid))
            await db.execute("UPDATE markets SET yes_shares = ?, no_shares = ? "
                             "WHERE guild_id = ? AND market_id = ?", (new_y, new_n, gid, market_id))
            await db.execute(
                "UPDATE positions SET yes_shares = yes_shares - ?, no_shares = no_shares - ? "
                "WHERE guild_id = ? AND user_id = ? AND market_id = ?",
                (sell_shares if outcome == "yes" else 0.0,
                 sell_shares if outcome == "no" else 0.0, gid, uid, market_id))
            p_yes, p_no = prices(new_y, new_n, b)
            await db.execute(
                "INSERT INTO trades (guild_id, user_id, market_id, outcome, shares, cost, "
                "kind, price_at_trade, price_after, tax_paid, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'sell', ?, ?, ?, ?)",
                (gid, uid, market_id, outcome, sell_shares, net,
                 p_yes if outcome == "yes" else p_no, p_yes, tax, now_iso))
            await update_user_snapshot(db, gid, uid)
            await db.commit()

        result = discord.Embed(color=BLURPLE, description=(
            f"## Sold {outcome.upper()} on #{market_id}\n"
            f"{ctx.author.mention} cashed out **{net} {cur_name}** "
            f"({sell_shares:.2f} shares sold)."))
        result.add_field(name="New odds", value=f"YES {p_yes*100:.0f}% / NO {p_no*100:.0f}%",
                         inline=True)
        if tax > 0:
            result.add_field(name="Tax", value=f"{tax} {cur_name}", inline=True)
        await msg.edit(content=None, embed=result, view=None)


async def setup(bot):
    await bot.add_cog(TradeCog(bot))
