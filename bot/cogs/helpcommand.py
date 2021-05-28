"""Reference: https://gist.github.com/Gobot1234/45cad24df63fc144e85a7f8c85812567"""
#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import collections
import math

import discord
from discord.ext import commands

from bot import utils

cooldown_message_length = commands.CooldownMapping.from_cooldown(
    1, 30, commands.BucketType.user)


class HelpCommand(commands.HelpCommand):

    help_categories_per_page = 9  # Max of 25 fields
    help_commands_per_category = 5

    help_cog_commands_per_page = 9  # Max of 25 fields

    help_message_length_threshold = 500
    # Maximum allowed characters in a help message before it is sent via DM

    no_category = 'No Category'

    def __init__(self):
        super().__init__(
            command_attrs={
                'help': 'Shows help about the bot, a command, or a category',
                'cooldown': commands.Cooldown(2, 3, commands.BucketType.user)
            }
        )

    def command_not_found(self, string):
        """A method called when a command is not found in the help command.

        Defaults to ``No command called {0} found.``

        Args:
            string (str):
                The string that contains the invalid command.
                Note that this has had mentions removed to prevent abuse.

        Returns:
            Tuple[str, str]:
                The error message to show, and the input that caused
                it.
        """
        return 'No command called "{}" found.'.format(string), string

    def subcommand_not_found(self, command, string):
        """A method called when a command did not have a subcommand
        requested in the help command.

        Defaults to either:
        - 'Command "{command.qualified_name}" has no subcommands.'
          If there is no subcommand in the ``command`` parameter.
        - 'Command "{command.qualified_name}" has no subcommand named {string}'
          If the `command` parameter has subcommands
          but not one named `string`.

        Args:
            command (commands.Command):
                The command that did not have the subcommand requested.
            string (str):
                The string that contains the invalid subcommand.
                Note that this has had mentions removed to prevent abuse.

        Returns:
            Tuple[str, str, commands.Command]:
                The error message to show,
                the input that caused it,
                and the command that doesn't have the requested subcommand.
        """
        if isinstance(command, commands.Group) and len(command.all_commands) > 0:
            message = 'Command "{}" has no subcommand named {}'.format(
                command.qualified_name, string)
        else:
            message = 'Command "{}" has no subcommands.'.format(
                command.qualified_name)

        return message, string, command

    async def send(self, content=None, *args, embed=None, **kwargs):
        """Send a message to the user, diverting it to DMs
        if the message is too long."""
        length = 0
        if content is not None:
            length += len(content)
        if embed is not None:
            length += len(embed)

        destination = self.get_destination()
        ctx = self.context

        if length >= self.help_message_length_threshold:
            # Too long; send in DMs
            await ctx.author.send(content, embed=embed, *args, **kwargs)

            if ctx.guild is not None:
                # User sent command in server; only give notification if they
                # haven't recently received one
                if not cooldown_message_length.update_rate_limit(ctx.message):
                    await destination.send(
                        'Help message is a bit long; sent it to you in DMs.',
                        delete_after=8
                    )
        else:
            await destination.send(content, embed=embed, *args, **kwargs)

    async def create_help_category_page(self, *, page_num):
        """Create an embed showing a page of categories."""
        categories: list = await self.get_commands()

        total_pages = math.ceil(
            len(categories) / self.help_categories_per_page)

        # Check if page num is valid
        if page_num not in range(1, total_pages + 1):
            if total_pages == 1:
                raise ValueError('Page number must be 1.')
            raise ValueError(
                f'Page number must be between 1 and {total_pages}.')

        embed = discord.Embed(
            title=f'Page {page_num}/{total_pages}',
            color=utils.get_bot_color(self.context.bot),
            description=(
                'Type {0}help [command] for more info on a command.\n'
                'You can also type {0}help [category] for '
                'more info on a category (do not type spaces in the '
                "category's name).".format(self.clean_prefix)
            )
        )

        # Create fields
        fields = []
        skip_to = self.help_categories_per_page * (page_num - 1)
        categories_to_add = self.help_categories_per_page
        for category, cmds in categories:
            if skip_to:
                skip_to -= 1
                continue
            if not categories_to_add:
                break

            # Create string listing commands
            field_text = []
            for i, com in enumerate(cmds, 1):
                if i == self.help_commands_per_category and len(cmds) != i:
                    # Too many commands to show
                    field_text.append('...')
                    break
                else:
                    field_text.append(com.qualified_name)
            field_text = '\n'.join(field_text)

            fields.append((self.get_cog_name(category), field_text))

            categories_to_add -= 1

        for field in fields:
            embed.add_field(name=field[0], value=field[1])

        return embed

    async def create_help_cog_page(self, cog, *, page_num):
        """Create an embed showing a page of commands in a cog."""
        cmds = await self.filter_commands(cog.get_commands(), sort=True)

        total_pages = math.ceil(len(cmds) / self.help_cog_commands_per_page)

        # Check if page num is valid
        if page_num not in range(1, total_pages + 1):
            if total_pages == 1:
                raise ValueError('Page number must be 1.')
            elif total_pages == 0:
                return discord.Embed(
                    title='Category help unavailable',
                    color=utils.get_bot_color(self.context.bot),
                    description=(
                        'This category exists, but you cannot access any '
                        'of its commands here.'
                    )
                )
            raise ValueError(
                f'Page number must be between 1 and {total_pages}.')

        embed = discord.Embed(
            title=f'{cog.qualified_name} - Page {page_num}/{total_pages}',
            color=utils.get_bot_color(self.context.bot),
            description=(
                f'{cog.description}\nType {self.clean_prefix}help [command] '
                'for more info on a command.'
            )
        )

        # Create fields
        fields = []
        skip_to = self.help_cog_commands_per_page * (page_num - 1)
        categories_to_add = self.help_cog_commands_per_page
        for com in cmds:
            if skip_to:
                skip_to -= 1
                continue
            if not categories_to_add:
                break

            fields.append(
                (com.qualified_name,
                 com.short_doc if com.short_doc else 'No description.')
            )

            categories_to_add -= 1

        for field in fields:
            embed.add_field(name=field[0], value=field[1])

        return embed

    def get_cog_name(self, cog):
        return getattr(cog, 'qualified_name', self.no_category)

    async def get_commands(self):
        """Return all sorted commands the bot has, categorized by sorted cogs.

        Returns:
            List[Optional[commands.Cog], List[commands.Command]]

        """
        categories = collections.defaultdict(list)

        for cmd in await self.filter_commands(self.context.bot.commands):
            categories[cmd.cog].append(cmd)

        # Create a paired list of of the dictionary
        categories_list = sorted(
            categories.items(),
            key=lambda x: self.get_cog_name(x[0])
        )

        # Sort each command by name
        for _, cmds in categories_list:
            cmds.sort(key=lambda x: x.qualified_name)

        return categories_list

    async def send_error_message(self, error):
        """Sends a help page if the user asks for a specific page.
        Otherwise, sends an error message.

        The result of `command_not_found` or
        `command_has_no_subcommand_found` will be passed here.

        Args:
            error (str):
                The error message to display to the user. Note that this has
                had mentions removed to prevent abuse.

        """
        destination = self.get_destination()

        error, string, *command = error
        command = command[0] if command else None

        try:
            # Try converting into a page number
            cog, page_num = None, int(string)
        except ValueError:
            try:
                # Get and try converting page number
                page_num = int(self.context.kwargs['command'].split()[1])
                cog = self.context.bot.get_cog(string)
            except (IndexError, ValueError):
                # Not a page number request
                return await self.send(error)

        if cog is None:
            # User requested a help page
            try:
                embed = await self.create_help_category_page(page_num=page_num)
            except ValueError as e:
                # Invalid page number
                await destination.send(str(e))
            else:
                await self.send(embed=embed)
        else:
            # User requested a cog help page
            try:
                embed = await self.create_help_cog_page(cog, page_num=page_num)
            except ValueError as e:
                # Invalid page number
                await destination.send(str(e))
            else:
                await self.send(embed=embed)

    async def send_bot_help(self, mapping):
        """Sends help when no arguments are given."""
        embed = await self.create_help_category_page(page_num=1)

        await self.send(embed=embed)

    async def send_cog_help(self, cog):
        """Sends help for a specific cog."""
        if all(c.hidden for c in cog.get_commands()):
            # Cog has no visible commands; pretend it doesn't exist
            ctx = self.context
            content = self.context.message.content.replace(
                ctx.prefix + ctx.invoked_with, '').strip()
            return await self.send_error_message(
                self.command_not_found(content))

        embed = await self.create_help_cog_page(cog, page_num=1)

        await self.send(embed=embed)

    async def send_group_help(self, group):
        """Sends help for an individual group.

        NOTE: Does not support groups containing over 25 commands.

        """
        embed = discord.Embed(
            title=self.get_command_signature(group),
            color=utils.get_bot_color(self.context.bot),
            description=group.help or group.short_doc
        )

        # Add fields
        for com in group.commands:
            embed.add_field(
                name=com.name,
                value=com.short_doc if com.short_doc else 'No description.'
            )

        await self.send(embed=embed)

    async def send_command_help(self, command):
        """Sends help for an individual command."""
        description = [f'`{self.get_command_signature(command)}`\n']

        if command.help:
            description.append(command.help)
        elif command.short_doc:
            description.append(command.short_doc)
        else:
            description.append('There is no description for this command.')

        embed = discord.Embed(
            title=command.qualified_name,
            color=utils.get_bot_color(self.context.bot),
            description=''.join(description)
        )
        if command.cog is not None:
            embed.set_author(
                name=f'In {self.get_cog_name(command.cog)} category')

        await self.send(embed=embed)


class HelpCommandCog(commands.Cog):
    qualified_name = 'Help Command'

    def __init__(self, bot):
        self.bot = bot
        self._original_help_command = bot.help_command

        bot.help_command = HelpCommand()
        bot.help_command.cog = bot.get_cog('Informative') or None

    def cog_unload(self):
        self.bot.help_command = help_command = self._original_help_command
        if help_command is not None:
            help_command.cog = self.bot.get_cog('Informative') or None


def setup(bot):
    bot.add_cog(HelpCommandCog(bot))
