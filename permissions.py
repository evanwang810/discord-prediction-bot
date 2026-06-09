import hashlib
import discord

from config import OWNER_ID_HASH


def is_owner(user_id: int) -> bool:
    return hashlib.sha256(str(user_id).encode()).hexdigest() == OWNER_ID_HASH


def is_admin_or_owner(interaction: discord.Interaction) -> bool:
    if is_owner(interaction.user.id):
        return True
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and perms.administrator)
