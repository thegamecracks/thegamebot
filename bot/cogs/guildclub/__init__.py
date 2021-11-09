#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import collections
import dataclasses
import datetime
import re
from typing import ClassVar, cast, Optional

import discord
import humanize
from discord.ext import commands

from bot import errors, utils


@dataclasses.dataclass(order=True, slots=True)
class Suggestion:
    timestamp: datetime.datetime
    user_id: int
    thread_id: int

    FORMAT = '{timestamp} <@{user}> \N{RIGHTWARDS ARROW} <#{thread}>'
    REGEX: ClassVar[re.Pattern] = re.compile(
        r"""<t:(?P<timestamp>\d+):[fFdDtTR]>
            \ <@!?(?P<user_id>\d+)>
            \ \N{RIGHTWARDS ARROW}
            \ <\#(?P<thread_id>\d+)>
        """,
        re.VERBOSE
    )

    def __str__(self):
        return self.FORMAT.format(
            timestamp=discord.utils.format_dt(self.timestamp, style='R'),
            user=self.user_id,
            thread=self.thread_id
        )

    @classmethod
    def from_string(cls, s: str):
        m = cls.REGEX.fullmatch(s)
        if m is None:
            raise ValueError(f'Suggestion string is malformed: {s!r}')

        return cls(
            datetime.datetime.fromtimestamp(int(m['timestamp'])).astimezone(),
            int(m['user_id']),
            int(m['thread_id'])
        )


# NOTE: whatever you do, don't use collections.UserList
# I was scratching my head for an hour because of it
class SuggestionsList:
    NO_SUGGESTIONS_TEXT = 'There are currently no running suggestions!'

    def __init__(self, suggestions: list[Suggestion]):
        self._items = suggestions

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, self._items)

    def __iter__(self):
        return iter(self._items)

    def append(self, s: Suggestion):
        self._items.append(s)

    def remove(self, s: Suggestion):
        self._items.remove(s)

    def to_embed(self) -> discord.Embed:
        embed = discord.Embed(
            color=0x3A8CEE,  # Admin blue
            title='Active Suggestions'
        )

        description = []
        if len(self._items) > 0:
            self._items.sort()
            for suggestion in self:
                description.append(str(suggestion))
        else:
            description.append(self.NO_SUGGESTIONS_TEXT)

        description.append('')
        description.append(
            'Updated {}'.format(
                discord.utils.format_dt(datetime.datetime.now(), style='R')
            )
        )

        embed.description = '\n'.join(description)

        return embed

    @classmethod
    def from_threads(cls, threads: list[discord.Thread], user_ids: list[int]):
        """Construct the suggestions embed from the existing threads."""
        suggestions = []

        for thread, user_id in zip(threads, user_ids):
            suggestions.append(Suggestion(
                thread.archive_timestamp,
                user_id,
                thread.id
            ))

        return cls(suggestions)

    @classmethod
    def from_embed(cls, embed: discord.Embed):
        """Parse the information from an existing suggestions embed."""

        if embed.description.startswith(cls.NO_SUGGESTIONS_TEXT):
            return cls([])

        suggestions = []
        for line in embed.description.split('\n'):
            if line:
                suggestions.append(Suggestion.from_string(line))
            else:
                # Empty line separating extra info from the suggestions
                break

        return cls(suggestions)


