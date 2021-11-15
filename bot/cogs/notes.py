#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
import itertools
import re
from typing import Optional, Sequence, Iterable, cast

import discord
from discord.ext import commands

from bot.classes.confirmation import ButtonConfirmation
from bot import converters, errors, utils


class IndexConverter(commands.Converter[list[int]]):
    """Convert an argument to a list of indices or a range.

    Formats supported:
        1        # [0]
        1, 9, 4  # [0, 4, 8]; indices are sorted
        1-3      # [0, 1, 2]

    """
    FORMAT_REGEX = re.compile(r'(?P<start>\d+)(?:-(?P<end>\d+))?')
    
    async def convert(self, ctx, argument) -> list[int]:
        indices = set()

        for m in self.FORMAT_REGEX.finditer(argument):
            start = int(m['start'])
            end = int(m['end'] or start)

            if start < 1:
                raise errors.IndexOutOfBoundsError(
                    'Your starting index cannot be below 1.')
            elif end < start:
                raise errors.IndexOutOfBoundsError(
                    'Your end index cannot be lower than your starting index.')

            for i in range(start - 1, end):
                indices.add(i)

        if not indices:
            raise errors.ErrorHandlerResponse('No indices were specified.')

        return sorted(indices)


class Location:
    """
    Attributes:
        guild (Optional[discord.Guild]):
            The guild this location is referencing, or None if global.
        outside (bool): Indicates if this location is not where the author
            is currently invoking the command, i.e. guild != ctx.guild.
    """

    def __init__(self, guild: Optional[discord.Guild] = None, *, outside=False):
        self.guild = guild
        self.outside = outside

    @property
    def id(self):
        """A shorthand for accessing the guild's ID."""
        return getattr(self.guild, 'id', None)

    @property
    def notes_in(self) -> str:
        return self.format_template(
            'notes globally',
            'notes in {name}',
            'notes in this server'
        )

    @property
    def note(self) -> str:
        return self.format_template(
            'global note',
            'note for {name}',
            'server note'
        )

    @property
    def notes(self) -> str:
        return self.format_template(
            'global notes',
            'notes for {name}',
            'server notes'
        )

    def format_template(self, globally: str, outside: str, here: str):
        """Return the appropriate template based on this location's state.
        For `outside` and `here`, the replacement field "{name}"
        can be included to substitute in the guild's name.
        """
        if self.guild is None:
            return globally
        elif self.outside:
            return outside.format(name=self.guild.name)
        return here.format(name=self.guild.name)

    @classmethod
    async def convert(cls, ctx, argument) -> "Location":
        argument = argument.lower()
        if argument == 'global':
            return cls()
        elif argument == 'server':
            return cls(ctx.guild)

        guild = await commands.GuildConverter().convert(ctx, argument)
        if await guild.try_member(ctx.author.id):
            return cls(guild, outside=True)
        return cls()


def escape_codeblocks(content: str) -> str:
    """Escape any code blocks in a given text."""
    parts = []
    last_index = 0

    # General form: pre ```block``` post
    # For each match, append pre and ```block```,
    # then check post for the same pattern, repeat if needed,
    # and append the remainder of that at the very end
    for m in converters.CodeBlock.REGEX.finditer(content):
        parts.append(content[last_index:m.start()])
        parts.append(discord.utils.escape_markdown(m.expand(r'```\g<code>```')))
        last_index = m.end()

    parts.append(content[last_index:])

    return ''.join(parts)


def invalid_indices(maximum: int, index: Iterable[int], *, limit=3) -> list[str]:
    """Return a list of 1-indexed strings indicating which
    indices are out of bounds."""
    over = (str(n + 1) for n in index if not 0 < n + 1 <= maximum)
    if limit:
        return list(itertools.islice(over, limit))
    return list(over)


