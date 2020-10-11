import datetime
import textwrap

import discord
from discord.ext import commands
import inflect

from bot.database import NoteDatabase, dbconnection_users
from bot import utils

inflector = inflect.engine()


class Notes(commands.Cog):
    qualified_name = 'Notes'
    description = 'Commands for saving notes.'

    def __init__(self, bot):
        self.bot = bot
        self.notedb = NoteDatabase(dbconnection_users)





    @commands.command(name='addnote')
    async def client_addnote(self, ctx, *, note):
        """Add a note.

You can have a maximum of 20 notes."""
        await ctx.channel.trigger_typing()

        total_notes = len(self.notedb.get_notes(ctx.author.id))

        if total_notes < 20:
            content = discord.utils.escape_mentions(note)

            self.notedb.add_note(
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
    @utils.print_error
    async def client_addnote_error(self, ctx, error):
        await ctx.send('An error has occurred.')





    @commands.command(name='removenote')
    async def client_removenote(self, ctx, index: int):
        """Remove a note.

To see a list of your notes and their indices, use the shownotes command.
To remove several notes, use the removenotes command."""
        await ctx.channel.trigger_typing()

        note_list = self.notedb.get_notes(ctx.author.id)

        if len(note_list) == 0:
            await ctx.send("You already don't have any notes.")
            return

        try:
            note = note_list[index - 1]
        except IndexError:
            await ctx.send('That note index does not exist.')
        else:
            self.notedb.delete_note_by_note_id(note['note_id'])
            await ctx.send('Note successfully deleted!')


    @client_removenote.error
    @utils.print_error
    async def client_removenote_error(self, ctx, error):
        await ctx.send('An error has occurred.')





    @commands.command(name='removenotes')
    async def client_removenotes(self, ctx, indices):
        """Remove multiple notes.

You can remove "all" of your notes or remove only a section of it by specifying the start and end indices ("1-4").
To remove only one note, use the removenote command."""
        await ctx.channel.trigger_typing()

        note_list = self.notedb.get_notes(ctx.author.id)

        if len(note_list) == 0:
            await ctx.send("You already don't have any notes.")
            return

        if indices.lower() == 'all':
            for note in note_list:
                self.notedb.delete_note_by_note_id(note['note_id'])
            await ctx.send('Notes successfully deleted!')

        else:
            start, end = [int(n) for n in indices.split('-')]
            start -= 1
            if start < 0:
                await ctx.send('Start must be 1 or greater.')
                return
            elif end > len(note_list):
                await ctx.send(f'End must only go up to {len(note_list)}.')

            for i in range(start, end):
                note = note_list[i]
                self.notedb.delete_note_by_note_id(note['note_id'])
            await ctx.send('Notes successfully deleted!')


    @client_removenotes.error
    @utils.print_error
    async def client_removenotes_error(self, ctx, error):
        await ctx.send('An error has occurred.')





    @commands.command(name='shownote')
    async def client_shownote(self, ctx, index: int):
        """Show one of your notes."""
        await ctx.channel.trigger_typing()

        note_list = self.notedb.get_notes(ctx.author.id)

        if len(note_list) == 0:
            await ctx.send("You don't have any notes.")
            return

        try:
            note = note_list[index - 1]
        except IndexError:
            await ctx.send('That note index does not exist.')
        else:
            await ctx.send(embed=discord.Embed(
                title=f'Note #{index:,}',
                description=note['content'],
                color=ctx.author.color,
                timestamp=datetime.datetime.fromisoformat(
                    note['time_of_entry'])
            ))


    @client_shownote.error
    @utils.print_error
    async def client_shownote_error(self, ctx, error):
        await ctx.send('An error has occurred.')





    @commands.command(name='shownotes')
    async def client_shownotes(self, ctx):
        """Show all of your notes."""
        await ctx.channel.trigger_typing()

        note_list = self.notedb.get_notes(ctx.author.id)

        if len(note_list) == 0:
            await ctx.send("You don't have any notes.")
            return

        # Create fields for each note, limiting them to 140 characters/5 lines
        fields = [
            utils.truncate_message(note['content'], 140, size_lines=5)
            for note in note_list
        ]

        # Use user's role color if called in a server
        color = (ctx.author.color
                 if isinstance(ctx.author, discord.Member)
                 else 0xFF8002)

        embed = discord.Embed(
            title='Your Notes',
            color=color,
            timestamp=datetime.datetime.now().astimezone()
        )

        for i, content in enumerate(fields, start=1):
            embed.add_field(name=f'Note {i:,}', value=content)

        await ctx.send(embed=embed)


    @client_shownotes.error
    @utils.print_error
    async def client_shownotes_error(self, ctx, error):
        await ctx.send('An error has occurred.')










def setup(bot):
    bot.add_cog(Notes(bot))