class SuggestionsView(discord.ui.View):
    def __init__(self, cog: "CSClub"):
        super().__init__(timeout=None)
        self.cog = cog
        self.last_suggestions: Optional[SuggestionsList] = None
        self.cooldown = commands.CooldownMapping.from_cooldown(
            1, 600, commands.BucketType.user
        )
        self.edit_lock = asyncio.Lock()
        # This lock should be used by anything that edits the message
        # to ensure state is not overridden

    @property
    def partial_message(self) -> Optional[discord.PartialMessage]:
        channel = self.cog.guild.get_channel(self.cog.SUGGESTIONS_CHANNEL_ID)
        if channel is not None:
            return channel.get_partial_message(self.cog.SUGGESTIONS_MESSAGE_ID)

    async def fetch_suggestions(self, message=None) -> SuggestionsList:
        if self.last_suggestions:
            return self.last_suggestions
        elif message is None:
            message = await self.partial_message.fetch()

        if message.embeds:
            self.last_suggestions = SuggestionsList.from_embed(message.embeds[0])
            return self.last_suggestions

        # Generate new embed from current threads
        threads = message.channel.threads
        thread_ids = [thread.id for thread in threads]
        thread_user_mapping = await self.cog.fetch_suggestion_user_ids(thread_ids)
        user_ids = list(thread_user_mapping.values())
        self.last_suggestions = SuggestionsList.from_threads(threads, user_ids)
        return self.last_suggestions

    async def update(self):
        suggestions = await self.fetch_suggestions()
        return await self.partial_message.edit(embed=suggestions.to_embed())

    async def on_error(self, error, item: discord.ui.Button, interaction):
        if isinstance(error, errors.SkipInteractionResponse):
            return

        # Make sure button isn't deadlocked
        if item.disabled and interaction.response.is_done():
            item.disabled = False
            await interaction.edit_original_message(view=self)

        raise error

    @discord.ui.button(
        custom_id='create',
        emoji='\N{MEMO}',
        label='Make a suggestion!',
        style=discord.ButtonStyle.blurple
    )
    async def create_suggestion(self, button: discord.ui.Button, interaction: discord.Interaction):
        async with self.edit_lock:
            # Parse the current suggestion embed for thread data
            suggestions = await self.fetch_suggestions(interaction.message)

            # Disallow having more than one active suggestion
            existing = discord.utils.get(suggestions, user_id=interaction.user.id)
            if existing is not None:
                return await interaction.response.send_message(
                    f'You already have an active suggestion: <#{existing.thread_id}>',
                    ephemeral=True
                )

            # Check that user is not on cooldown
            bucket = self.cooldown.get_bucket(utils.MockMessage(interaction.user))  # type: ignore
            retry_after = bucket.get_retry_after()
            if retry_after:
                return await interaction.response.send_message(
                    'Please wait {} before creating another suggestion!'.format(
                        humanize.naturaldelta(retry_after)  # type: ignore
                    ),
                    ephemeral=True
                )

            # Start creating thread, temporarily disabling the button
            button.disabled = True
            try:
                await interaction.response.edit_message(view=self)
            except discord.HTTPException:
                raise errors.SkipInteractionResponse('Timed out before edit')

            thread = await interaction.channel.create_thread(
                name='By ' + interaction.user.display_name,
                type=discord.ChannelType.public_thread
            )

            # Update cooldown
            bucket.update_rate_limit()

            # Add to database
            async with self.cog.bot.dbusers.connect(writing=True) as conn:
                await conn.execute(
                    'INSERT INTO CSClubSuggestions VALUES (?, ?)',
                    thread.id, interaction.user.id
                )

            # Update the message
            suggestions.append(Suggestion(
                thread.archive_timestamp,
                interaction.user.id,
                thread.id
            ))
            embed = suggestions.to_embed()

            button.disabled = False
            await interaction.edit_original_message(embed=embed, view=self)

        # Send initial message
        await thread.send(
            '{} Write your suggestion and anyone can discuss it in here!\n'
            'To change the name of this thread, use the `/rename <title>` '
            'slash command.'.format(interaction.user.mention)
        )


def is_valid_suggestion_channel():
    async def predicate(ctx: commands.Context):
        channel: discord.TextChannel | discord.Thread = ctx.channel
        cog = cast(CSClub, ctx.bot.get_cog('CSClub'))

        if (not isinstance(channel, discord.Thread)
                or channel.parent_id != cog.SUGGESTIONS_CHANNEL_ID):
            raise errors.ErrorHandlerResponse(
                'This command is only for threads inside '
                f'<#{cog.SUGGESTIONS_CHANNEL_ID}>!'
            )

        if not ctx.author_permissions().manage_threads:
            user_id = await cog.fetch_suggestion_user_id(channel.id)
            if ctx.author.id != user_id:
                raise errors.ErrorHandlerResponse(
                    "You cannot rename someone else's suggestion!"
                )

        return True

    return commands.check(predicate)


