import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from typing import Optional

from db import connect


class AccountsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="create", description="Create your prediction market account.")
    @app_commands.describe(
        username="Your trader display name",
        referrer="(optional) the username of whoever referred you",
    )
    @commands.guild_only()
    async def create(self, ctx: commands.Context, username: str,
                     referrer: Optional[str] = None):
        gid, uid = ctx.guild.id, ctx.author.id
        username = username.strip()
        if not (2 <= len(username) <= 32):
            await ctx.send("Username must be 2–32 characters.", ephemeral=True)
            return
        async with connect() as db:
            async with db.execute(
                "SELECT starting_balance, currency_name, referral_enabled, referral_bonus "
                "FROM servers WHERE guild_id = ?", (gid,)
            ) as cur:
                srv = await cur.fetchone()
            if not srv:
                await ctx.send("This server isn't set up yet. An admin must run `/setup`.",
                               ephemeral=True)
                return
            async with db.execute(
                "SELECT 1 FROM accounts WHERE guild_id = ? AND user_id = ?", (gid, uid)
            ) as cur:
                if await cur.fetchone():
                    await ctx.send("You already have an account on this server.", ephemeral=True)
                    return
            async with db.execute(
                "SELECT 1 FROM accounts WHERE guild_id = ? AND username = ?", (gid, username)
            ) as cur:
                if await cur.fetchone():
                    await ctx.send("That username is taken.", ephemeral=True)
                    return

            referrer_id = None
            notes = []
            if referrer:
                if not srv["referral_enabled"]:
                    notes.append("Referrals are disabled on this server, so no bonus was given.")
                else:
                    async with db.execute(
                        "SELECT user_id FROM accounts WHERE guild_id = ? AND username = ?",
                        (gid, referrer.strip()),
                    ) as cur:
                        ref = await cur.fetchone()
                    if not ref:
                        notes.append(f"No trader named `{referrer.strip()}` was found.")
                    elif ref["user_id"] == uid:
                        notes.append("You can't refer yourself.")
                    else:
                        referrer_id = ref["user_id"]

            now = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "INSERT INTO accounts (guild_id, user_id, username, balance, "
                "last_inflation, referred_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (gid, uid, username, srv["starting_balance"], now, referrer_id, now),
            )
            if referrer_id is not None:
                await db.execute(
                    "UPDATE accounts SET balance = balance + ? WHERE guild_id = ? AND user_id = ?",
                    (srv["referral_bonus"], gid, referrer_id),
                )
                notes.append(f"`{referrer.strip()}` earned a **{srv['referral_bonus']} "
                             f"{srv['currency_name']}** referral bonus.")
            await db.commit()

        msg = (f"{ctx.author.mention} joined as `{username}` with "
               f"**{srv['starting_balance']} {srv['currency_name']}**.")
        if notes:
            msg += "\n" + "\n".join(notes)
        await ctx.send(msg)

    @commands.hybrid_command(name="transfer", description="Send currency to another user.")
    @app_commands.describe(user="Recipient", amount="How much to send")
    @commands.guild_only()
    async def transfer(self, ctx: commands.Context, user: discord.Member,
                       amount: commands.Range[int, 1, 1_000_000_000]):
        gid, uid = ctx.guild.id, ctx.author.id
        if user.id == uid:
            await ctx.send("You can't transfer to yourself.", ephemeral=True)
            return
        if user.bot:
            await ctx.send("Bots don't have accounts.", ephemeral=True)
            return
        async with connect() as db:
            async with db.execute(
                "SELECT a.balance, s.currency_name FROM accounts a "
                "JOIN servers s ON a.guild_id = s.guild_id "
                "WHERE a.guild_id = ? AND a.user_id = ?", (gid, uid)
            ) as cur:
                sender = await cur.fetchone()
            if not sender:
                await ctx.send("You don't have an account. Run `/create` first.", ephemeral=True)
                return
            if sender["balance"] < amount:
                await ctx.send(f"Insufficient balance. You have {sender['balance']} "
                               f"{sender['currency_name']}.", ephemeral=True)
                return
            async with db.execute(
                "SELECT 1 FROM accounts WHERE guild_id = ? AND user_id = ?", (gid, user.id)
            ) as cur:
                if not await cur.fetchone():
                    await ctx.send(f"{user.mention} doesn't have an account here.", ephemeral=True)
                    return
            await db.execute(
                "UPDATE accounts SET balance = balance - ? WHERE guild_id = ? AND user_id = ?",
                (amount, gid, uid))
            await db.execute(
                "UPDATE accounts SET balance = balance + ? WHERE guild_id = ? AND user_id = ?",
                (amount, gid, user.id))
            await db.execute(
                "INSERT INTO transfers (guild_id, from_user, to_user, amount, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (gid, uid, user.id, amount, datetime.now(timezone.utc).isoformat()))
            await db.commit()
        await ctx.send(f"{ctx.author.mention} sent **{amount} {sender['currency_name']}** "
                       f"to {user.mention}.")


async def setup(bot):
    await bot.add_cog(AccountsCog(bot))
