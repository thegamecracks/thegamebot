"https://gist.github.com/Gobot1234/45cad24df63fc144e85a7f8c85812567"
import discord
from discord.ext import commands

from bot import settings


class HelpCommand(commands.HelpCommand):

    def __init__(self):
        super().__init__(
            command_attrs={
                # This is the command.help string
                'help': 'Shows help about the bot, a command, or a category',
                # this is a custom attribute passed to the help command
                'cooldown': commands.Cooldown(1, 3, commands.BucketType.user)
            }
        )

    # async def send_bot_help(self, mapping):
    # handles the invocation of help with no args

    # async def send_cog_help(self, cog):
    # sends help for a specific cog

    # async def send_group_help(self, group):
    # sends help for an individual group

    async def send_command_help(self, command):
        "Sends help for an individual command."
        channel = self.get_destination()

        description = f'`{self.get_command_signature(command)}`\n'

        if command.help is not None:
            description += f'```{command.help}```'
        elif command.short_doc is not None:
            description += f'```{command.short_doc}```'
        else:
            description += 'There is no description for this command.'

        embed = discord.Embed(
            title=command.name,
            color=int(settings.get_setting('bot_color'), 16),
            description=description
        )

        await channel.send(embed=embed)

    # def get_command_signature(command):
    # a method for retrieving the signature (the args) of a command
