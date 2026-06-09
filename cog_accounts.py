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
            f"Account `{uname}` created with **{srv['starting_balance']} {srv['currency_name']}**.",
            ephemeral=True,
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


async def setup(bot):
    await bot.add_cog(AccountsCog(bot))
