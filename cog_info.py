import discord
from discord import app_commands
from discord.ext import commands

from db import connect
from market import prices, SHARE_PAYOUT
from config import TRADE_COOLDOWN_SECONDS


COMMANDS_HELP = [
    ("/setup", "Admin — initialize the bot on this server (run once)."),
    ("/create", "Create your account with a starting balance."),
    ("/markets", "List open prediction markets."),
    ("/odds", "Graph of a market's odds over time."),
    ("/buy", "Buy YES or NO shares on a market."),
    ("/sell", "Sell shares you hold back to the market."),
    ("/transfer", "Send currency to another user."),
    ("/portfolio", "Your balance, positions, stats and net-worth graph."),
    ("/leaderboard", "Top 10 traders by net worth."),
    ("/info", "Bot and server information."),
    ("/commands", "Show this list."),
    ("/settings show", "Admin — show current server configuration."),
    ("/settings currency", "Admin — rename the currency."),
    ("/settings starting_balance", "Admin — set starting balance for new accounts."),
    ("/settings initial_subsidy", "Admin — default subsidy used to seed new markets."),
    ("/settings tax", "Admin — transaction tax on trades."),
    ("/settings inflation", "Admin — automatic credit inflation."),
    ("/settings create_market", "Admin — open a new YES/NO market."),
    ("/settings close_market", "Admin — stop trading on a market."),
    ("/settings resolve", "Admin — resolve a market and pay out winners."),
    ("/settings grant", "Admin — give or take credits from a user."),
]


class InfoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="commands", description="List all available commands.")
    @app_commands.guild_only()
    async def commands_(self, interaction: discord.Interaction):
        lines = ["**Commands**"]
        for cmd, desc in COMMANDS_HELP:
            lines.append(f"`{cmd}` — {desc}")
        await interaction.response.send_message("\n".join(lines))

    @app_commands.command(name="info", description="Show bot and server info.")
    @app_commands.guild_only()
    async def info(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        async with connect() as db:
            async with db.execute("SELECT * FROM servers WHERE guild_id = ?", (gid,)) as cur:
                s = await cur.fetchone()
            if not s:
                await interaction.response.send_message(
                    "Server isn't set up. Admin must run `/setup`."
                )
                return
            async with db.execute(
                "SELECT COUNT(*) AS n FROM accounts WHERE guild_id = ?", (gid,)
            ) as cur:
                accounts = (await cur.fetchone())["n"]
            async with db.execute(
                "SELECT "
                "(SELECT COUNT(*) FROM markets WHERE guild_id = ? AND status = 'open') AS open_n, "
                "(SELECT COUNT(*) FROM markets WHERE guild_id = ? AND status = 'resolved') AS res_n",
                (gid, gid),
            ) as cur:
                m = await cur.fetchone()
        cooldown_min = TRADE_COOLDOWN_SECONDS // 60
        await interaction.response.send_message(
            f"**Prediction Market Bot**\n"
            f"Binary YES/NO markets priced by an LMSR market maker. Each winning share pays "
            f"**{SHARE_PAYOUT} {s['currency_name']}**. Trades are rate-limited to one every "
            f"**{cooldown_min} minutes** per user.\n\n"
            f"**This server**\n"
            f"- Currency: `{s['currency_name']}`\n"
            f"- Starting balance: `{s['starting_balance']}`\n"
            f"- Default market subsidy: `{s['initial_subsidy']}`\n"
            f"- Accounts: `{accounts}`\n"
            f"- Markets open / resolved: `{m['open_n']}` / `{m['res_n']}`\n\n"
            f"Run `/commands` for the full command list.",
        )

    @app_commands.command(name="leaderboard", description="Top traders by net worth.")
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        async with connect() as db:
            async with db.execute(
                "SELECT currency_name FROM servers WHERE guild_id = ?", (gid,)
            ) as cur:
                srv = await cur.fetchone()
            if not srv:
                await interaction.response.send_message(
                    "Server isn't set up."
                )
                return
            async with db.execute(
                "SELECT user_id, username, balance FROM accounts WHERE guild_id = ?", (gid,)
            ) as cur:
                accounts = await cur.fetchall()
            async with db.execute(
                "SELECT p.user_id, p.yes_shares, p.no_shares, "
                "m.yes_shares AS my, m.no_shares AS mn, m.liquidity "
                "FROM positions p JOIN markets m ON p.market_id = m.market_id "
                "WHERE p.guild_id = ? AND m.status = 'open' "
                "AND (p.yes_shares > 0 OR p.no_shares > 0)",
                (gid,),
            ) as cur:
                positions = await cur.fetchall()
            async with db.execute(
                "SELECT t.user_id, "
                "COUNT(*) FILTER (WHERE m.outcome = t.outcome AND t.kind = 'buy') AS wins, "
                "COUNT(*) FILTER (WHERE m.status = 'resolved' AND t.kind = 'buy') AS total "
                "FROM trades t JOIN markets m ON t.market_id = m.market_id "
                "WHERE t.guild_id = ? GROUP BY t.user_id",
                (gid,),
            ) as cur:
                stats_rows = await cur.fetchall()

        if not accounts:
            await interaction.response.send_message("No accounts yet.")
            return

        stats = {r["user_id"]: (r["wins"], r["total"]) for r in stats_rows}
        net = {
            a["user_id"]: {
                "username": a["username"],
                "balance": a["balance"],
                "value": float(a["balance"]),
            }
            for a in accounts
        }
        for p in positions:
            entry = net.get(p["user_id"])
            if not entry:
                continue
            py, pn = prices(p["my"], p["mn"], p["liquidity"])
            entry["value"] += (p["yes_shares"] * py + p["no_shares"] * pn) * SHARE_PAYOUT

        ranked = sorted(net.items(), key=lambda kv: -kv[1]["value"])[:10]
        cur_name = srv["currency_name"]
        lines = ["**Leaderboard** — net worth (balance + open positions at market price)"]
        for i, (uid, info) in enumerate(ranked, start=1):
            wins, total = stats.get(uid, (0, 0))
            wr = f"{wins*100/total:.0f}%" if total > 0 else "—"
            lines.append(
                f"`{i:>2}.` **{info['username']}** — "
                f"`{info['value']:.0f} {cur_name}` "
                f"(balance {info['balance']}, win rate {wr})"
            )
        await interaction.response.send_message("\n".join(lines))


async def setup(bot):
    await bot.add_cog(InfoCog(bot))
