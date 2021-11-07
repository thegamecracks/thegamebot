#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
import itertools
import re
from typing import Optional

import discord
from discord.ext import commands

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


class GuildIDConverter(commands.Converter[Optional[int]]):
    async def convert(self, ctx, argument) -> Optional[int]:
        argument = argument.lower()
        if argument == 'global':
            return 0
        elif argument == 'server':
            return getattr(ctx.guild, 'id', 0)

        guild = await commands.GuildConverter().convert(ctx, argument)
        if await guild.try_member(ctx.author.id):
            return guild.id

    @staticmethod
    def convert_after(ctx: commands.Context, argument: Optional[int]) -> Optional[int]:
        """Returns the context's guild id if the argument is None and passes-through otherwise.
        Should be used if the converter is combined with Optional.
        """
        if argument is None:
            # Either given by Optional converter or user inputted a guild they are not in
            return getattr(ctx.guild, 'id', None)
        elif argument == 0:
            # User inputted "global", or "server" inside DMs,
            # so do not default to the context's guild
            return None
        else:
            # Actual guild ID
            return argument


def escape_codeblocks(content: str) -> str:
    return converters.CodeBlock.REGEX.sub(
        r'\`\`\`\g<code>\`\`\`',
        content
    )


def invalid_indices(maximum: int, index: list[int], *, limit=3) -> list[int]:
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
        self, ctx, location: Optional[GuildIDConverter],
        *, index: IndexConverter = None
    ):
        """Show your global or server notes.

Examples:
note 1  (show note 1 for your current location)
notes global 1, 5  (show your global notes 1 and 5)
notes server 3-8  (show notes 3 through 8 for your current server)
If nothing is provided, all notes are shown."""
        location = GuildIDConverter.convert_after(ctx, location)
        location_name = 'global' if location is None else 'server'
        index: Optional[list[int]]

        note_list = await self.get_notes(ctx.author.id, location)
        length = len(note_list)

        if length == 0:
            return await ctx.send(f"You don't have any {location_name} notes.")
        elif index and (out_of_bounds := invalid_indices(length, index)):
            return await ctx.send(
                '{} {} {} out of range. Your notes are 1-{:,}.'.format(
                    ctx.bot.inflector.plural('Index', len(out_of_bounds)),
                    ctx.bot.inflector.join(out_of_bounds),
                    ctx.bot.inflector.plural('is', len(out_of_bounds)),
                    length
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
                name=f"{ctx.author.display_name}'s {location_name} note #{i + 1}",
                icon_url=ctx.author.display_avatar.url
            )
            return await ctx.send(embed=embed)

        lines = []
        for i, note in zip(index, note_list):
            content = escape_codeblocks(note['content'])
            truncated = utils.truncate_simple(content, 140, '...')
            first_line, *extra = truncated.split('\n', 1)
            extra = '...' if extra else ''
            lines.append(f'{i + 1}. {first_line}{extra}')

        embed = discord.Embed(
            color=color,
            description='\n'.join(lines)
        ).set_author(
            name="{}'s {} notes".format(
                ctx.author.display_name,
                location_name
            ),
            icon_url=ctx.author.display_avatar.url
        )

        await ctx.send(embed=embed)





    @client_notes.command(name='add')
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    async def client_notes_add(
        self, ctx,
        location: Optional[GuildIDConverter],
        *, content
    ):
        """Store a note.

Examples:
notes add ... (add a note in your current location)
notes add global ... (add a global note)
notes add server ... (add a server note)"""
        location = GuildIDConverter.convert_after(ctx, location)
        total_notes = len(await self.get_notes(ctx.author.id, location))

        if total_notes < self.MAX_NOTES_PER_LOCATION:
            await self.add_note(
                ctx.author.id, location,
                datetime.datetime.now().astimezone(),
                content
            )

            await ctx.send(
                'Your {} {} note has been added!'.format(
                    ctx.bot.inflector.ordinal(total_notes + 1),
                    'global' if location is None else 'server'
                )
            )
        else:
            await ctx.send(
                'Sorry, but you have reached your maximum limit of '
                '{:,} notes {}.'.format(
                    self.MAX_NOTES_PER_LOCATION,
                    'globally' if location is None
                    else 'in this server' if location == ctx.guild.id
                    else 'in that server'
                )
            )





    @client_notes.command(name='edit')
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    async def client_notes_edit(
        self, ctx, location: Optional[GuildIDConverter], index: int,
        *, content
    ):
        """Edit one of your notes.

Examples:
notes edit 1 ... (edit note 1 for your current location)
notes edit global 1 ... (edit global note 1)
notes edit server 3  (edit note 3 for your current server)

To see the indices for your notes, use the "notes" command."""
        location = GuildIDConverter.convert_after(ctx, location)
        location_name = 'global' if location is None else 'server'

        note_list = await self.get_notes(ctx.author.id, location)

        length = len(note_list)
        if length == 0:
            return await ctx.send(
                "You already don't have any {}.".format(
                    'global notes' if location is None
                    else 'notes in this server' if location == ctx.guild.id
                    else 'notes in that server'
                )
            )
        elif not 0 < index <= length:
            return await ctx.send(
                'Index {} is out of range. Your {} notes are 1-{:,}.'.format(
                    index,
                    location_name,
                    length
                )
            )

        await self.edit_note(
            ctx.author.id, location,
            note_list[index - 1]['note_id'],
            content=content
        )

        await ctx.send(
            ctx.bot.inflector.inflect(
                "{} note #{} successfully edited!".format(
                    location_name.capitalize(),
                    index
                )
            )
        )





    @client_notes.command(name='remove', aliases=('delete',))
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    async def client_notes_remove(
        self, ctx, location: Optional[GuildIDConverter],
        *, index: IndexConverter
    ):
        """Remove one or more notes.

Examples:
notes delete 1  (delete note 1 for your current location)
notes delete global 1, 5  (delete global notes 1 and 5)
notes delete server 3-8  (delete notes 3 through 8 for your current server)

To see the indices for your notes, use the "notes" command."""
        location = GuildIDConverter.convert_after(ctx, location)
        location_name = 'global' if location is None else 'server'
        index: list[int]

        note_list = await self.get_notes(ctx.author.id, location)

        length = len(note_list)
        if length == 0:
            return await ctx.send(
                "You already don't have any {}.".format(
                    'global notes' if location is None
                    else 'notes in this server' if location == ctx.guild.id
                    else 'notes in that server'
                )
            )
        elif out_of_bounds := invalid_indices(length, index):
            return await ctx.send(
                '{} {} {} out of range. Your {} notes are 1-{:,}.'.format(
                    ctx.bot.inflector.plural('Index', len(out_of_bounds)),
                    ctx.bot.inflector.join(out_of_bounds),
                    ctx.bot.inflector.plural('is', len(out_of_bounds)),
                    location_name,
                    length
                )
            )

        note_ids = [note_list[i]['note_id'] for i in index]
        await self.delete_notes_by_note_id(note_ids)

        await ctx.send(
            ctx.bot.inflector.inflect(
                "{n:,} {loc} plural('note', {n}) successfully deleted!".format(
                    n=len(index),
                    loc=location_name
                )
            )
        )










def setup(bot):
    bot.add_cog(NoteManagement(bot))
