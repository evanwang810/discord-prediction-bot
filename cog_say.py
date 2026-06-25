import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from permissions import is_admin_or_owner


class SayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="say", description="Make the bot post a message.")
    @app_commands.describe(
        message="What the bot should say",
        channel="Channel to post in (defaults to the current one)",
    )
    @app_commands.guild_only()
    async def say(
        self,
        interaction: discord.Interaction,
        message: app_commands.Range[str, 1, 2000],
        channel: Optional[discord.TextChannel] = None,
    ):
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message(
                "Admin permission required.", ephemeral=True
            )
            return
        target = channel or interaction.channel
        perms = target.permissions_for(interaction.guild.me)
        if not perms.send_messages:
            await interaction.response.send_message(
                f"I don't have permission to send messages in {target.mention}.",
                ephemeral=True,
            )
            return
        # Suppress @everyone/@here so the command can't be used for mass pings.
        await target.send(
            message, allowed_mentions=discord.AllowedMentions(everyone=False)
        )
        await interaction.response.send_message(
            f"Sent to {target.mention}.", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(SayCog(bot))
