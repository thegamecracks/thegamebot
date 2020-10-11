import discord
from discord.ext import commands


class Database(commands.Cog):
    qualified_name = 'Notes'
    description = 'Commands for saving notes.'

    def __init__(self, bot):
        self.bot = bot





    @commands.command(name='addnote')
    async def client_addnote(self, ctx, *, note):
        """Add a note."""
        print(f'Adding note for {ctx.author.id}:', note)





    @commands.command(name='removenote')
    async def client_removenote(self, ctx, note_number: int):
        """Remove a note.

To see a list of notes and their number, use the shownotes command."""
        print(f'Adding note for {ctx.author.id}:', note)





    @commands.command(name='shownotes')
    async def client_shownotes(self, ctx, *, note):
        """Show."""
        print(f'Adding note for {ctx.author.id}:', note)










def setup(bot):
    bot.add_cog(Database(bot))
