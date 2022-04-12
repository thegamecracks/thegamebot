#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
import functools
import itertools
import sqlite3
from typing import Sequence, Iterable, cast, AsyncGenerator, Collection

import asqlite
import discord
from discord.ext import commands

from bot.utils import ConfirmationView
from bot import converters, utils
from main import Context, TheGameBot


def index_converter(**kwargs):
    return commands.parameter(converter=converters.IndexConverter, **kwargs)


class Location:
    """Represents a location where one or more notes are being acquired from."""

    def __init__(self, guild: discord.Guild = None, *, outside=False):
        """
        :param guild:
            The guild this location is referencing, or None if global.
        :param outside:
            Indicates if this location is not where the author is currently
            invoking the command, i.e. guild != ctx.guild.
        """
        self.guild = guild
        self.outside = outside

    @property
    def id(self) -> int | None:
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
    def notes_str(self) -> str:
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
        if await utils.getch_member(guild, ctx.author.id):
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


async def query_note_count(conn: asqlite.Connection, user_id: int, guild_id: int | None) -> int:
    # NOTE: because guild_id can be None, the query has
    # to use "IS" to correctly match nulls
    query = 'SELECT COUNT(*) AS length FROM note WHERE user_id = ? AND guild_id IS ?'
    async with conn.execute(query, user_id, guild_id) as c:
        row = await c.fetchone()
        return row['length']


async def yield_notes(
    conn: asqlite.Connection, user_id: int, guild_id: int | None,
    *, indices: Collection[int] = None, only_ids: bool = False
) -> AsyncGenerator[sqlite3.Row, None]:
    columns = 'note_id' if only_ids else '*'
    query = f'SELECT {columns} FROM note WHERE user_id = ? AND guild_id IS ?'

    async with conn.execute(query, user_id, guild_id) as c:
        if indices is not None:
            i = 0
            while row := await c.fetchone():
                if i in indices:
                    yield row
                i += 1
        else:
            while row := await c.fetchone():
                yield row


