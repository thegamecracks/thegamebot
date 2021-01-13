import asyncio
from typing import Optional

import discord
from discord.ext import commands

from bot.classes.confirmation import AdaptiveConfirmation
from bot.classes.games import blackjack
from bot.classes.games import multimath
from bot.classes import paginator
from bot.database import GameDatabase
from bot import utils


class Games(commands.Cog):
    qualified_name = 'Games'
    description = 'Commands with interactive games.'

    def __init__(self, bot):
        self.bot = bot
        self.gamedb = GameDatabase





    @commands.command(name='testpages')
    @commands.is_owner()
    @commands.max_concurrency(1, commands.BucketType.channel)
    async def client_testpages(self, ctx):
        """Create a simple paginator."""
        embeds = [
            discord.Embed(title="test page 1",
                description="This is just some test content!", color=0x115599),
            discord.Embed(title="test page 2",
                description="Nothing interesting here.", color=0x5599ff),
            discord.Embed(title="test page 3",
                description="Why are you still here?", color=0x191638)
        ]

        pages = paginator.RemovableReactBotEmbedPaginator(
            ctx, embeds)
        await pages.run()





    @commands.command(name='testconfirmation')
    @commands.is_owner()
    @commands.max_concurrency(1, commands.BucketType.channel)
    async def client_testconfirmation(self, ctx):
        """Create a test confirmation prompt."""
        prompt = AdaptiveConfirmation(ctx, utils.get_bot_color())

        confirmed = await prompt.confirm('Confirmation')

        if confirmed:
            await prompt.update('Confirmed', prompt.emoji_yes.color)
        else:
            await prompt.update('Cancelled', prompt.emoji_no.color)





    def get_members(self, ctx, players: str, members: list):
        """Take a players and greedy members argument and parse it
        for the users argument in games."""
        lower = players.lower()
        if lower == 'allow':
            if members:
                # Player whitelist
                members.append(ctx.author)
                return members
            # All players
            return True
        elif lower in ('me', 'all'):
            if members:
                # Argument error
                raise ValueError(
                    'You cannot specify which members can play if you do '
                    'not allow others. See the help message for more info.'
                )
            return None if lower == 'me' else True
        else:
            raise ValueError(f'Unknown input for "players": {players!r}')





    @commands.group(name='blackjack', aliases=('bj',), invoke_without_command=True)
    @commands.cooldown(4, 20, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel)
    async def client_blackjack(
            self, ctx,
            decks: Optional[int] = 2,
            players='me',
            members: commands.Greedy[discord.User] = None):
        """Answer simple multiple-choice math expressions.

If the first parameter says "allow", you can then specify which other members are allowed to play, by mention or name:
> blackjack allow Alice#1234 Bob
If no members are specified after "allow" or you type "all", anyone can play:
> blackjack allow
Otherwise, only you can play:
> blackjack"""
        if ctx.guild is None and not self.bot.intents.members:
            return await ctx.send('Unfortunately games will not work in DMs at this time.')
        elif decks < 1:
            return await ctx.send('The deck size must be at least one.')
        elif decks > 10:
            return await ctx.send('The deck size can only be ten at most.')

        try:
            users = self.get_members(ctx, players, members)
        except ValueError as e:
            return await ctx.send(e)

        game = blackjack.BotBlackjackGame(ctx, decks=decks)

        results = await game.run(users=users)

        if results.done:
            await self.gamedb.blackjack.change('played', ctx.author.id, 1)
        if results.player.maximum == 21:
            await self.gamedb.blackjack.change('blackjacks', ctx.author.id, 1)
        if results.winner:
            await self.gamedb.blackjack.change('wins', ctx.author.id, 1)
        elif results.winner is False:
            await self.gamedb.blackjack.change('losses', ctx.author.id, 1)





    @client_blackjack.group(name='stats', invoke_without_command=True)
    @commands.cooldown(2, 15, commands.BucketType.user)
    async def client_blackjack_stats(self, ctx):
        """View your blackjack stats."""
        db = self.gamedb.blackjack
        row = await db.get_blackjack_row(ctx.author.id)
        blackjacks = row['blackjacks']
        losses = row['losses']
        played = row['played']
        wins = row['wins']
        ties = played - wins - losses

        description = [
            f'Games played: {played:,}',
            f'Wins: {wins:,}',
            f'Losses: {losses:,}'
        ]
        if ties:
            description.append(f'Ties: {ties:,}')
        if blackjacks:
            description.append(f'Blackjacks: {blackjacks:,}')
        if played:
            rate = f'Win rate: {wins / played:.0%}'
            description.append(rate)
            if ties:
                description.append(
                    f'Win rate (no pushes): {wins / (played - ties):.0%}')

        description = '\n'.join(description)
        embed = discord.Embed(
            color=utils.get_user_color(ctx.author),
            description=description
        ).set_author(
            name=ctx.author.display_name,
            icon_url=ctx.author.avatar_url
        )

        await ctx.send(embed=embed)





    @client_blackjack.group(name='reset', invoke_without_command=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def client_blackjack_stats_reset(self, ctx):
        """Reset your blackjack stats."""
        prompt = AdaptiveConfirmation(ctx, utils.get_bot_color())

        confirmed = await prompt.confirm(
            'Are you sure you want to reset your blackjack stats?')

        if confirmed:
            await self.gamedb.delete_data(ctx.author.id)
            await prompt.update('Successfully wiped your stats!',
                                prompt.emoji_yes.color)
        else:
            await prompt.update('Cancelled reset.', prompt.emoji_no.color)





    @commands.command(name='multimath')
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.channel)
    async def client_multimath(
            self, ctx,
            players='me',
            members: commands.Greedy[discord.User] = None):
        """Answer simple multiple-choice math expressions.

If the first parameter says "allow", you can then specify which other members are allowed to play, by mention or name:
> multimath allow Alice#1234 Bob
If no members are specified after "allow" or you type "all", anyone can play:
> multimath allow
Otherwise, only you can play:
> multimath"""
        if ctx.guild is None and not self.bot.intents.members:
            return await ctx.send('Unfortunately games will not work in DMs at this time.')

        try:
            users = self.get_members(ctx, players, members)
        except ValueError as e:
            return await ctx.send(e)

        game = multimath.BotMultimathGame(ctx)

        await game.run(users=users)










def setup(bot):
    bot.add_cog(Games(bot))
