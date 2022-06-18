#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import collections
from typing import cast

import berconpy as rcon
import discord
from discord import app_commands
from discord.ext import commands, tasks

from . import SignalHill
from main import Context, TheGameBot


def filter_ascii(s: str):
    return ''.join(c for c in s if c.isascii())


class MessageTransformer(app_commands.Transformer):
    MAX_LENGTH = 140
    @classmethod
    async def transform(cls, interaction, value: str):
        bot = cast(TheGameBot, interaction.client)
        value = filter_ascii(value)

        if (over := len(value) - cls.MAX_LENGTH) > 0:
            raise app_commands.AppCommandError(
                'Your message is too long! Please shorten it by {} {}.'.format(
                    over, bot.inflector.plural('character', over)
                )
            )

        return value


MessageTransform = app_commands.Transform[str, MessageTransformer]


def in_telephone_channel():
    async def predicate(interaction: discord.Interaction):
        bot = cast(TheGameBot, interaction.client)
        settings = bot.get_settings()
        channel_id = settings.get('signal_hill', 'telephone_channel_id')

        if interaction.channel_id != channel_id:
            raise app_commands.AppCommandError(
                f'You must be in <#{channel_id}> to use this command!'
            )

        return True

    return app_commands.check(predicate)


def is_rcon_connected():
    async def predicate(interaction: discord.Interaction):
        bot = cast(TheGameBot, interaction.client)
        cog: SignalHill = bot.get_cog('SignalHill')

        if not cog.rcon_client.is_logged_in():
            raise app_commands.AppCommandError(
                'I am currently unable to communicate with the server '
                'at this time.'
            )

        return True

    return app_commands.check(predicate)


class _SignalHill_RCON(commands.GroupCog, name='signal-hill'):
    __discord_app_commands_default_guilds__ = [SignalHill.GUILD_ID]

    MESSAGE_LOG_SIZE = 10
    MESSAGE_LOG_UPDATE_RATE = 10

    def __init__(self, bot: TheGameBot, base: SignalHill):
        self.bot = bot
        self.base = base

        self.messages = collections.deque([], self.MESSAGE_LOG_SIZE)
        self.rcon_client.add_listener('on_player_message', self.log_player_message)

        self.update_log_loop.start()
        self.messages_has_updated = False

    def cog_unload(self):
        self.update_log_loop.cancel()

    @property
    def rcon_client(self):
        return self.base.rcon_client

    async def log_player_message(self, player: rcon.Player, channel: str, message: str):
        if channel not in ('Side', 'Group'):
            return

        message = discord.utils.escape_markdown(message)
        self.messages.append(f'`({channel}) {player.name}`: {message}')
        self.messages_has_updated = True

    @tasks.loop(seconds=MESSAGE_LOG_UPDATE_RATE)
    async def update_log_loop(self):
        if not self.messages_has_updated:
            return

        settings = self.bot.get_settings()
        channel_id = settings.get('signal_hill', 'telephone_channel_id')
        message_id = settings.get('signal_hill', 'telephone_message_id')

        channel = self.base.guild.get_channel(channel_id)
        message = channel.get_partial_message(message_id)

        now = discord.utils.utcnow()
        lines = [
            f"Last updated: {discord.utils.format_dt(now, 'R')}",
            ''
        ]
        lines.extend(self.messages)

        await message.edit(content='\n'.join(lines))
        self.messages_has_updated = False

    @app_commands.command()
    @app_commands.describe(
        message=f'Your message to send. Must be no longer than '
                f'{MessageTransformer.MAX_LENGTH} characters.'
    )
    @is_rcon_connected()
    @in_telephone_channel()
    @app_commands.checks.cooldown(2, 15)
    async def send(
        self, interaction: discord.Interaction, message: MessageTransform
    ):
        """Send a message to the Invade and Annex server."""
        name = filter_ascii(interaction.user.display_name)
        announcement = f'{name} (Telephone): {message}'
        logged_message = f'`(Telephone) {name}`: {message}'

        try:
            await self.rcon_client.send(announcement)
        except rcon.RCONCommandError:
            pass  # Let the interaction fail
        else:
            self.messages.append(logged_message)
            self.messages_has_updated = True

            await interaction.response.send_message(logged_message, ephemeral=True)
