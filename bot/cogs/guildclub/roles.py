import asyncio
import functools
from typing import Generic, NamedTuple, Type, TypeVar

import discord
from discord.ext import commands

from . import CSClub

T = TypeVar('T')


class RoleConfig(NamedTuple):
    id: int
    emoji: str | None = None
    label: str | None = None
    style: discord.ButtonStyle = discord.ButtonStyle.primary
    removed_emoji: str | None = None


class SectionRoleButton(discord.ui.Button['RoleView']):
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
                f'\N{BELL} Joined the {self.role.mention} role!',
                ephemeral=True
            )
        else:
            await interaction.user.remove_roles(self.role)
            await interaction.response.send_message(
                '\N{BELL WITH CANCELLATION STROKE} '
                f'Removed your {self.role.mention} role.',
                ephemeral=True
            )


class PronounRoleButton(SectionRoleButton):
    async def callback(self, interaction: discord.Interaction):
        if interaction.user._roles.get(self.role.id):
            await interaction.user.remove_roles(self.role)
            return await interaction.response.send_message(
                f'{self.config.removed_emoji} Removed your pronoun.',
                ephemeral=True
            )

        pronouns = frozenset(button.role.id for button in self.view.children)
        new_roles = [r for r in interaction.user.roles if r.id not in pronouns]

        if len(new_roles) < len(interaction.user.roles):
            # Replace the user's pronoun role
            new_roles.append(self.role)
            await interaction.user.edit(roles=new_roles)
            await interaction.response.send_message(
                f'{self.config.emoji} Changed your pronoun!',
                ephemeral=True
            )
        else:
            await interaction.user.add_roles(self.role)
            await interaction.response.send_message(
                f'{self.config.emoji} Added your pronoun!',
                ephemeral=True
            )


class RoleView(discord.ui.View, Generic[T]):
    """Handles adding and removing roles from users."""
    children: list[T]

    def __init__(
        self, guild: discord.Guild, roles: list[RoleConfig],
        *, button_cls: Type[T]
    ):
        super().__init__(timeout=None)

        for config in roles:
            role = guild.get_role(config.id)
            if role is not None:
                self.add_item(button_cls(role, config))
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
    SECTION_ROLES = [
        RoleConfig(914723299244777472, '\N{ICE CUBE}'),
        RoleConfig(914723216289857576, '\N{SCHOOL}'),
        RoleConfig(914723135163621386, '\N{PENGUIN}'),
        RoleConfig(914722982109249586, '\N{VIDEO GAME}'),
        RoleConfig(914723181108031529, '\N{MECHANICAL ARM}')
    ]
    SECTION_ROLES_CHANNEL_ID = 914726464157523969
    SECTION_ROLES_MESSAGE_ID = 914726715253723206

    PRONOUN_ROLES = [
        RoleConfig(914990720543236177, '\N{LARGE BLUE SQUARE}',
                   removed_emoji='\N{WHITE LARGE SQUARE}'),
        RoleConfig(914990706702053448, '\N{LARGE RED CIRCLE}',
                   removed_emoji='\N{MEDIUM WHITE CIRCLE}'),
        RoleConfig(914992495832739861, '\N{LARGE ORANGE DIAMOND}',
                   removed_emoji='\N{WHITE SMALL SQUARE}')
    ]
    PRONOUN_ROLES_CHANNEL_ID = SECTION_ROLES_CHANNEL_ID
    PRONOUN_ROLES_MESSAGE_ID = 914983602071171162

    def __init__(self, bot: commands.Bot, base: CSClub):
        self.bot = bot
        self.base = base

        self.section_view: RoleView[SectionRoleButton] | None = None
        self.pronoun_view: RoleView[PronounRoleButton] | None = None
        asyncio.create_task(self.start_listening_for_roles())

    @property
    def section_partial_message(self):
        return self.bot.get_partial_messageable(
            self.SECTION_ROLES_CHANNEL_ID,
            type=discord.ChannelType.text
        ).get_partial_message(self.SECTION_ROLES_MESSAGE_ID)

    @property
    def pronoun_partial_message(self):
        return self.bot.get_partial_messageable(
            self.PRONOUN_ROLES_CHANNEL_ID,
            type=discord.ChannelType.text
        ).get_partial_message(self.PRONOUN_ROLES_MESSAGE_ID)

    async def start_listening_for_roles(self):
        await self.bot.wait_until_ready()

        self.section_view = RoleView(self.base.guild, self.SECTION_ROLES,
                                     button_cls=SectionRoleButton)
        self.pronoun_view = RoleView(self.base.guild, self.PRONOUN_ROLES,
                                     button_cls=PronounRoleButton)

        self.bot.add_view(self.section_view, message_id=self.SECTION_ROLES_MESSAGE_ID)
        self.bot.add_view(self.pronoun_view, message_id=self.PRONOUN_ROLES_MESSAGE_ID)

    @commands.Cog.listener('on_guild_role_update')
    @locked_coroutine
    async def on_role_name_update(
            self, before: discord.Role, after: discord.Role):
        """Update the role view's buttons if one of the roles is renamed."""
        if before.guild.id != self.base.GUILD_ID:
            return

        views = [
            (self.section_view, self.section_partial_message),
            (self.pronoun_view, self.pronoun_partial_message)
        ]

        if None in views:
            return

        for view, message in views:
            button = discord.utils.get(view.children, role__id=before.id)
            if button is None:
                continue
            elif button.config.label is not None:
                return
            elif before.name == after.name:
                return

            button.label = after.name
            view.sort_buttons()
            await message.edit(view=view)
