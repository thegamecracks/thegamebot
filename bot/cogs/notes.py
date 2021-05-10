#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
import itertools
import re
import textwrap
from typing import Iterable, Optional

import discord
from discord.ext import commands
from discord_slash.utils import manage_commands
from discord_slash import cog_ext as dslash_cog
from discord_slash import SlashContext
import discord_slash as dslash

from bot import errors, utils


class IndexConverter(commands.Converter):
    """Convert an argument to a list of indices or a range.

    Formats supported:
        1        # [0]
        1, 5, 9  # [0, 4, 8]
        1-3      # range(0, 3)

    """
    int_regex = re.compile(r'-?\d+')
    
    async def convert(self, ctx, argument) -> Iterable[int]:
        # slice
        try:
            x, y = [int(n) for n in argument.split('-', 1)]

            if x - 1 < 0:
                raise errors.IndexOutOfBoundsError(
                    'Your starting index cannot be below 1.')
            elif y < x:
                raise errors.IndexOutOfBoundsError(
                    'Your end index cannot be lower than your starting index.')

            return range(x - 1, y)
        except ValueError:
            pass

        # list
        indices = self.int_regex.findall(argument)
        if not indices:
            raise errors.IndexOutOfBoundsError(
                'Could not understand your range.')
                
        return [int(n) - 1 for n in indices]


