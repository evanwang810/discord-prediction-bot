import discord
from discord import app_commands
from discord.ext import commands

from db import connect
from market import market_cap
from networth import guild_net_worths
from config import TRADE_COOLDOWN_SECONDS, DAILY_TRADE_LIMIT

BLURPLE = discord.Color.from_rgb(88, 101, 242)

COMMANDS_HELP = [
    ("/setup", "Admin: initialize the bot on this server (run once)."),
    ("/create", "Create your account (optionally name who referred you)."),
    ("/markets", "List open prediction markets."),
    ("/odds", "Graph of a market's odds over time."),
    ("/buy", "Buy YES or NO shares on a market."),
    ("/sell", "Sell a position for a currency amount."),
    ("/transfer", "Send currency to another user."),
    ("/portfolio", "View positions, rank and graph (yours or someone's)."),
    ("/leaderboard", "Top 10 traders by net worth."),
    ("/data", "Server-wide economy statistics."),
    ("/info", "Bot and server information."),
    ("/commands", "Show this list."),
    ("/settings ...", "Admin: currency, balance, tax, referrals, markets, grants."),
]


class InfoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="commands", description="List all available commands.")
    @commands.guild_only()
    async def commands_(self, ctx: commands.Context):
        body = "\n".join(f"`{cmd}` {desc}" for cmd, desc in COMMANDS_HELP)
        embed = discord.Embed(color=BLURPLE, description=(
            "## Commands\nEvery command works as `/name` or `!name`.\n\n" + body))
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="info", description="Show bot and server info.")
    @commands.guild_only()
    async def info(self, ctx: commands.Context):
        gid = ctx.guild.id
        async with connect() as db:
            async with db.execute("SELECT * FROM servers WHERE guild_id = ?", (gid,)) as cur:
                s = await cur.fetchone()
            if not s:
                await ctx.send("Server isn't set up. Admin must run `/setup`.")
                return
            async with db.execute(
                "SELECT COUNT(*) AS n FROM accounts WHERE guild_id = ?", (gid,)
            ) as cur:
                accounts = (await cur.fetchone())["n"]
            async with db.execute(
                "SELECT "
                "(SELECT COUNT(*) FROM markets WHERE guild_id = ? AND status = 'open') AS open_n, "
                "(SELECT COUNT(*) FROM markets WHERE guild_id = ? AND status = 'resolved') AS res_n",
                (gid, gid)
            ) as cur:
                m = await cur.fetchone()
        embed = discord.Embed(color=BLURPLE, description=(
            "## Prediction Market Bot\n"
            "Binary YES/NO markets priced by an LMSR market maker. Buy shares on the "
            "outcome you believe, sell anytime, and winning shares cash out when an admin "
            "resolves the market."))
        embed.add_field(name="Currency", value=s["currency_name"], inline=True)
        embed.add_field(name="Starting balance", value=str(s["starting_balance"]), inline=True)
        embed.add_field(name="Winning share pays", value=str(s["share_payout"]), inline=True)
        embed.add_field(name="Accounts", value=str(accounts), inline=True)
        embed.add_field(name="Markets (open/resolved)",
                        value=f"{m['open_n']} / {m['res_n']}", inline=True)
        embed.add_field(name="Trade limits",
                        value=f"1 per {TRADE_COOLDOWN_SECONDS}s, {DAILY_TRADE_LIMIT}/day",
                        inline=True)
        embed.set_footer(text="Run /commands for the full list.")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="data", description="Server-wide economy statistics.")
    @commands.guild_only()
    async def data(self, ctx: commands.Context):
        gid = ctx.guild.id
        async with connect() as db:
            async with db.execute(
                "SELECT currency_name FROM servers WHERE guild_id = ?", (gid,)
            ) as cur:
                srv = await cur.fetchone()
            if not srv:
                await ctx.send("Server isn't set up.")
                return
            async with db.execute(
                "SELECT COUNT(*) AS accounts, COALESCE(SUM(balance), 0) AS credits "
                "FROM accounts WHERE guild_id = ?", (gid,)
            ) as cur:
                acc = await cur.fetchone()
            async with db.execute(
                "SELECT COUNT(*) AS n FROM trades WHERE guild_id = ?", (gid,)
            ) as cur:
                trades = (await cur.fetchone())["n"]
            async with db.execute(
                "SELECT yes_shares, no_shares, liquidity, payout FROM markets "
                "WHERE guild_id = ? AND status = 'open'", (gid,)
            ) as cur:
                open_markets = await cur.fetchall()
        invested = sum(market_cap(m["yes_shares"], m["no_shares"], m["liquidity"], m["payout"])
                       for m in open_markets)
        cur_name = srv["currency_name"]
        embed = discord.Embed(color=BLURPLE, description=f"## {ctx.guild.name} economy")
        embed.add_field(name="Accounts", value=str(acc["accounts"]), inline=True)
        embed.add_field(name="Trades made", value=str(trades), inline=True)
        embed.add_field(name="Open markets", value=str(len(open_markets)), inline=True)
        embed.add_field(name="In wallets", value=f"{acc['credits']:.0f} {cur_name}", inline=True)
        embed.add_field(name="Invested", value=f"{invested:.0f} {cur_name}", inline=True)
        embed.add_field(name="Total in circulation",
                        value=f"{acc['credits'] + invested:.0f} {cur_name}", inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="leaderboard", description="Top traders by net worth.")
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context):
        gid = ctx.guild.id
        async with connect() as db:
            async with db.execute(
                "SELECT currency_name FROM servers WHERE guild_id = ?", (gid,)
            ) as cur:
                srv = await cur.fetchone()
            if not srv:
                await ctx.send("Server isn't set up.")
                return
            async with db.execute(
                "SELECT user_id, username, balance FROM accounts WHERE guild_id = ?", (gid,)
            ) as cur:
                accounts = {a["user_id"]: a for a in await cur.fetchall()}
            if not accounts:
                await ctx.send("No accounts yet.")
                return
            async with db.execute(
                "SELECT t.user_id, "
                "COUNT(*) FILTER (WHERE m.outcome = t.outcome AND t.kind = 'buy') AS wins, "
                "COUNT(*) FILTER (WHERE m.status = 'resolved' AND t.kind = 'buy') AS total "
                "FROM trades t JOIN markets m ON t.market_id = m.market_id "
                "WHERE t.guild_id = ? GROUP BY t.user_id", (gid,)
            ) as cur:
                stats = {r["user_id"]: (r["wins"], r["total"]) for r in await cur.fetchall()}
            net_map = await guild_net_worths(db, gid)

        ranked = sorted(net_map.items(), key=lambda kv: -kv[1])[:10]
        cur_name = srv["currency_name"]
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for i, (uid, worth) in enumerate(ranked, start=1):
            a = accounts.get(uid)
            if not a:
                continue
            wins, total = stats.get(uid, (0, 0))
            wr = f"{wins*100/total:.0f}%" if total > 0 else "no record"
            rank = medals.get(i, f"`{i:>2}.`")
            lines.append(f"{rank} **{a['username']}**  `{worth:.0f} {cur_name}`  "
                         f"(win rate {wr})")
        embed = discord.Embed(color=BLURPLE, description=(
            "## Leaderboard\nNet worth = balance plus open positions at market price.\n\n"
            + "\n".join(lines)))
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(InfoCog(bot))