class NoteView(discord.ui.View):
    """Provides extra buttons when viewing a single note.

    Args:
        index (int): The note index.
        kwargs: All columns of the note.

    """
    message: discord.Message | None = None

    def __init__(self, *, index: int, **kwargs):
        super().__init__(timeout=30)
        self.index = index
        self.content = kwargs.get('content', '')

        if self.escaped_content == self.content:
            self.remove_item(self.view_raw)  # type: ignore

    @functools.cached_property
    def escaped_content(self):
        return utils.rawify_content(self.content)

    async def on_timeout(self):
        await self.message.edit(view=None)

    @discord.ui.button(label='View raw')
    async def view_raw(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(self.escaped_content, ephemeral=True)


class NoteManagement(commands.Cog):
    """Commands for saving notes."""
    qualified_name = 'Note Management'

    MAX_NOTES_PER_LOCATION = 20

    def __init__(self, bot: TheGameBot):
        self.bot = bot

    def send_invalid_indices(
        self, channel: discord.abc.Messageable,
        out_of_bounds: list[str], location: Location, total: int
    ):
        inflector = self.bot.inflector
        return channel.send(
            '{indexes} {n} {are} out of range. Your {notes} are between 1-{total:,}.'.format(
                indexes=inflector.plural('Index', len(out_of_bounds)),
                n=inflector.join(out_of_bounds),
                are=inflector.plural('is', len(out_of_bounds)),
                notes=location.notes_str,
                total=total
            )
        )

    @commands.group(
        name='notes', aliases=('note',),
        invoke_without_command=True
    )
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def notes(
        self, ctx: Context, location: Location | None,
        *, index: list[int] = index_converter(default=None)
    ):
        """Show your global or server notes.

Examples:
note 1  (show note 1 for your current location)
notes global 1, 5  (show your global notes 1 and 5)
notes server 3-8  (show notes 3 through 8 for your current server)
If nothing is provided, all notes are shown."""
        location = cast(Location, location or Location(ctx.guild))
        index: Sequence[int] | None

        async with ctx.bot.db.connect() as conn:
            total = await query_note_count(conn, ctx.author.id, location.id)

            if total == 0:
                return await ctx.send(f"You don't have any {location.notes_str}.")
            elif index and (out_of_bounds := invalid_indices(total, index)):
                return await self.send_invalid_indices(ctx, out_of_bounds, location, total)

            if index is None:
                index = range(total)

            note_list = [
                row
                async for row in yield_notes(
                    conn, ctx.author.id,
                    location.id, indices=index
                )
            ]

        color = ctx.author.color.value or ctx.bot.get_bot_color()

        # TODO: pagination of notes
        if len(note_list) == 1:
            i, note = index[0], note_list[0]
            embed = discord.Embed(
                description=note['content'],
                color=color,
                timestamp=note['time_of_entry']
            ).set_author(
                name=f"{ctx.author.display_name}'s {location.note} #{i + 1}",
                icon_url=ctx.author.display_avatar.url
            )
            view = NoteView(index=i, **note)  # type: ignore
            view.message = await ctx.send(embed=embed, view=view)
            return

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
            name=f"{ctx.author.display_name}'s {location.notes_str}",
            icon_url=ctx.author.display_avatar.url
        )

        await ctx.send(embed=embed)

    @notes.command(name='add')
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def notes_add(
        self, ctx: Context,
        location: Location | None,
        *, content
    ):
        """Store a note.

Examples:
notes add ... (add a note in your current location)
notes add global ... (add a global note)
notes add server ... (add a server note)"""
        location = cast(Location, location or Location(ctx.guild))

        async with ctx.bot.db.connect() as conn:
            total = await query_note_count(conn, ctx.author.id, location.id)

        if total < self.MAX_NOTES_PER_LOCATION:
            async with ctx.bot.db.connect(writing=True) as conn:
                await conn.execute(
                    'INSERT OR IGNORE INTO user (user_id) VALUES (?)',
                    ctx.author.id
                )
                await conn.execute(
                    """
                    INSERT INTO note (user_id, guild_id, time_of_entry, content)
                        VALUES (?, ?, ?, ?);
                    """,
                    ctx.author.id, location.id,
                    datetime.datetime.now().astimezone(), content
                )

            await ctx.send(
                'Your {nth} {note} has been added!'.format(
                    nth=ctx.bot.inflector.ordinal(total + 1),
                    note=location.note
                )
            )
        else:
            await ctx.send(
                'Sorry, but you have reached your maximum limit of '
                f'{self.MAX_NOTES_PER_LOCATION:,} {location.notes_in}.'
            )

    @notes.command(name='edit')
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def notes_edit(
        self, ctx: Context, location: Location | None, index: int,
        *, content
    ):
        """Edit one of your notes.

Examples:
notes edit 1 ... (edit note 1 for your current location)
notes edit global 1 ... (edit global note 1)
notes edit server 3  (edit note 3 for your current server)

To see the indices for your notes, use the "notes" command."""
        location = cast(Location, location or Location(ctx.guild))

        async with ctx.bot.db.connect(writing=True) as conn:
            total = await query_note_count(conn, ctx.author.id, location.id)

            if total == 0:
                return await ctx.send(f"You don't have any {location.notes_in}.")
            elif not 0 < index <= total:
                return await self.send_invalid_indices(ctx, [str(index)], location, total)

            query = """
            SELECT note_id FROM note WHERE user_id = ? AND guild_id IS ?
            LIMIT 1 OFFSET ?
            """
            async with conn.execute(query, ctx.author.id, location.id, index - 1) as c:
                row = await c.fetchone()
                note_id: int = row['note_id']

            await conn.execute(
                'UPDATE note SET content = ? WHERE note_id = ?',
                content, note_id
            )

        await ctx.send(f"{location.note} #{index} successfully edited!".capitalize())

    @notes.command(name='remove', aliases=('delete',))
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def notes_remove(
        self, ctx: Context, location: Location | None,
        *, index: list[int] = index_converter()
    ):
        """Remove one or more notes.

Examples:
notes delete 1  (delete note 1 for your current location)
notes delete global 1, 5  (delete global notes 1 and 5)
notes delete server 3-8  (delete notes 3 through 8 for your current server)

To see the indices for your notes, use the "notes" command."""
        location = cast(Location, location or Location(ctx.guild))
        index: list[int]

        async with ctx.bot.db.connect() as conn:
            total = await query_note_count(conn, ctx.author.id, location.id)

            if total == 0:
                return await ctx.send(f"You already don't have any {location.notes_in}.")
            elif out_of_bounds := invalid_indices(total, index):
                return await self.send_invalid_indices(ctx, out_of_bounds, location, total)

        note_str = '{n} {notes}'.format(
            n=len(index),
            notes=location.notes_str if len(index) != 1 else location.note
        )

        view = ConfirmationView(ctx.author)
        await view.start(
            ctx,
            color=ctx.author.color.value or ctx.bot.get_bot_color(),
            title=f'Are you sure you want to delete {note_str}?'
        )

        if await view.wait_for_confirmation():
            async with ctx.bot.db.connect(writing=True) as conn:
                note_ids = [
                    (row['note_id'],)
                    async for row in yield_notes(
                        conn, ctx.author.id, location.id,
                        indices=index, only_ids=True
                    )
                ]

                await conn.executemany(
                    'DELETE FROM note WHERE note_id = ?',
                    note_ids
                )

            await view.update(f'{note_str} successfully deleted!', color=view.YES)
        else:
            await view.update('Cancelled note deletion.', color=view.NO)


async def setup(bot: TheGameBot):
    await bot.add_cog(NoteManagement(bot))
