"""Reference: https://gist.github.com/Gobot1234/45cad24df63fc144e85a7f8c85812567"""
#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import collections
import functools
import math
from typing import Optional, Union

import discord
from discord.ext import commands

from bot import utils

_original_help_command: commands.HelpCommand | None = None
HELP_OBJECT = (
    dict[commands.Cog | None, commands.Command]  # send_bot_help
    | commands.Cog | None                        # send_cog_help
    | commands.Command                           # send_group/command_help
)


# NOTE: help objects are strongly referenced,
# preventing cleanup of reloaded cogs/commands
class HelpView(discord.ui.View):
    COGS_PER_PAGE = 5
    COMMANDS_PER_PAGE = 9

    def __init__(
        self, *,
        source: "PageSource",
        help_command: "HelpCommand",
        user_id: int,
        last_help: Union["HelpView", HELP_OBJECT] = discord.utils.MISSING,
        start_page: int = 0
    ):
        super().__init__(timeout=60)
        self.source: "PageSource" = source
        self.help_command = help_command
        self.user_id = user_id
        self.sub_help: Optional["HelpView"] = None
        if last_help is discord.utils.MISSING:
            last_help = self._get_last_help()
        self.last_help = last_help

        self.message: discord.Message | None = None
        self.current_page = -1
        self.embed = discord.Embed()
        self.options: list[discord.SelectOption] = []
        self.option_objects: list[HELP_OBJECT] = []

        self.can_paginate = True
        self.can_navigate = True

        if isinstance(source, BotPageSource):  # top-level bot help
            self.remove_item(self.back_source)  # type: ignore
            self.remove_item(self.stop_help)  # type: ignore
            self.stop_help.row = 1
            self.add_item(self.stop_help)  # type: ignore

        self.show_page(start_page)

    @classmethod
    async def get_page_source(
        cls, obj: HELP_OBJECT,
        help_command: "HelpCommand"
    ) -> "PageSource":
        if isinstance(obj, dict):
            return BotPageSource(
                await help_command.filter_bot_mapping(obj),
                per_page=cls.COGS_PER_PAGE
            )
        elif isinstance(obj, (commands.Cog, type(None))):
            mapping = help_command.get_bot_mapping()
            cmds = mapping.get(obj)

            if cmds is None:
                # Cog was either reloaded or unloaded;
                # try querying by name and fallback to BotPageSource
                if isinstance(obj, commands.Cog):
                    obj = help_command.context.bot.get_cog(type(obj).__name__)
                    cmds = mapping.get(obj)

                if cmds is None:
                    return await cls.get_page_source(mapping, help_command)

            cmds = await help_command.filter_commands(cmds, sort=True)
            return CogPageSource(obj, cmds, per_page=cls.COMMANDS_PER_PAGE)
        elif isinstance(obj, commands.Group):
            return GroupPageSource(obj, per_page=cls.COMMANDS_PER_PAGE)
        return CommandPageSource(obj)

    @functools.cached_property
    def _pagination_buttons(self) -> tuple[discord.ui.Button]:
        return self.first_page, self.prev_page, self.next_page, self.last_page  # type: ignore

    def _get_last_help(self) -> HELP_OBJECT:
        """Determine the help object that comes before self.source."""
        if isinstance(self.source, (CommandPageSource, GroupPageSource)):
            return self.source.command.parent or self.source.command.cog
        return self.help_command.get_bot_mapping()  # type: ignore

    def _get_message_kwargs(self) -> dict:
        return {'embed': self.embed, 'view': self}

    def _maybe_remove_item(self, item: discord.ui.Item):
        if item in self.children:
            self.remove_item(item)

    def _clear_navigation(self):
        if self.can_navigate:
            self.remove_item(self.navigate)  # type: ignore
            self.can_navigate = False

    def _update_navigation(self):
        if not self.can_navigate:
            self.add_item(self.navigate)  # type: ignore
            self.can_paginate = True

        self.navigate.options = self.options

    def _clear_pagination(self):
        if self.can_navigate:
            for button in self._pagination_buttons:
                self.remove_item(button)
            self.can_paginate = False

    def _update_pagination(self):
        if not self.can_paginate:
            for button in self._pagination_buttons:
                self.add_item(button)
            self.can_paginate = True

        # Disable/enable buttons if we're on the first/last page
        on_first_page = self.current_page == 0
        on_last_page = self.current_page == self.source.max_pages - 1
        self.first_page.disabled = on_first_page
        self.prev_page.disabled = on_first_page
        self.next_page.disabled = on_last_page
        self.last_page.disabled = on_last_page

    async def respond(self, interaction: discord.Interaction):
        await interaction.response.edit_message(**self._get_message_kwargs())

    def refresh_components(self):
        """Update the state of each component in this view based
        on the current source and page.
        """
        if self.source.max_pages > 1:
            self._update_pagination()
        else:
            self._clear_pagination()

        # NOTE: back_source is only updated during __init__

        if self.options:
            self._update_navigation()
        else:
            self._clear_navigation()

    def show_page(self, page_num: int):
        if page_num != self.current_page:
            self.current_page = page_num
            page = self.source.get_page(page_num)
            self.embed = self.source.format_page(self, page)
            self.options, self.option_objects = self.source.get_page_options(self, page)
            self.refresh_components()

    async def start(self, channel: discord.abc.Messageable | discord.Interaction):
        if isinstance(channel, discord.Interaction):
            # Continuing from a previous view
            await self.respond(channel)
            self.message = channel.message
        else:
            self.message = await channel.send(**self._get_message_kwargs())

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                'This is not your help message!',
                ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        if self.sub_help is None:
            await self.message.delete()

    @discord.ui.select(options=[], placeholder='Navigate...', row=0)
    async def navigate(self, select, interaction):
        index = int(select.values[0])
        obj = self.option_objects[index]

        self.sub_help = HelpView(
            source=await self.get_page_source(obj, self.help_command),
            help_command=self.help_command,
            user_id=self.user_id,
            last_help=self
        )
        await self.sub_help.start(interaction)

    @discord.ui.button(
        emoji='\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}',
        style=discord.ButtonStyle.blurple, row=1)
    async def first_page(self, button, interaction):
        self.show_page(0)
        await self.respond(interaction)

    @discord.ui.button(
        emoji='\N{BLACK LEFT-POINTING TRIANGLE}',
        style=discord.ButtonStyle.blurple, row=1)
    async def prev_page(self, button, interaction):
        self.show_page(self.current_page - 1)
        await self.respond(interaction)

    @discord.ui.button(
        emoji='\N{BLACK RIGHT-POINTING TRIANGLE}',
        style=discord.ButtonStyle.blurple, row=1)
    async def next_page(self, button, interaction):
        self.show_page(self.current_page + 1)
        await self.respond(interaction)

    @discord.ui.button(
        emoji='\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}',
        style=discord.ButtonStyle.blurple, row=1)
    async def last_page(self, button, interaction):
        self.show_page(self.source.max_pages - 1)
        await self.respond(interaction)

    @discord.ui.button(
        emoji='\N{LEFTWARDS ARROW WITH HOOK}',
        style=discord.ButtonStyle.blurple, row=2)
    async def back_source(self, button, interaction):
        self.stop()

        obj = self.last_help
        if isinstance(obj, HelpView):
            # Create copy of last_help in case it timed out
            view = HelpView(
                source=obj.source,
                help_command=obj.help_command,
                user_id=self.user_id,
                last_help=obj.last_help,
                start_page=obj.current_page
            )
        else:
            view = HelpView(
                source=await self.get_page_source(obj, self.help_command),
                help_command=self.help_command,
                user_id=self.user_id
            )
        await view.start(interaction)

    @discord.ui.button(
        emoji='\N{THUMBS UP SIGN}',
        style=discord.ButtonStyle.success, row=2)
    async def stop_help(self, button, interaction):
        self.stop()
        await interaction.message.delete()


