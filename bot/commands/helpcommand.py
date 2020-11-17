"Reference: https://gist.github.com/Gobot1234/45cad24df63fc144e85a7f8c85812567"
import collections
import math

import discord
from discord.ext import commands

from bot import settings

get_bot_color = lambda: int(settings.get_setting('bot_color'), 16)


class HelpCommand(commands.HelpCommand):

    help_categories_per_page = 9  # Max of 25 fields
    help_commands_per_category = 5

    help_cog_commands_per_page = 9  # Max of 25 fields

    def __init__(self):
        super().__init__(
            command_attrs={
                # This is the command.help string
                'help': 'Shows help about the bot, a command, or a category',
                # this is a custom attribute passed to the help command
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
        if isinstance(command, Group) and len(command.all_commands) > 0:
            message = 'Command "{}" has no subcommand named {}'.format(
                command.qualified_name, string)
        else:
            message = 'Command "{}" has no subcommands.'.format(
                command.qualified_name)

        return message, string, command

    async def create_help_category_page(self, *, page_num):
        "Create an embed showing a page of categories."
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
            color=get_bot_color(),
            description=(
                'Type {0}help [command] for more info on a command.\n'
                'You can also type {0}help [category] for '
                'more info on a category.'.format(self.clean_prefix)
            )
        )

        # Create fields
        fields = []
        skip_to = self.help_categories_per_page * (page_num - 1)
        categories_to_add = self.help_categories_per_page
        for category, commands in categories:
            if skip_to:
                skip_to -= 1
                continue
            if not categories_to_add:
                break

            # Create string listing commands
            field_text = []
            for i, com in enumerate(commands, 1):
                if i == self.help_commands_per_category and len(commands) != i:
                    # Too many commands to show
                    field_text.append('...')
                    break
                else:
                    field_text.append(com.qualified_name)
            field_text = '\n'.join(field_text)

            fields.append((category.qualified_name, field_text))

            categories_to_add -= 1

        for field in fields:
            embed.add_field(name=field[0], value=field[1])

        return embed

    async def create_help_cog_page(self, cog, *, page_num):
        "Create an embed showing a page of commands in a cog."
        commands = await self.filter_commands(cog.get_commands(), sort=True)

        total_pages = math.ceil(
            len(commands) / self.help_cog_commands_per_page)

        # Check if page num is valid
        if page_num not in range(1, total_pages + 1):
            if total_pages == 1:
                raise ValueError('Page number must be 1.')
            elif total_pages == 0:
                # All commands in this cog are hidden
                return discord.Embed(
                    title='Category help unavailable',
                    color=get_bot_color(),
                    description=(
                        'This category exists, but you cannot access any '
                        'of its commands here.'
                    )
                )
            raise ValueError(
                f'Page number must be between 1 and {total_pages}.')

        embed = discord.Embed(
            title=f'{cog.qualified_name} - Page {page_num}/{total_pages}',
            color=get_bot_color(),
            description=(
                f'{cog.description}\nType {self.clean_prefix}help [command] '
                'for more info on a command.'
            )
        )

        # Create fields
        fields = []
        skip_to = self.help_cog_commands_per_page * (page_num - 1)
        categories_to_add = self.help_cog_commands_per_page
        for com in commands:
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

    async def get_commands(self):
        """Return all sorted commands the bot has categorized by sorted cogs.

        Returns:
            List[commands.Cog, List[commands.Command]]

        """
        categories = collections.defaultdict(list)

        for command in await self.filter_commands(self.context.bot.commands):
            categories[type(command.cog)].append(command)

        # Create a paired list of of the dictionary
        categories_list = sorted(
            categories.items(),
            key=lambda x: x[0].qualified_name
        )

        # Sort each command by name
        for _, commands in categories_list:
            commands.sort(key=lambda x: x.qualified_name)

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
                await destination.send(error)
                return

        if cog is None:
            # User requested a help page
            try:
                embed = await self.create_help_category_page(page_num=page_num)
            except ValueError as e:
                # Invalid page number
                await destination.send(str(e))
            else:
                await destination.send(embed=embed)
        else:
            # User requested a cog help page
            try:
                embed = await self.create_help_cog_page(cog, page_num=page_num)
            except ValueError as e:
                # Invalid page number
                await destination.send(str(e))
            else:
                await destination.send(embed=embed)

    async def send_bot_help(self, mapping):
        "Sends help when no arguments are given."
        destination = self.get_destination()

        embed = await self.create_help_category_page(page_num=1)

        await destination.send(embed=embed)

    async def send_cog_help(self, cog):
        "Sends help for a specific cog."
        destination = self.get_destination()

        embed = await self.create_help_cog_page(cog, page_num=1)

        await destination.send(embed=embed)

    async def send_group_help(self, group):
        """Sends help for an individual group.

        NOTE: Does not support groups containing over 25 commands.

        """
        destination = self.get_destination()

        embed = discord.Embed(
            title=self.get_command_signature(group),
            color=get_bot_color(),
            description=group.description
        )

        # Add fields
        for com in group.commands:
            embed.add_field(
                name=com.name,
                value=com.short_doc if com.short_doc else 'No description.'
            )

        await destination.send(embed=embed)

    async def send_command_help(self, command):
        "Sends help for an individual command."
        channel = self.get_destination()

        description = f'`{self.get_command_signature(command)}`\n'

        if command.help:
            description += f'```{command.help}```'
        elif command.short_doc:
            description += f'```{command.short_doc}```'
        else:
            description += 'There is no description for this command.'

        embed = discord.Embed(
            title=command.qualified_name,
            color=get_bot_color(),
            description=description
        )
        if command.cog is not None:
            embed.set_author(name=f'In {command.cog.qualified_name} category')

        await channel.send(embed=embed)