class NoteManagement(commands.Cog):
    """Commands for saving notes."""
    qualified_name = 'Note Management'

    max_notes_user = 20

    def __init__(self, bot):
        self.bot = bot
        self.cache = {}  # user_id: notes
        # NOTE: this bot is small so this isn't required but if the bot
        # never restarts frequently, the cache could grow forever,
        # so this could use an LRU cache implementation





    async def add_note(self, user_id, *args, **kwargs):
        """Adds a note and invalidates the user's cache."""
        await self.bot.dbusers.add_user(user_id)
        await self.bot.dbnotes.add_note(user_id, *args, **kwargs)
        self.cache.pop(user_id, None)

    def invalid_indices(self, maximum: int, index: list, *, limit=3):
        """Return a list of 1-indexed strings indicating which
        indices are out of bounds."""
        over = (str(n + 1) for n in index if not 0 < n + 1 <= maximum)
        if limit:
            return list(itertools.islice(over, limit))
        return list(over)

    async def delete_notes_by_note_id(self, note_id, pop=False):
        """Remove a note by note_id and update the cache."""
        deleted = await self.bot.dbnotes.delete_notes_by_note_id(note_id, pop=True)

        updated_ids = frozenset(note['user_id'] for note in deleted)

        for user_id in updated_ids:
            self.cache.pop(user_id, None)

        return deleted if pop else None

    async def get_notes(self, user_id):
        notes = self.cache.get(user_id)

        if notes is None:
            # Uncached user; add them to cache
            notes = await self.bot.dbnotes.get_notes(user_id)
            self.cache[user_id] = notes

        return notes





    @commands.group(
        name='notes', aliases=('note',),
        invoke_without_command=True
    )
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    async def client_notes(self, ctx, *, index: IndexConverter = None):
        """Show your notes.
The index parameter allows several formats:
1  # show note 1
1, 5  # show notes 1 and 5
3-8  # show notes 3 through 8
If nothing is provided, all notes are shown."""
        index: Optional[Iterable[int]]

        note_list = await self.get_notes(ctx.author.id)

        length = len(note_list)
        if length == 0:
            return await ctx.send("You don't have any notes.")
        elif index and (out_of_bounds := self.invalid_indices(length, index)):
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

        if len(note_list) == 1:
            index, note = next(zip(index, note_list))
            embed = discord.Embed(
                title=f'Note #{index+1:,}',
                description=note['content'],
                color=color,
                timestamp=datetime.datetime.fromisoformat(
                    note['time_of_entry'])
            )
            return await ctx.send(embed=embed)

        # Create fields for each note, limiting them to 140 characters/5 lines
        fields = [
            utils.truncate_message(note['content'], 140, max_lines=5)
            for note in note_list
        ]

        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Notes",
            color=color
        )

        for i, content in zip(index, fields):
            embed.add_field(name=f'Note {i+1:,}', value=content)

        await ctx.send(embed=embed)


    @dslash_cog.cog_subcommand(
        base='notes',
        name='show',
        options=[manage_commands.create_option(
            name='index',
            description='The note to view. Leave empty to show all notes.',
            option_type=4,
            required=False
        )]
    )
    async def client_slash_shownote(self, ctx: SlashContext, index: int = None):
        """Show one or all of your notes."""
        note_list = await self.get_notes(ctx.author.id)
        notes_len = len(note_list)

        if notes_len == 0:
            return await ctx.send("You don't have any notes.", hidden=True)
        elif index is not None:
            # Show one note
            if index < 1:
                return await ctx.send('Index must be 1 or greater.', hidden=True)

            try:
                note = note_list[index - 1]
            except IndexError:
                await ctx.send('That note index does not exist.', hidden=True)
            else:
                content = (
                    f'__Note #{index:,}__\n'
                    f"{note['content']}"
                )
                await ctx.send(content, hidden=True)
        else:
            # Create fields for each note, keeping it under 2000 characters
            title_total = len(f'__Note {notes_len:,}__\n')
            title_total += 2 * notes_len - 2  # Include newlines
            max_per_field = (2000 - title_total) // self.max_notes_user

            fields = [
                f'__Note {i:,}__\n'
                + utils.truncate_message(
                    note['content'], max_per_field, max_lines=5)
                for i, note in enumerate(note_list, start=1)
            ]
            content = '\n\n'.join(fields)

            await ctx.send(content, hidden=True)





    @client_notes.command(name='add')
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    async def client_notes_add(self, ctx, *, note):
        """Store a note."""
        total_notes = len(await self.get_notes(ctx.author.id))

        if total_notes < self.max_notes_user:
            await self.add_note(
                ctx.author.id, datetime.datetime.now().astimezone(), note
            )

            await ctx.send(
                'Your {} note has been added!'.format(
                    ctx.bot.inflector.ordinal(total_notes + 1)
                )
            )
        else:
            await ctx.send(
                'Sorry, but you have reached your maximum limit of '
                f'{self.max_notes_user:,} notes.'
            )


    @dslash_cog.cog_subcommand(
        base='notes',
        name='add',
        description=f'Store a note. You can have a maximum of {max_notes_user:,} notes.',
        base_description='Commands for saving notes.',
        options=[manage_commands.create_option(
            name='text',
            description='The content of your note.',
            option_type=3,
            required=True
        )]
    )
    async def client_slash_addnote(self, ctx: SlashContext, note):
        max_length = 2000 - len(f'__Note #{self.max_notes_user:,}__\n')
        if len(note) > max_length:
            return await ctx.send('This note is too large.', hidden=True)

        total_notes = len(await self.get_notes(ctx.author.id))

        if total_notes < self.max_notes_user:
            await self.add_note(
                ctx.author.id, datetime.datetime.now().astimezone(), note
            )

            await ctx.send(
                'Your {} note has been added!'.format(
                    ctx.bot.inflector.ordinal(total_notes + 1)
                ), hidden=True
            )
        else:
            await ctx.send(
                'Sorry, but you have reached your maximum limit of '
                f'{self.max_notes_user:,} notes.',
                hidden=True
            )





    @client_notes.command(name='remove', aliases=('delete',))
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    async def client_notes_remove(self, ctx, *, index: IndexConverter):
        """Remove one or more notes.
The index parameter allows several formats:
1  # delete note 1
1, 5  # delete notes 1 and 5
3-8  # delete notes 3 through 8
To see a list of your notes and their indices, use the "notes show" command."""
        index: Iterable[int]

        note_list = await self.get_notes(ctx.author.id)

        length = len(note_list)
        if length == 0:
            return await ctx.send("You already don't have any notes.")
        elif out_of_bounds := self.invalid_indices(length, index):
            return await ctx.send(
                '{} {} {} out of range. Your notes are 1-{:,}.'.format(
                    ctx.bot.inflector.plural('Index', len(out_of_bounds)),
                    ctx.bot.inflector.join(out_of_bounds),
                    ctx.bot.inflector.plural('is', len(out_of_bounds)),
                    length
                )
            )

        note_ids = [note_list[i]['note_id'] for i in index]
        await self.delete_notes_by_note_id(note_ids)

        await ctx.send(
            ctx.bot.inflector.inflect(
                "{n:,} plural('note', {n}) successfully deleted!".format(
                    n=len(index)
                )
            )
        )


    @dslash_cog.cog_subcommand(
        base='notes',
        name='remove',
        options=[manage_commands.create_option(
            name='index',
            description='The note to remove.',
            option_type=4,
            required=True
        )]
    )
    async def client_slash_removenote(self, ctx: SlashContext, index: int):
        """Remove a note by index. To see the indices for your notes, use /notes show."""
        note_list = await self.get_notes(ctx.author.id)

        if len(note_list) == 0:
            return await ctx.send("You already don't have any notes.",
                                  hidden=True)

        try:
            note = note_list[index - 1]
        except IndexError:
            await ctx.send('That note index does not exist.',
                           hidden=True)
        else:
            await self.delete_notes_by_note_id(note['note_id'])
            await ctx.send('Note successfully deleted!', hidden=True)










def setup(bot):
    bot.add_cog(NoteManagement(bot))