class PageSource:
    def __init__(self, entries: list, *, per_page: int):
        self.entries = entries
        self.per_page = per_page

    def get_page(self, page_num: int) -> list:
        start = page_num * self.per_page
        return self.entries[start:start + self.per_page]

    @functools.cached_property
    def max_pages(self):
        pages, remainder = divmod(len(self.entries), self.per_page)
        return pages + bool(remainder)

    def get_page_options(
        self, menu: HelpView, page: list
    ) -> tuple[list[discord.SelectOption], list[HELP_OBJECT]]:
        raise NotImplementedError

    def format_page(self, menu: HelpView, page: list) -> discord.Embed:
        raise NotImplementedError


class BotPageSource(PageSource):
    def __init__(self, mapping: dict, *args, **kwargs):
        super().__init__(list(mapping.items()), *args, **kwargs)

    def get_page_options(
        self, menu,
        page: list[tuple[commands.Cog | None, list[commands.Command]]]
    ):
        options, objects = [], []
        for i, (cog, _) in enumerate(page):
            options.append(discord.SelectOption(
                label=menu.help_command.get_cog_name(cog),
                description=utils.truncate_message(
                    cog.description, 100, max_lines=1,
                    placeholder='...'
                ) if cog is not None else 'Uncategorized commands.',
                value=str(i)
            ))
            objects.append(cog)

        return options, objects

    def format_page(
        self, menu,
        page: list[tuple[commands.Cog | None, list[commands.Command]]]
    ):
        help_command = menu.help_command
        ctx = help_command.context

        description = []
        for cog, cmds in page:
            command_names = ' '.join([c.qualified_name for c in cmds])
            description.append(f'__**{help_command.get_cog_name(cog)}**__')
            description.append(utils.truncate_message(command_names, 70, placeholder='...'))

        embed = discord.Embed(
            title=ctx.me.display_name,
            color=utils.get_bot_color(ctx.bot),
            description='\n'.join(description)
        )
        if self.max_pages > 1:
            embed.title += f' ({menu.current_page + 1}/{self.max_pages})'

        return embed