class CSClub(commands.Cog):
    """Commands for CS Club."""
    qualified_name = 'CS Club'

    GUILD_ID = 901195466656604211
    SUGGESTIONS_CHANNEL_ID = 905955070934384671
    SUGGESTIONS_MESSAGE_ID = 907478104891621386

    def __init__(self, bot):
        self.bot = bot

        self.suggestions_view = SuggestionsView(self)
        bot.add_view(self.suggestions_view, message_id=self.SUGGESTIONS_MESSAGE_ID)

        asyncio.create_task(self.setup_database())

    @property
    def guild(self):
        return self.bot.get_guild(self.GUILD_ID)

    # Listeners

    @commands.Cog.listener('on_message')
    async def on_suggestion_create(self, message: discord.Message):
        if message.channel.id != self.SUGGESTIONS_CHANNEL_ID:
            return
        elif message.type == discord.MessageType.thread_created:
            await message.delete()

    @commands.Cog.listener('on_thread_delete')
    async def on_suggestion_delete(self, thread: discord.Thread, *, keep_in_database=False):
        if thread.parent_id != self.SUGGESTIONS_CHANNEL_ID:
            return

        if not keep_in_database:
            # Remove from database if it exists
            # NOTE: this cleanup does not happen for archived threads
            # since they can be unarchived
            async with self.bot.dbusers.connect(writing=True) as conn:
                await conn.execute(
                    'DELETE FROM CSClubSuggestions WHERE thread_id=?',
                    thread.id
                )

        # Remove from embed if it exists
        async with self.suggestions_view.edit_lock:
            suggestions = await self.suggestions_view.fetch_suggestions()
            existing = discord.utils.get(suggestions, thread_id=thread.id)
            if existing is not None:
                suggestions.remove(existing)
                await self.suggestions_view.update()

    @commands.Cog.listener('on_thread_update')
    async def on_suggestion_update(self, before: discord.Thread, after: discord.Thread):
        if after.parent_id != self.SUGGESTIONS_CHANNEL_ID:
            return
        elif not before.archived and after.archived:
            # Archived; remove from embed
            return await self.on_suggestion_delete(after, keep_in_database=True)
        elif before.archived and not after.archived:
            # Unarchived; add back to embed
            async with self.suggestions_view.edit_lock:
                suggestions = await self.suggestions_view.fetch_suggestions()
                suggestions.append(Suggestion(
                    after.archive_timestamp,
                    await self.fetch_suggestion_user_id(after.id),
                    after.id
                ))
                return await self.suggestions_view.update()

    # Database stuff

    async def setup_database(self):
        async with self.bot.dbusers.connect(writing=True) as conn:
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS CSClubSuggestions (
                thread_id INTEGER PRIMARY KEY NOT NULL,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES Users(id)
                    ON DELETE CASCADE
            )""")

    async def fetch_suggestion_user_id(self, thread_id: int) -> int:
        async with self.bot.dbusers.connect() as conn:
            async with conn.execute(
                    'SELECT user_id FROM CSClubSuggestions '
                    'WHERE thread_id=?', thread_id) as c:
                row = await c.fetchone()

                if row is None:
                    raise ValueError(f'Unknown thread id {thread_id}')

                return row['user_id']

    async def fetch_suggestion_user_ids(self, thread_ids: list[int]) -> dict[int, int]:
        result = dict.fromkeys(thread_ids)
        async with self.bot.dbusers.connect() as conn:
            async with conn.cursor() as c:
                query = """
                SELECT thread_id, user_id FROM CSClubSuggestions
                WHERE user_id IN ({})
                """.format(', '.join('?' * len(thread_ids)))
                await c.execute(query, *result.keys())

                while row := await c.fetchone():
                    result[row['thread_id']] = row['user_id']

                return result

    # Commands

    @commands.command(
        name='rename',
        message_command=False,
        slash_command=True, slash_command_guilds=[GUILD_ID]
    )
    @commands.cooldown(2, 600, commands.BucketType.channel)
    @is_valid_suggestion_channel()
    async def client_rename_suggestion(
        self, ctx: commands.Context,
        title: str = commands.Option(description='The new title for your suggestion (at most 50 letters).')
    ):
        """Rename the title of your suggestion thread."""
        excess = len(title) - 50
        if excess > 0:
            return await ctx.send(
                f'Your title is {excess:,} characters too long!',
                ephemeral=True
            )

        await ctx.interaction.response.defer(ephemeral=True)
        await ctx.channel.edit(name=title)
        await ctx.interaction.followup.send(
            'Suggestion title successfully edited!',
            ephemeral=True
        )


def setup(bot):
    bot.add_cog(CSClub(bot))
