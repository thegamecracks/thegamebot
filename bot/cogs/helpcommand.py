"""Reference: https://gist.github.com/Gobot1234/45cad24df63fc144e85a7f8c85812567"""
#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import collections
import math

import discord
from discord.ext import commands

from bot import utils
from bot.utils import paging
from main import Context, TheGameBot

_original_help_command: commands.HelpCommand | None = None
BOT_MAPPING = dict[commands.Cog | None, list[commands.Command]]
BOT_MAPPING_LIST = list[tuple[commands.Cog | None, list[commands.Command]]]
HELP_OBJECT = (
    BOT_MAPPING            # send_bot_help
    | commands.Cog | None  # send_cog_help
    | commands.Command     # send_group/command_help
)


class CommandPageSource(paging.PageSource[commands.Command, None, "HelpView"]):
    """Displays a command."""
    def __init__(self, command: commands.Command):
        super().__init__()
        self.command = command

    def get_page(self, index):
        return self.command

    def format_page(self, view: "HelpView", command: commands.Command):
        help_command = view.help_command
        ctx = help_command.context

        embed = discord.Embed(
            title=command.qualified_name,
            color=ctx.bot.get_bot_color(),
            description='`{signature}`\n{documentation}'.format(
                signature=help_command.get_command_signature(command),
                documentation=help_command.get_command_doc(command)
            )
        )

        cog = command.cog
        if hasattr(command, 'injected_cog'):
            cog = ctx.bot.get_cog(command.injected_cog)
        cog_name = help_command.get_cog_name(cog) if cog else 'No'
        embed.set_author(name=f'{cog_name} category')

        return embed


