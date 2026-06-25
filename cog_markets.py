import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from typing import Optional

from db import connect
from charts import odds_chart, portfolio_chart
from market import prices, price_credits, market_cap, SHARE_PAYOUT
from networth import guild_net_worths


class MarketsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="markets", description="List open prediction markets.")
    @commands.guild_only()
    async def markets(self, ctx: commands.Context):
        gid = ctx.guild.id
        async with connect() as db:
            async with db.execute(
                "SELECT currency_name FROM servers WHERE guild_id = ?", (gid,)
            ) as cur:
                srv = await cur.fetchone()
            async with db.execute(
                "SELECT market_id, question, yes_shares, no_shares, liquidity "
                "FROM markets WHERE guild_id = ? AND status = 'open' ORDER BY market_id", (gid,)
            ) as cur:
                rows = await cur.fetchall()
        if not rows:
            await ctx.send("No open markets.")
            return
        cur_name = srv["currency_name"] if srv else "credits"
        lines = [f"**Open markets** — winning shares pay **{SHARE_PAYOUT} {cur_name}** each"]
        for r in rows:
            y_c, n_c = price_credits(r["yes_shares"], r["no_shares"], r["liquidity"])
            p_y, p_n = prices(r["yes_shares"], r["no_shares"], r["liquidity"])
            cap = market_cap(r["yes_shares"], r["no_shares"], r["liquidity"])
            lines.append(
                f"`#{r['market_id']}` {r['question']}\n"
                f"   YES `{y_c:.1f}` ({p_y*100:.1f}%)  /  NO `{n_c:.1f}` ({p_n*100:.1f}%)  "
                f"·  market cap `{cap:.0f} {cur_name}`")
        await ctx.send("\n".join(lines))

    @commands.hybrid_command(name="odds", description="Graph of a market's odds over time.")
    @app_commands.describe(market_id="ID of the market (see /markets)")
    @commands.guild_only()
    async def odds(self, ctx: commands.Context, market_id: int):
        gid = ctx.guild.id
        await ctx.defer()
        async with connect() as db:
            async with db.execute(
                "SELECT m.question, m.status, m.created_at, m.yes_shares, m.no_shares, "
                "m.liquidity, s.currency_name FROM markets m "
                "JOIN servers s ON m.guild_id = s.guild_id "
                "WHERE m.guild_id = ? AND m.market_id = ?", (gid, market_id)
            ) as cur:
                m = await cur.fetchone()
            if not m:
                await ctx.send("Market not found.")
                return
            async with db.execute(
                "SELECT created_at, price_after FROM trades "
                "WHERE guild_id = ? AND market_id = ? AND price_after IS NOT NULL "
                "ORDER BY trade_id", (gid, market_id)
            ) as cur:
                rows = await cur.fetchall()

        times = [datetime.fromisoformat(m["created_at"])]
        probs = [0.5]
        for r in rows:
            times.append(datetime.fromisoformat(r["created_at"]))
            probs.append(r["price_after"])
        if m["status"] == "open":
            py, _ = prices(m["yes_shares"], m["no_shares"], m["liquidity"])
            times.append(datetime.now(times[0].tzinfo))
            probs.append(py)
        cap = market_cap(m["yes_shares"], m["no_shares"], m["liquidity"])
        buf = odds_chart(times, probs, m["question"])
        await ctx.send(
            f"`#{market_id}` {m['question']} — **{len(rows)}** trade(s), "
            f"currently `{probs[-1]*100:.1f}%` YES · market cap "
            f"`{cap:.0f} {m['currency_name']}`",
            file=discord.File(buf, filename=f"odds_{market_id}.png"))

    @commands.hybrid_command(name="portfolio", description="View a portfolio, positions and rank.")
    @app_commands.describe(user="Whose portfolio to view (defaults to you)")
    @commands.guild_only()
    async def portfolio(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        gid = ctx.guild.id
        target = user or ctx.author
        tid = target.id
        await ctx.defer(ephemeral=(user is None))
        async with connect() as db:
            async with db.execute(
                "SELECT a.balance, a.username, s.currency_name "
                "FROM accounts a JOIN servers s ON a.guild_id = s.guild_id "
                "WHERE a.guild_id = ? AND a.user_id = ?", (gid, tid)
            ) as cur:
                acc = await cur.fetchone()
            if not acc:
                who = "You don't" if user is None else f"{target.mention} doesn't"
                await ctx.send(f"{who} have an account here.")
                return
            async with db.execute(
                "SELECT p.market_id, p.yes_shares, p.no_shares, m.question, m.status, "
                "m.outcome, m.yes_shares AS my, m.no_shares AS mn, m.liquidity "
                "FROM positions p JOIN markets m ON p.market_id = m.market_id "
                "WHERE p.guild_id = ? AND p.user_id = ? "
                "AND (p.yes_shares > 0 OR p.no_shares > 0) ORDER BY m.market_id", (gid, tid)
            ) as cur:
                positions = await cur.fetchall()
            async with db.execute(
                "SELECT "
                "COUNT(*) FILTER (WHERE m.outcome = t.outcome AND t.kind = 'buy') AS wins, "
                "COUNT(*) FILTER (WHERE m.status = 'resolved' AND t.kind = 'buy') AS total, "
                "COUNT(*) AS all_trades, "
                "COUNT(*) FILTER (WHERE t.created_at >= datetime('now', '-7 days')) AS recent "
                "FROM trades t JOIN markets m ON t.market_id = m.market_id "
                "WHERE t.guild_id = ? AND t.user_id = ?", (gid, tid)
            ) as cur:
                stats = await cur.fetchone()
            async with db.execute(
                "SELECT snap_date, net_worth FROM snapshots "
                "WHERE guild_id = ? AND user_id = ? ORDER BY snap_date", (gid, tid)
            ) as cur:
                snaps = await cur.fetchall()
            net_map = await guild_net_worths(db, gid)

        cur_name = acc["currency_name"]
        net = net_map.get(tid, float(acc["balance"]))
        ranking = sorted(net_map.items(), key=lambda kv: -kv[1])
        rank = next((i for i, (u, _) in enumerate(ranking, 1) if u == tid), None)
        rank_str = f"#{rank} of {len(ranking)}" if rank else "—"

        pos_lines = []
        for p in positions:
            bits = []
            if p["yes_shares"] > 0:
                bits.append(f"YES `{p['yes_shares']:.2f}`")
            if p["no_shares"] > 0:
                bits.append(f"NO `{p['no_shares']:.2f}`")
            tag = ""
            if p["status"] == "resolved":
                tag = f" *(resolved {p['outcome'].upper()})*"
            elif p["status"] == "closed":
                tag = " *(closed)*"
            pos_lines.append(f"`#{p['market_id']}` {p['question']}{tag} — {' / '.join(bits)}")

        wins, total = stats["wins"] or 0, stats["total"] or 0
        wr = f"{wins}/{total} ({wins*100/total:.0f}%)" if total > 0 else "—"
        lines = [
            f"**{acc['username']}** — rank **{rank_str}**",
            f"Net worth (incl. open positions at market price): **{net:.0f} {cur_name}**",
            f"Balance: **{acc['balance']} {cur_name}**",
            f"Total trades: **{stats['all_trades'] or 0}** "
            f"({stats['recent'] or 0} in the last 7 days)",
            f"Win rate on resolved trades: **{wr}**",
        ]
        if pos_lines:
            lines.append("")
            lines.append("**Positions:**")
            lines.extend(pos_lines)

        file = None
        if len(snaps) >= 2:
            dates = [datetime.fromisoformat(s["snap_date"]) for s in snaps]
            worths = [s["net_worth"] for s in snaps]
            buf = portfolio_chart(dates, worths, acc["username"], cur_name)
            file = discord.File(buf, filename="portfolio.png")
        else:
            lines.append("")
            lines.append("*Net worth graph appears after a couple of daily snapshots.*")

        if file:
            await ctx.send("\n".join(lines), file=file)
        else:
            await ctx.send("\n".join(lines))


async def setup(bot):
    await bot.add_cog(MarketsCog(bot))
