#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import discord
from discord.ext import commands


class ArrowButton(discord.ui.Button):
    def __init__(self, direction, **kwargs):
        super().__init__(
            style=discord.ButtonStyle.primary,
            **kwargs
        )
        self.direction = direction

    async def callback(self, interaction):
        link = 'https://discordpy.readthedocs.io/en/master/api.html#id11'
        await interaction.response.send_message(
            f'You clicked [{self.direction}]({link})!')
        # m = await interaction.followup.fetch_message('@original')
        # await m.edit(content='test')


class ArrowSelect(discord.ui.Select):
    def __init__(self, bot, *, row=None):
        super().__init__(
            placeholder='beep',
            options=[
                discord.SelectOption(label='up', description='uppity'),
                discord.SelectOption(label='down', description='downy'),
                discord.SelectOption(label='left', description='lefty'),
                discord.SelectOption(label='right', description='righty')
            ],
            max_values=4,
            row=row
        )
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        link = 'https://discordpy.readthedocs.io/en/master/api.html#select'
        await interaction.response.send_message(
            'You clicked [{}]({})!'.format(
                self.bot.inflector.join(self.values),
                link
            ),
            ephemeral=True
        )


class ArrowView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=60)
        self.message = None

        self.add_item(ArrowSelect(bot, row=0))
        self.add_empty(row=1)
        self.add_arrow('up', emoji='\N{UPWARDS BLACK ARROW}', row=1)
        self.add_empty(row=1)
        self.add_arrow('left', emoji='\N{LEFTWARDS BLACK ARROW}', row=2)
        self.add_arrow('down', emoji='\N{DOWNWARDS BLACK ARROW}', row=2)
        self.add_arrow('right', emoji='\N{BLACK RIGHTWARDS ARROW}', row=2)

    def add_arrow(self, direction, **kwargs):
        button = ArrowButton(direction, **kwargs)
        self.add_item(button)
        return button

    def add_empty(self, row=None):
        button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label='\u200b',
            disabled=True,
            row=row
        )
        self.add_item(button)
        return button

    async def on_timeout(self):
        await self.message.edit(content='buttons! timeout!', view=None)


class Testing(commands.Cog, command_attrs={'hidden': True}):
    """Testing commands."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return await ctx.bot.is_owner(ctx.author)

    @commands.group()
    async def foo(self, ctx):
        print('foo', ctx.invoked_subcommand)

    @foo.group()
    async def bar(self, ctx):
        print('  bar', ctx.invoked_subcommand)

    @bar.command(name='2000')
    async def _2000(self, ctx):
        print('    2000', ctx.invoked_subcommand)

    @commands.command()
    @commands.max_concurrency(1, commands.BucketType.default)
    async def buttons(self, ctx):
        """Buttons!"""
        view = ArrowView(ctx.bot)
        message = await ctx.send('buttons!', view=view)
        view.message = message
        await view.wait()










def setup(bot):
    bot.add_cog(Testing(bot))
