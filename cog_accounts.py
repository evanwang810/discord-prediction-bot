import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from db import connect


class CreateModal(discord.ui.Modal, title="Create Account"):
    username = discord.ui.TextInput(
        label="Username",
        min_length=2,
        max_length=32,
        required=True,
        placeholder="Your trader display name",
    )

    async def on_submit(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        uid = interaction.user.id
        uname = str(self.username).strip()
        async with connect() as db:
            async with db.execute(
                "SELECT starting_balance, currency_name FROM servers WHERE guild_id = ?", (gid,)
            ) as cur:
                srv = await cur.fetchone()
            if not srv:
                await interaction.response.send_message(
                    "This server isn't set up yet. An admin must run `/setup`.", ephemeral=True
                )
                return
            async with db.execute(
                "SELECT 1 FROM accounts WHERE guild_id = ? AND user_id = ?", (gid, uid)
            ) as cur:
                if await cur.fetchone():
                    await interaction.response.send_message(
                        "You already have an account on this server.", ephemeral=True
                    )
                    return
            async with db.execute(
                "SELECT 1 FROM accounts WHERE guild_id = ? AND username = ?", (gid, uname)
            ) as cur:
                if await cur.fetchone():
                    await interaction.response.send_message(
                        "That username is taken.", ephemeral=True
                    )
                    return
            now = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "INSERT INTO accounts (guild_id, user_id, username, balance, "
                "last_inflation, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (gid, uid, uname, srv["starting_balance"], now, now),
            )
            await db.commit()
        await interaction.response.send_message(
            f"{interaction.user.mention} joined as `{uname}` with "
            f"**{srv['starting_balance']} {srv['currency_name']}**."
        )


class AccountsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="create", description="Create your prediction market account.")
    @app_commands.guild_only()
    async def create(self, interaction: discord.Interaction):
        async with connect() as db:
            async with db.execute(
                "SELECT 1 FROM servers WHERE guild_id = ?", (interaction.guild_id,)
            ) as cur:
                if not await cur.fetchone():
                    await interaction.response.send_message(
                        "This server isn't set up yet. An admin must run `/setup`.", ephemeral=True
                    )
                    return
        await interaction.response.send_modal(CreateModal())

    @app_commands.command(name="transfer", description="Send currency to another user.")
    @app_commands.describe(user="Recipient", amount="How much to send")
    @app_commands.guild_only()
    async def transfer(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        amount: app_commands.Range[int, 1, 1_000_000_000],
    ):
        gid, uid = interaction.guild_id, interaction.user.id
        if user.id == uid:
            await interaction.response.send_message(
                "You can't transfer to yourself.", ephemeral=True
            )
            return
        if user.bot:
            await interaction.response.send_message(
                "Bots don't have accounts.", ephemeral=True
            )
            return
        async with connect() as db:
            async with db.execute(
                "SELECT a.balance, s.currency_name FROM accounts a "
                "JOIN servers s ON a.guild_id = s.guild_id "
                "WHERE a.guild_id = ? AND a.user_id = ?",
                (gid, uid),
            ) as cur:
                sender = await cur.fetchone()
            if not sender:
                await interaction.response.send_message(
                    "You don't have an account. Run `/create` first.", ephemeral=True
                )
                return
            if sender["balance"] < amount:
                await interaction.response.send_message(
                    f"Insufficient balance. You have {sender['balance']} "
                    f"{sender['currency_name']}.",
                    ephemeral=True,
                )
                return
            async with db.execute(
                "SELECT 1 FROM accounts WHERE guild_id = ? AND user_id = ?",
                (gid, user.id),
            ) as cur:
                if not await cur.fetchone():
                    await interaction.response.send_message(
                        f"{user.mention} doesn't have an account here.", ephemeral=True
                    )
                    return
            await db.execute(
                "UPDATE accounts SET balance = balance - ? WHERE guild_id = ? AND user_id = ?",
                (amount, gid, uid),
            )
            await db.execute(
                "UPDATE accounts SET balance = balance + ? WHERE guild_id = ? AND user_id = ?",
                (amount, gid, user.id),
            )
            await db.execute(
                "INSERT INTO transfers (guild_id, from_user, to_user, amount, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (gid, uid, user.id, amount, datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()
        await interaction.response.send_message(
            f"{interaction.user.mention} sent **{amount} {sender['currency_name']}** "
            f"to {user.mention}."
        )


async def setup(bot):
    await bot.add_cog(AccountsCog(bot))