class NoteManagement(commands.Cog):
    """Commands for saving notes."""
    qualified_name = 'Note Management'

    MAX_NOTES_PER_LOCATION = 20

    def __init__(self, bot):
        self.bot = bot
        self.cache = {}  # (user_id, guild_id): notes
        # NOTE: this bot is small so this isn't required but if the bot
        # never restarts frequently, the cache could grow forever,
        # so this could use an LRU cache implementation





    async def add_note(self, user_id, guild_id, *args, **kwargs):
        """Adds a note and invalidates the user's cache."""
        await self.bot.dbusers.add_user(user_id)
        await self.bot.dbnotes.add_note(user_id, guild_id, *args, **kwargs)
        self.cache.pop((user_id, guild_id), None)

    async def delete_notes_by_note_id(self, note_id, pop=False):
        """Remove a note by note_id and update the cache."""
        deleted = await self.bot.dbnotes.delete_notes_by_note_id(note_id, pop=True)

        updated_keys = frozenset(
            (note['user_id'], note['guild_id'])
            for note in deleted
        )

        for key in updated_keys:
            self.cache.pop(key, None)

        return deleted if pop else None

    async def edit_note(self, user_id, guild_id, *args, **kwargs):
        """Edits a note and invalidates the user's cache."""
        await self.bot.dbnotes.edit_note(*args, **kwargs)
        self.cache.pop((user_id, guild_id), None)

    async def get_notes(self, user_id: int, guild_id: Optional[int]):
        key = (user_id, guild_id)
        notes = self.cache.get(key)

        if notes is None:
            # Uncached user; add them to cache
            notes = await self.bot.dbnotes.get_notes(user_id, guild_id)
            self.cache[key] = notes

        return notes





    @commands.group(
        name='notes', aliases=('note',),
        invoke_without_command=True
    )
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    async def client_notes(
        self, ctx, location: Optional[Location],
        *, index: IndexConverter = None
    ):
        """Show your global or server notes.

Examples:
note 1  (show note 1 for your current location)
notes global 1, 5  (show your global notes 1 and 5)
notes server 3-8  (show notes 3 through 8 for your current server)
If nothing is provided, all notes are shown."""
        location = cast(Location, location or Location(ctx.guild))
        index: Optional[Sequence[int]]

        note_list = await self.get_notes(ctx.author.id, location.id)
        length = len(note_list)

        if length == 0:
            return await ctx.send(f"You don't have any {location.notes}.")
        elif index and (out_of_bounds := invalid_indices(length, index)):
            return await ctx.send(
                '{} {} {} out of range. Your {notes} are 1-{end:,}.'.format(
                    ctx.bot.inflector.plural('Index', len(out_of_bounds)),
                    ctx.bot.inflector.join(out_of_bounds),
                    ctx.bot.inflector.plural('is', len(out_of_bounds)),
                    notes=location.notes,
                    end=length
                )
            )

        if index is None:
            index = range(length)
        else:
            note_list = [note_list[i] for i in index]

        color = utils.get_user_color(ctx.bot, ctx.author)

        # TODO: pagination of notes
        if len(note_list) == 1:
            i, note = next(zip(index, note_list))
            embed = discord.Embed(
                description=note['content'],
                color=color,
                timestamp=note['time_of_entry']
            ).set_author(
                name=f"{ctx.author.display_name}'s {location.note} #{i + 1}",
                icon_url=ctx.author.display_avatar.url
            )
            return await ctx.send(embed=embed)

        lines = []
        for i, note in zip(index, note_list):
            # NOTE: it is possible that truncate_simple will cut off
            # between a backslash and a markdown character
            content = escape_codeblocks(note['content'])
            truncated = utils.truncate_simple(content, 140, '...')
            first_line, *extra = truncated.split('\n', 1)
            extra = '...' if extra else ''
            lines.append(f'{i + 1}. {first_line}{extra}')

        embed = discord.Embed(
            color=color,
            description='\n'.join(lines)
        ).set_author(
            name=f"{ctx.author.display_name}'s {location.notes}",
            icon_url=ctx.author.display_avatar.url
        )

        await ctx.send(embed=embed)





    @client_notes.command(name='add')
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    async def client_notes_add(
        self, ctx,
        location: Optional[Location],
        *, content
    ):
        """Store a note.

Examples:
notes add ... (add a note in your current location)
notes add global ... (add a global note)
notes add server ... (add a server note)"""
        location = cast(Location, location or Location(ctx.guild))
        total_notes = len(await self.get_notes(ctx.author.id, location.id))

        if total_notes < self.MAX_NOTES_PER_LOCATION:
            await self.add_note(
                ctx.author.id, location.id,
                datetime.datetime.now().astimezone(),
                content
            )

            await ctx.send(
                'Your {nth} {note} has been added!'.format(
                    nth=ctx.bot.inflector.ordinal(total_notes + 1),
                    note=location.note
                )
            )
        else:
            await ctx.send(
                'Sorry, but you have reached your maximum limit of '
                f'{self.MAX_NOTES_PER_LOCATION:,} {location.notes_in}.'
            )





    @client_notes.command(name='edit')
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    async def client_notes_edit(
        self, ctx, location: Optional[Location], index: int,
        *, content
    ):
        """Edit one of your notes.

Examples:
notes edit 1 ... (edit note 1 for your current location)
notes edit global 1 ... (edit global note 1)
notes edit server 3  (edit note 3 for your current server)

To see the indices for your notes, use the "notes" command."""
        location = cast(Location, location or Location(ctx.guild))

        note_list = await self.get_notes(ctx.author.id, location.id)

        length = len(note_list)
        if length == 0:
            return await ctx.send(f"You already don't have any {location.notes_in}.")
        elif not 0 < index <= length:
            return await ctx.send(
                'Index {i} is out of range. Your {notes} are 1-{end:,}.'.format(
                    i=index,
                    notes=location.notes,
                    end=length
                )
            )

        await self.edit_note(
            ctx.author.id, location.id,
            note_list[index - 1]['note_id'],
            content=content
        )

        await ctx.send(f"{location.note} #{index} successfully edited!".capitalize())





    @client_notes.command(name='remove', aliases=('delete',))
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    async def client_notes_remove(
        self, ctx, location: Optional[Location],
        *, index: IndexConverter
    ):
        """Remove one or more notes.

Examples:
notes delete 1  (delete note 1 for your current location)
notes delete global 1, 5  (delete global notes 1 and 5)
notes delete server 3-8  (delete notes 3 through 8 for your current server)

To see the indices for your notes, use the "notes" command."""
        location = cast(Location, location or Location(ctx.guild))
        index: list[int]

        note_list = await self.get_notes(ctx.author.id, location.id)

        length = len(note_list)
        if length == 0:
            return await ctx.send(f"You already don't have any {location.notes_in}.")
        elif out_of_bounds := invalid_indices(length, index):
            return await ctx.send(
                '{} {} {} out of range. Your {notes} are 1-{end:,}.'.format(
                    ctx.bot.inflector.plural('Index', len(out_of_bounds)),
                    ctx.bot.inflector.join(out_of_bounds),
                    ctx.bot.inflector.plural('is', len(out_of_bounds)),
                    notes=location.notes,
                    end=length
                )
            )

        note_str = '{n} {notes}'.format(
            n=len(index),
            notes=location.notes if len(index) != 1 else location.note
        )

        prompt = ButtonConfirmation(ctx, utils.get_user_color(ctx.bot, ctx.author))
        if await prompt.confirm(f'Are you sure you want to delete {note_str}?'):
            await prompt.update(f'Deleting {note_str}...', color=prompt.YES)

            note_ids = [note_list[i]['note_id'] for i in index]
            await self.delete_notes_by_note_id(note_ids)

            await prompt.update(f'{note_str} successfully deleted!')
        else:
            await prompt.update('Cancelled note deletion.', color=prompt.NO)










def setup(bot):
    bot.add_cog(NoteManagement(bot))
