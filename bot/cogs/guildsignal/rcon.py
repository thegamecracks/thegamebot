#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import collections
import unicodedata

import berconpy as rcon
import discord
from discord.ext import commands, tasks

from . import SignalHill
from main import TheGameBot


def filter_ascii(s: str) -> str:
    """Removes diacritics and drops any non-ascii characters from the given string."""
    decomposed_bytes = unicodedata.normalize('NFKD', s).encode()
    return decomposed_bytes.decode('ascii', 'ignore')


def timestamp_now(style):
    return discord.utils.format_dt(discord.utils.utcnow(), style)


class _SignalHill_RCON(commands.Cog):
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
        self.messages_to_remove: list[discord.Message] = []
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
            # This function is intentionally synchronous so the message
            # can be appended before attempting to add the reaction.
            # If the reaction fails or is ratelimited,
            # the `update_log_loop` can still delete the message.
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

    @update_log_loop.before_loop
    async def before_update_log_loop(self):
        await self.bot.wait_until_ready()
