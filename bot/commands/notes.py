import datetime
import textwrap

import discord
from discord.ext import commands
import inflect

from bot.database import NoteDatabase, dbconn_users
from bot import utils

inflector = inflect.engine()


class Notes(commands.Cog):
    qualified_name = 'Notes'
    description = 'Commands for saving notes.'

    def __init__(self, bot):
        self.bot = bot
        self.notedb = NoteDatabase(dbconn_users)





    @commands.command(name='addnote')
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def client_addnote(self, ctx, *, note):
        """Add a note.

You can have a maximum of 20 notes."""
        await ctx.channel.trigger_typing()

        total_notes = len(await self.notedb.get_notes(ctx.author.id))

        if total_notes < 20:
            content = discord.utils.escape_mentions(note)

            await self.notedb.add_note(
                ctx.author.id, datetime.datetime.now().astimezone(), note,
                add_user=True
            )

            await ctx.send(
                'Your {} note has been added!'.format(
                    inflector.ordinal(total_notes + 1)
                )
            )
        else:
            await ctx.send(
                'Sorry, but you have reached your maximum limit of 20 notes.')


    @client_addnote.error
    async def client_addnote_error(self, ctx, error):
        error = getattr(error, 'original', error)





    @commands.command(name='removenote')
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def client_removenote(self, ctx, index: int):
        """Remove a note.

To see a list of your notes and their indices, use the shownotes command.
To remove several notes, use the removenotes command."""
        await ctx.channel.trigger_typing()

        note_list = await self.notedb.get_notes(ctx.author.id)

        if len(note_list) == 0:
            return await ctx.send("You already don't have any notes.")

        try:
            note = note_list[index - 1]
        except IndexError:
            await ctx.send('That note index does not exist.')
        else:
            await self.notedb.delete_note_by_note_id(note['note_id'])
            await ctx.send('Note successfully deleted!')


    @client_removenote.error
    async def client_removenote_error(self, ctx, error):
        error = getattr(error, 'original', error)





    @commands.command(name='removenotes')
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def client_removenotes(self, ctx, indices):
        """Remove multiple notes.

You can remove "all" of your notes or remove only a section of it by specifying the start and end indices ("1-4").
To remove only one note, use the removenote command."""
        await ctx.channel.trigger_typing()

        note_list = await self.notedb.get_notes(ctx.author.id)

        if len(note_list) == 0:
            return await ctx.send("You already don't have any notes.")

        if indices.lower() == 'all':
            for note in note_list:
                await self.notedb.delete_note_by_note_id(note['note_id'])
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
                await self.notedb.delete_note_by_note_id(note['note_id'])
            await ctx.send('Notes successfully deleted!')


    @client_removenotes.error
    async def client_removenotes_error(self, ctx, error):
        error = getattr(error, 'original', error)





    @commands.command(name='shownote')
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def client_shownote(self, ctx, index: int):
        """Show one of your notes."""
        await ctx.channel.trigger_typing()

        note_list = await self.notedb.get_notes(ctx.author.id)

        if len(note_list) == 0:
            return await ctx.send("You don't have any notes.")

        try:
            note = note_list[index - 1]
        except IndexError:
            await ctx.send('That note index does not exist.')
        else:
            await ctx.send(embed=discord.Embed(
                title=f'Note #{index:,}',
                description=note['content'],
                color=utils.get_user_color(ctx.author),
                timestamp=datetime.datetime.fromisoformat(
                    note['time_of_entry'])
            ))


    @client_shownote.error
    async def client_shownote_error(self, ctx, error):
        error = getattr(error, 'original', error)





    @commands.command(name='shownotes')
    @commands.cooldown(1, 15, commands.BucketType.user)
    @commands.cooldown(4, 40, commands.BucketType.channel)
    async def client_shownotes(self, ctx):
        """Show all of your notes."""
        await ctx.channel.trigger_typing()

        note_list = await self.notedb.get_notes(ctx.author.id)

        if len(note_list) == 0:
            return await ctx.send("You don't have any notes.")

        # Create fields for each note, limiting them to 140 characters/5 lines
        fields = [
            utils.truncate_message(note['content'], 140, size_lines=5)
            for note in note_list
        ]
        color = utils.get_user_color(ctx.author)

        embed = discord.Embed(
            title=f"{ctx.author.display_name}'s Notes",
            color=color,
            timestamp=datetime.datetime.now().astimezone()
        )

        for i, content in enumerate(fields, start=1):
            embed.add_field(name=f'Note {i:,}', value=content)

        await ctx.send(embed=embed)


    @client_shownotes.error
    async def client_shownotes_error(self, ctx, error):
        error = getattr(error, 'original', error)










def setup(bot):
    bot.add_cog(Notes(bot))