class CommandListPageSource(PageSource):
    def get_page_options(self, menu, page: list[commands.Command]):
        options, objects = [], []
        for i, cmd in enumerate(page):
            options.append(discord.SelectOption(
                label=cmd.qualified_name,
                description=utils.truncate_simple(cmd.short_doc, 100, placeholder='...'),
                value=str(i)
            ))
            objects.append(cmd)

        return options, objects

    def format_page(self, menu, page: list[commands.Command]):
        ctx = menu.help_command.context

        embed = discord.Embed(
            color=utils.get_bot_color(ctx.bot)
        )

        per_field = math.ceil(self.per_page / 3)
        groups = discord.utils.as_chunks(page, per_field)
        for group in groups:
            embed.add_field(
                name='\u200b',
                value='\n'.join([str(c.qualified_name) for c in group])
            )

        return embed


class CogPageSource(CommandListPageSource):
    def __init__(self, cog: commands.Cog, cmds: list[commands.Command], *args, **kwargs):
        super().__init__(cmds, *args, **kwargs)
        self.cog = cog

    def format_page(self, menu, page: list[commands.Command]):
        embed = super().format_page(menu, page)

        embed.description = self.cog.description
        embed.title = self.cog.qualified_name
        if self.max_pages > 1:
            embed.title += f' ({menu.current_page + 1}/{self.max_pages})'

        return embed


class GroupPageSource(CommandListPageSource):
    def __init__(self, group: commands.Group, *args, **kwargs):
        super().__init__(list(group.commands), *args, **kwargs)
        self.command = group

    def format_page(self, menu, page: list[commands.Command]):
        help_command = menu.help_command
        embed = super().format_page(menu, page)

        embed.description = '`{signature}`\n{documentation}'.format(
            signature=help_command.get_command_signature(self.command),
            documentation=help_command.get_command_doc(self.command)
        )
        embed.title = self.command.qualified_name
        if self.max_pages > 1:
            embed.title += f' ({menu.current_page + 1}/{self.max_pages})'

        return embed


class CommandPageSource(PageSource):
    def __init__(self, command: commands.Command):
        super().__init__([command], per_page=1)
        self.command = command

    def get_page_options(self, menu, page):
        return [], []

    def format_page(self, menu, page: list[commands.Command]):
        help_command = menu.help_command
        ctx = help_command.context
        command = page[0]

        embed = discord.Embed(
            title=command.qualified_name,
            color=utils.get_bot_color(ctx.bot),
            description='`{signature}`\n{documentation}'.format(
                signature=help_command.get_command_signature(command),
                documentation=help_command.get_command_doc(command)
            )
        )

        # Show which cog the command is in if any
        cog = command.cog
        if hasattr(command, 'injected_cog'):
            cog = ctx.bot.get_cog(command.injected_cog)
        cog_name = help_command.get_cog_name(cog) if cog else 'No'
        embed.set_author(name=f'{cog_name} category')

        return embed


class HelpCommand(commands.HelpCommand):
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
        mapping, to_inject = collections.OrderedDict(), []

        # Create usual mapping but pick out commands with `injected_cog`
        for cog in bot.cogs.values():
            cmds = []
            for c in cog.get_commands():
                if hasattr(c, 'injected_cog'):
                    to_inject.append(c)
                else:
                    cmds.append(c)
            mapping[cog] = cmds

        # Append injected commands to corresponding cogs
        for c in to_inject:
            cog = self.context.bot.get_cog(c.injected_cog)
            mapping[cog].append(c)

        # Remove empty cogs
        to_remove = [cog for cog, cmds in mapping.items() if not cmds]
        for cog in to_remove:
            del mapping[cog]

        # Re-order keys by name
        ordered_cogs = sorted(mapping.keys(), key=lambda cog: self.get_cog_name(cog))
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

    def command_not_found(self, string: str) -> tuple[str, str]:
        return 'No command called "{}" found.'.format(string), string

    def subcommand_not_found(
        self, command: commands.Command, string: str
    ) -> tuple[str, str, commands.Command]:
        if isinstance(command, commands.Group) and len(command.all_commands) > 0:
            message = 'Command "{}" has no subcommand named {}'.format(
                command.qualified_name, string)
        else:
            message = 'Command "{}" has no subcommands.'.format(
                command.qualified_name)

        return message, string, command

    async def send_bot_help(self, mapping):
        """Sends help when no arguments are given."""
        view = HelpView(
            source=await HelpView.get_page_source(mapping, self),
            help_command=self,
            user_id=self.context.author.id
        )
        await view.start(self.get_destination())
        await view.wait()

    async def send_cog_help(self, cog):
        """Sends help for a specific cog."""
        return await self.send_bot_help(cog)

    async def send_group_help(self, group):
        """Sends help for an individual group."""
        return await self.send_bot_help(group)

    async def send_command_help(self, command):
        """Sends help for an individual command."""
        return await self.send_bot_help(command)


def setup(bot):
    global _original_help_command
    _original_help_command = bot.help_command

    bot.help_command = HelpCommand()
    bot.help_command.cog = bot.get_cog('Informative') or None


def teardown(bot):
    bot.help_command = help_command = _original_help_command
    if help_command is not None:
        help_command.cog = bot.get_cog('Informative') or None
