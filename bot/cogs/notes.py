import datetime
import textwrap

import discord
from discord.ext import commands
from discord_slash.utils import manage_commands
from discord_slash import cog_ext as dslash_cog
from discord_slash import SlashContext
import discord_slash as dslash

from bot import utils


class Notes(commands.Cog):
    """Commands for saving notes."""
    qualified_name = 'Notes'

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
        del self.cache[user_id]

    async def delete_note_by_note_id(self, note_id, pop=False):
        """Remove a note by note_id and update the cache."""
        deleted = await self.bot.dbnotes.delete_note_by_note_id(note_id, pop=True)

        updated_ids = frozenset(note['user_id'] for note in deleted)

        for user_id in updated_ids:
            del self.cache[user_id]

        return deleted if pop else None

    async def get_notes(self, user_id):
        notes = self.cache.get(user_id)

        if notes is None:
            # Uncached user; add them to cache
            notes = await self.bot.dbnotes.get_notes(user_id)
            self.cache[user_id] = notes

        return notes





    @commands.command(name='addnote')
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    async def client_addnote(self, ctx, *, note):
        """Store a note on the bot."""
        await ctx.channel.trigger_typing()

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





    @commands.command(name='removenote')
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    async def client_removenote(self, ctx, index: int):
        """Remove a note.

To see a list of your notes and their indices, use the shownotes command.
To remove several notes, use the removenotes command."""
        await ctx.channel.trigger_typing()

        note_list = await self.get_notes(ctx.author.id)

        if len(note_list) == 0:
            return await ctx.send("You already don't have any notes.")

        try:
            note = note_list[index - 1]
        except IndexError:
            await ctx.send('That note index does not exist.')
        else:
            await self.delete_note_by_note_id(note['note_id'])
            await ctx.send('Note successfully deleted!')


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
            await self.delete_note_by_note_id(note['note_id'])
            await ctx.send('Note successfully deleted!',
                           hidden=True)





    @commands.command(name='removenotes')
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    async def client_removenotes(self, ctx, indices):
        """Remove multiple notes.

You can remove "all" of your notes or remove only a section of it by specifying the start and end indices ("1-4").
To remove only one note, use the removenote command."""
        await ctx.channel.trigger_typing()

        note_list = await self.get_notes(ctx.author.id)

        if len(note_list) == 0:
            return await ctx.send("You already don't have any notes.")

        if indices.lower() == 'all':
            for note in note_list:
                await self.delete_note_by_note_id(note['note_id'])
            await ctx.send('Notes successfully deleted!')

        else:
            start, end = [int(n) for n in indices.split('-')]
            start -= 1
            if start < 0:
                return await ctx.send('Start must be 1 or greater.')
            elif end > len(note_list):
                return await ctx.send(
                    f'End must only go up to {len(note_list)}.')

            for i in range(start, end):
                note = note_list[i]
                await self.delete_note_by_note_id(note['note_id'])
            await ctx.send('Notes successfully deleted!')





    @commands.command(name='shownote')
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    async def client_shownote(self, ctx, index: int):
        """Show one of your notes."""
        await ctx.channel.trigger_typing()

        note_list = await self.get_notes(ctx.author.id)

        if len(note_list) == 0:
            return await ctx.send("You don't have any notes.")
        elif index < 1:
            return await ctx.send('Index must be 1 or greater.')

        try:
            note = note_list[index - 1]
        except IndexError:
            await ctx.send('That note index does not exist.')
        else:
            await ctx.send(embed=discord.Embed(
                title=f'Note #{index:,}',
                description=note['content'],
                color=utils.get_user_color(ctx.bot, ctx.author),
                timestamp=datetime.datetime.fromisoformat(
                    note['time_of_entry'])
            ))


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
            # Show all notes
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





    @commands.command(name='shownotes')
    @commands.cooldown(1, 15, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel, wait=True)
    async def client_shownotes(self, ctx):
        """Show all of your notes."""
        await ctx.channel.trigger_typing()

        note_list = await self.get_notes(ctx.author.id)

        if len(note_list) == 0:
            return await ctx.send("You don't have any notes.")

        # Create fields for each note, limiting them to 140 characters/5 lines
        fields = [
            utils.truncate_message(note['content'], 140, max_lines=5)
            for note in note_list
        ]
        color = utils.get_user_color(ctx.bot, ctx.author)

        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Notes",
            color=color,
            timestamp=datetime.datetime.now().astimezone()
        )

        for i, content in enumerate(fields, start=1):
            embed.add_field(name=f'Note {i:,}', value=content)

        await ctx.send(embed=embed)










def setup(bot):
    bot.add_cog(Notes(bot))