class CommandListPageSource(
    paging.ListPageSource[commands.Command, CommandPageSource, "HelpView"]
):
    """Displays a list of commands."""
    def __init__(
        self, *args,
        title: str = None,
        description: str = None,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.title = title
        self.description = description

    def get_page_options(self, view: "HelpView", page: list[commands.Command]):
        options = [
            paging.PageOption(
                label=cmd.qualified_name,
                description=utils.truncate_simple(cmd.short_doc, 100, placeholder='...'),
                source=(
                    GroupPageSource(cmd, page_size=HelpView.COMMANDS_PER_PAGE)
                    if isinstance(cmd, commands.Group) else CommandPageSource(cmd)
                )
            )
            for i, cmd in enumerate(page)
        ]

        return options

    def format_page(self, view: "HelpView", page: list[commands.Command]):
        ctx = view.help_command.context

        embed = discord.Embed(
            color=ctx.bot.get_bot_color(),
            description=self.description,
            title=self.title
        )

        if self.title and self.max_pages > 1:
            embed.title = '{} ({}/{})'.format(
                self.title,
                view.current_index + 1,
                self.max_pages
            )

        per_field = math.ceil(self.page_size / 3)
        groups = discord.utils.as_chunks(page, per_field)
        for group in groups:
            embed.add_field(
                name='\u200b',
                value='\n'.join([f'__{c.qualified_name}__' for c in group])
            )

        return embed


class CogPageSource(CommandListPageSource):
    """Displays a list of commands under a cog.

    If the cog is None, the `title` and `description` kwargs
    can be used to add those attributes in.

    """
    def __init__(
        self,
        cog: commands.Cog | None,
        *args,
        title: str = None,
        description: str = None,
        **kwargs
    ):
        title = title or getattr(cog, 'qualified_name', None)
        description = description or getattr(cog, 'description', None)
        super().__init__(
            *args,
            title=title,
            description=description,
            **kwargs
        )


class GroupPageSource(CommandListPageSource):
    """Displays a command group along with its subcommands."""
    def __init__(self, group: commands.Group, *args, **kwargs):
        super().__init__(
            list(group.commands),
            *args,
            title=group.qualified_name,
            **kwargs
        )
        self.command = group

    def format_page(self, view, page: list[commands.Command]):
        help_command = view.help_command
        if self.description is None:
            self.description = '`{signature}`\n{documentation}'.format(
                signature=help_command.get_command_signature(self.command),
                documentation=help_command.get_command_doc(self.command)
            )

        return super().format_page(view, page)


class BotPageSource(
    paging.ListPageSource[
        BOT_MAPPING_LIST,
        CogPageSource,
        "HelpView"
    ]
):
    """Displays the cogs and commands in each cog."""
    def __init__(self, mapping: BOT_MAPPING, *args, **kwargs):
        super().__init__(list(mapping.items()), *args, **kwargs)

    def get_page_options(self, view: "HelpView", page: BOT_MAPPING_LIST):
        options = []
        for i, (cog, cmds) in enumerate(page):
            # NOTE: in case cog is None,
            # name is explicitly passed to CogPageSource
            name = view.help_command.get_cog_name(cog)
            option = paging.PageOption(
                label=name,
                description=utils.truncate_message(
                    cog.description, 100, max_lines=1,
                    placeholder='...'
                ) if cog is not None else 'Uncategorized commands.',
                source=CogPageSource(
                    cog, cmds, title=name,
                    page_size=view.COMMANDS_PER_PAGE
                )
            )
            options.append(option)

        return options

    def format_page(self, view: "HelpView", page: BOT_MAPPING_LIST):
        help_command = view.help_command
        ctx = help_command.context

        description = []
        for cog, cmds in page:
            command_names = ' '.join([c.qualified_name for c in cmds])
            description.append(f'__**{help_command.get_cog_name(cog)}**__')
            description.append(utils.truncate_message(command_names, 70, placeholder='...'))

        embed = discord.Embed(
            title=ctx.me.name,
            color=ctx.bot.get_bot_color(),
            description='\n'.join(description)
        )

        if self.max_pages > 1:
            embed.title = '{} ({}/{})'.format(
                ctx.me.name,
                view.current_index + 1,
                self.max_pages
            )

        return embed


# NOTE: help objects are strongly referenced,
# preventing cleanup of reloaded cogs/commands
class HelpView(paging.PaginatorView):
    """A paginator for presenting cogs, commands, and command groups."""
    COGS_PER_PAGE = 5
    COMMANDS_PER_PAGE = 9
    TIMEOUT_MAX_EMBED_SIZE = 400

    def __init__(
        self, *args,
        help_command: "HelpCommand",
        **kwargs
    ):
        self.help_command = help_command
        super().__init__(*args, timeout=60, **kwargs)

    async def interaction_check(self, interaction):
        is_allowed = await super().interaction_check(interaction)
        if not is_allowed:
            user_id: int = tuple(self.allowed_users)[0]
            await interaction.response.send_message(
                f'This help message is for <@{user_id}>!',
                ephemeral=True
            )
        return is_allowed

    async def on_timeout(self):
        embed = self.page.get('embed')
        if embed and len(embed) > self.TIMEOUT_MAX_EMBED_SIZE:
            await self.message.delete()
        else:
            await self.message.edit(view=None)


class HelpCommand(commands.HelpCommand):
    context: Context

    def __init__(self):
        super().__init__(
            command_attrs={
                'help': 'Shows help about the bot, a command, or a category.',
                'max_concurrency': commands.MaxConcurrency(
                    1, per=commands.BucketType.user, wait=False)
            }
        )

    def get_bot_mapping(self) -> collections.OrderedDict[
        commands.Cog | None, list[commands.Command]
    ]:
        """Retrieves the bot mapping passed to :meth:`send_bot_help`.

        This performs a few extra modifications to the mapping:
            1. Cogs without commands are excluded
            2. Keys are sorted alphabetically
            3. Commands with the `injected_cog` attribute are reassigned
               to the specified cog.

        """
        bot = self.context.bot
        mapping = collections.OrderedDict()
        to_inject: list[tuple[commands.Command, str]] = []

        # Create usual mapping but pick out commands with `injected_cog`
        for cog in bot.cogs.values():
            cmds = []
            for c in cog.get_commands():
                injected_cog = getattr(c, 'injected_cog', None)
                if injected_cog:
                    to_inject.append((c, injected_cog))
                else:
                    cmds.append(c)
            mapping[cog] = cmds

        # Append injected commands to corresponding cogs
        for c, injected_cog in to_inject:
            cog = self.context.bot.get_cog(injected_cog)
            mapping[cog].append(c)

        # Remove empty cogs
        to_remove = [cog for cog, cmds in mapping.items() if not cmds]
        for cog in to_remove:
            del mapping[cog]

        # Re-order keys by name
        ordered_cogs = sorted(mapping.keys(), key=self.get_cog_name)
        for cog in ordered_cogs:
            mapping.move_to_end(cog)

        return mapping

    async def filter_bot_mapping(self, mapping: dict, *args, **kwargs) -> dict:
        """Filters the commands given by get_bot_mapping() and returns
        the mutated dict.
        """
        for cog, cmds in mapping.items():
            mapping[cog] = await self.filter_commands(cmds, *args, **kwargs)

        # Remove any newly empty cogs
        to_remove = [cog for cog, cmds in mapping.items() if not cmds]
        for cog in to_remove:
            del mapping[cog]

        return mapping

    @staticmethod
    def get_command_doc(command: commands.Command) -> str:
        return (
            command.help
            or command.short_doc
            or 'There is no description for this {}.'.format(
                'group' if isinstance(command, commands.Group) else 'command'
            )
        )

    @staticmethod
    def get_cog_name(cog: commands.Cog | None):
        return getattr(cog, 'qualified_name', 'No Category')

    def command_not_found(self, string):
        return 'No command called "{}" found.'.format(string)

    def subcommand_not_found(self, command, string):
        if isinstance(command, commands.Group) and len(command.all_commands) > 0:
            return 'Command "{}" has no subcommand named {}'.format(
                command.qualified_name, string)
        return 'Command "{}" has no subcommands.'.format(command.qualified_name)

    async def send_bot_help(self, obj: HELP_OBJECT):
        """Sends help when no arguments are given."""
        async def get_cog_source(cog: commands.Cog | None):
            cmds = mapping[cog]
            cmds = await self.filter_commands(cmds, sort=True)
            return CogPageSource(obj, cmds, page_size=HelpView.COMMANDS_PER_PAGE)

        def get_group_source(group: commands.Group):
            return GroupPageSource(group, page_size=HelpView.COMMANDS_PER_PAGE)

        mapping = obj if isinstance(obj, dict) else self.get_bot_mapping()
        sources = [BotPageSource(mapping, page_size=HelpView.COGS_PER_PAGE)]

        if isinstance(obj, (commands.Cog, type(None))):
            sources.append(await get_cog_source(obj))
        elif isinstance(obj, commands.Command):
            sources.append(await get_cog_source(obj.cog))

            for parent in reversed(obj.parents):
                sources.append(get_group_source(parent))

            if isinstance(obj, commands.Group):
                sources.append(get_group_source(obj))
            else:
                sources.append(CommandPageSource(obj))

        view = HelpView(
            sources=sources,
            help_command=self,
            allowed_users={self.context.author.id}
        )
        await view.start(self.get_destination())
        await view.wait()

    async def send_cog_help(self, cog: commands.Cog):
        """Sends help for a specific cog."""
        return await self.send_bot_help(cog)

    async def send_group_help(self, group: commands.Group):
        """Sends help for an individual group."""
        return await self.send_bot_help(group)

    async def send_command_help(self, command: commands.Command):
        """Sends help for an individual command."""
        return await self.send_bot_help(command)


async def setup(bot: TheGameBot):
    global _original_help_command
    _original_help_command = bot.help_command

    bot.help_command = HelpCommand()


async def teardown(bot: TheGameBot):
    bot.help_command = _original_help_command
