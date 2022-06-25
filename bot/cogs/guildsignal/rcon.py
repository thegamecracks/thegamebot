#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import collections
from typing import cast
import unicodedata

import berconpy as rcon
import discord
from discord import app_commands
from discord.ext import commands, tasks

from . import SignalHill
from main import Context, TheGameBot


def filter_ascii(s: str):
    decomposed_bytes = unicodedata.normalize('NFKD', s).encode()
    return decomposed_bytes.decode('ascii', 'ignore')


def timestamp_now(style):
    return discord.utils.format_dt(discord.utils.utcnow(), style)


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


@app_commands.guilds(SignalHill.GUILD_ID)
class _SignalHill_RCON(commands.GroupCog, name='signal-hill'):
    MESSAGE_LOG_SIZE = 10
    MESSAGE_LOG_UPDATE_RATE = 10

    def __init__(self, bot: TheGameBot, base: SignalHill):
        self.bot = bot
        self.base = base

        settings = self.bot.get_settings()
        self.telephone_channel_id: int = settings.get('signal_hill', 'telephone_channel_id')
        self.telephone_message_id: int = settings.get('signal_hill', 'telephone_message_id')
        self.disconnect_emoji_id: int = settings.get('signal_hill', 'emoji_disconnect')

        self.messages = collections.deque([], self.MESSAGE_LOG_SIZE)
        self.messages_to_remove: list[int] = []
        self.message_cooldown = commands.CooldownMapping.from_cooldown(2, 10, commands.BucketType.user)
        self.rcon_client.add_listener('on_player_message', self.log_player_message)

        self.update_log_loop.start()
        self.messages_has_updated = False

    def cog_unload(self):
        self.update_log_loop.cancel()

    @property
    def rcon_client(self):
        return self.base.rcon_client

    @property
    def disconnect_emoji(self):
        return self.bot.get_emoji(self.disconnect_emoji_id)

    @property
    def telephone_partial_message(self) -> discord.PartialMessage:
        channel = self.base.guild.get_channel(self.telephone_channel_id)
        return channel.get_partial_message(self.telephone_message_id)

    async def send_rcon_message(self, name: str, message: str) -> str:
        """Sends a message from a user and returns the message that will
        be appended to the message log.

        :raises rcon.RCONCommandError:
            The message could not be sent to the server.

        """
        ts = timestamp_now('T')
        announcement = f'{name} (Telephone): {message}'
        logged_message = f'{ts} `(Telephone) {name}`: {message}'

        await self.rcon_client.send(announcement)

        self.messages.append(logged_message)
        self.messages_has_updated = True

        return logged_message

    @commands.Cog.listener('on_message')
    async def on_telephone_message(self, message: discord.Message):
        def delete_and_react(emoji):
            self.messages_to_remove.append(message)
            return message.add_reaction(emoji)

        if message.channel.id != self.telephone_channel_id:
            return
        elif message.flags.ephemeral:
            # guild will be None in this case
            return
        elif message.author == message.guild.me:
            return
        elif not self.bot.intents.message_content:
            return
        elif not self.rcon_client.is_logged_in():
            # NOTE: potential race condition if IDs are not added before reaction
            return await delete_and_react(self.disconnect_emoji)
        elif not 0 < len(content := filter_ascii(message.content)) < 140:
            return await delete_and_react('\N{HEAVY EXCLAMATION MARK SYMBOL}')
        elif self.message_cooldown.update_rate_limit(message):
            return await delete_and_react('\N{ALARM CLOCK}')

        try:
            await self.send_rcon_message(
                filter_ascii(message.author.display_name),
                content
            )
        except rcon.RCONCommandError:
            await delete_and_react('\N{HEAVY EXCLAMATION MARK SYMBOL}')
        else:
            await delete_and_react('\N{SATELLITE ANTENNA}')

    async def log_player_message(self, player: rcon.Player, channel: str, message: str):
        """Logs a message sent from RCON to be displayed in the telephone."""
        if channel not in ('Side', 'Group'):
            return

        message = discord.utils.escape_markdown(message)
        ts = timestamp_now('T')
        self.messages.append(f"{ts} `({channel}) {player.name}`: {message}")
        self.messages_has_updated = True

    @tasks.loop(seconds=MESSAGE_LOG_UPDATE_RATE)
    async def update_log_loop(self):
        """Periodically updates the telephone message."""
        message = self.telephone_partial_message
        channel = message.channel

        if self.messages_to_remove:
            try:
                await channel.delete_messages(self.messages_to_remove)
            except discord.NotFound:
                pass
            self.messages_to_remove.clear()

        if not self.messages_has_updated:
            return

        ts = timestamp_now('R')
        lines = [
            f'Last updated: {ts}',
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
        """Send a message to the Invade and Annex server (deprecated)."""
        try:
            logged_message = await self.send_rcon_message(
                filter_ascii(interaction.user.display_name),
                message
            )
        except rcon.RCONCommandError:
            pass  # Let the interaction fail
        else:
            await interaction.response.send_message(logged_message, ephemeral=True)
