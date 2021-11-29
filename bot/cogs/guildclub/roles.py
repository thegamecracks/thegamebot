import asyncio
import functools
from typing import NamedTuple

import discord
from discord.ext import commands

from . import CSClub


class RoleConfig(NamedTuple):
    id: int
    emoji: str | None = None
    label: str | None = None
    style: discord.ButtonStyle = discord.ButtonStyle.primary


class RoleButton(discord.ui.Button['RoleView']):
    """Adds or removes a particular role from a user."""
    def __init__(self, role: discord.Role, config: RoleConfig):
        super().__init__(
            custom_id=str(config.id),
            emoji=config.emoji,
            label=config.label or role.name,
            style=config.style
        )
        self.role = role
        self.config = config

    async def callback(self, interaction: discord.Interaction):
        # Optimized role check
        if not interaction.user._roles.get(self.role.id):
            await interaction.user.add_roles(self.role)
            await interaction.response.send_message(
                f'\N{BELL} Turned on notifications for {self.role.mention}!',
                ephemeral=True
            )
        else:
            await interaction.user.remove_roles(self.role)
            await interaction.response.send_message(
                '\N{BELL WITH CANCELLATION STROKE} Turned off '
                f'notifications for {self.role.mention}.',
                ephemeral=True
            )


class RoleView(discord.ui.View):
    """Handles adding and removing roles from users."""
    children: list[RoleButton]

    def __init__(self, guild: discord.Guild, roles: list[RoleConfig]):
        super().__init__(timeout=None)

        for config in roles:
            role = guild.get_role(config.id)
            if role is not None:
                self.add_item(RoleButton(role, config))
        self.sort_buttons()

    def sort_buttons(self):
        """Sort each role button by their label."""
        buttons = self.children.copy()
        buttons.sort(key=lambda b: b.label)

        for button in buttons:
            self.remove_item(button)

        for button in buttons:
            self.add_item(button)


def locked_coroutine(func):
    """Applies a lock onto a coroutine function."""
    lock = asyncio.Lock()

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        async with lock:
            return await func(*args, **kwargs)

    return wrapper


class _CSClub_Roles(commands.Cog):
    ROLES = [
        RoleConfig(914723299244777472, '\N{ICE CUBE}'),
        RoleConfig(914723216289857576, '\N{SCHOOL}'),
        RoleConfig(914723135163621386, '\N{PENGUIN}'),
        RoleConfig(914722982109249586, '\N{VIDEO GAME}'),
        RoleConfig(914723181108031529, '\N{MECHANICAL ARM}')
    ]
    ROLE_VIEW_CHANNEL_ID = 914726464157523969
    ROLE_VIEW_MESSAGE_ID = 914726715253723206

    def __init__(self, bot: commands.Bot, base: CSClub):
        self.bot = bot
        self.base = base

        self.role_view = RoleView(self.base.guild, self.ROLES)
        bot.add_view(self.role_view, message_id=self.ROLE_VIEW_MESSAGE_ID)

    @property
    def partial_role_message(self):
        return self.bot.get_partial_messageable(
            self.ROLE_VIEW_CHANNEL_ID,
            type=discord.ChannelType.text
        ).get_partial_message(self.ROLE_VIEW_MESSAGE_ID)

    @commands.Cog.listener('on_guild_role_update')
    @locked_coroutine
    async def on_role_name_update(
            self, before: discord.Role, after: discord.Role):
        """Update the role view's buttons if one of the roles is renamed."""
        button = discord.utils.get(self.role_view.children, role__id=before.id)
        if button is None:
            return
        elif before.name == after.name:
            return
        elif button.config.label is not None:
            return

        button.label = after.name
        self.role_view.sort_buttons()
        await self.partial_role_message.edit(view=self.role_view)
