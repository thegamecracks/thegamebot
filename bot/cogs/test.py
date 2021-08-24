#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio

import discord
from discord.ext import commands


class TimeoutView(discord.ui.View):
    message: discord.Message

    async def on_timeout(self):
        await self.message.edit(view=None)


# latedefer
class SlowButton(discord.ui.Button):
    def __init__(self, duration: float, *args, **kwargs):
        super().__init__(*args, label=str(duration), **kwargs)
        self.duration = duration

    async def callback(self, interaction):
        await asyncio.sleep(self.duration)


class LateDeferView(TimeoutView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for i in range(1, 6):
            self.add_item(SlowButton(i))


# buttons
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


class ArrowView(TimeoutView):
    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)

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


# reveal
class RevealView(TimeoutView):

    @discord.ui.button(label='Reveal')
    async def on_reveal(self, button, interaction):
        self.add_item(discord.ui.Button(
            # style=discord.ButtonStyle.primary,
            emoji='\N{WRAPPED PRESENT}',
            url='https://discordpy.readthedocs.io/en/master/api.html#id11'
        ))
        await interaction.response.edit_message(view=self)


# ephemeral
class CountingButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=0
        )

    async def callback(self, interaction):
        self.label = int(self.label) + 1
        await interaction.response.edit_message(view=self.view)


class EphemeralSecondaryView(discord.ui.View):
    def __init__(self, interaction, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.interaction = interaction
        self.add_item(CountingButton())

    async def on_timeout(self):
        await self.interaction.edit_original_message(
            content='timeout',
            view=None
        )


class EphemeralPrimaryView(TimeoutView):
    @discord.ui.button(style=discord.ButtonStyle.primary, label='Send')
    async def on_send(self, button, interaction):
        await interaction.response.send_message(
            'ephemeral counter',
            view=EphemeralSecondaryView(interaction, timeout=5),
            ephemeral=True
        )


class Testing(commands.Cog, command_attrs={'hidden': True}):
    """Testing commands."""

    def __init__(self, bot):
        self.bot = bot

    # async def cog_check(self, ctx):
    #     return await ctx.bot.is_owner(ctx.author)

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
        view = ArrowView(ctx.bot, timeout=30)
        view.message = await ctx.send('buttons!', view=view)
        await view.wait()

    @commands.command()
    @commands.max_concurrency(1, commands.BucketType.default)
    async def ephemeral(self, ctx):
        view = EphemeralPrimaryView(timeout=30)
        view.message = await ctx.send('ephemeral buttons', view=view)
        await view.wait()

    @commands.command()
    @commands.max_concurrency(1, commands.BucketType.default)
    async def latedefer(self, ctx):
        view = LateDeferView(timeout=30)
        view.message = await ctx.send('Slow buttons!', view=view)
        await view.wait()

    @commands.command()
    @commands.max_concurrency(1, commands.BucketType.default)
    async def reveal(self, ctx):
        view = RevealView(timeout=30)
        view.message = await ctx.send('reveal menu', view=view)
        await view.wait()

    @commands.command()
    @commands.max_concurrency(1, commands.BucketType.default)
    async def wide(self, ctx):
        view = discord.ui.View(timeout=0)
        s = ['\u200b\u3000'] * 40
        t = 'Wide button!'
        for i, c in enumerate(t, len(s) // 2 - len(t) // 2):
            s[i] = c
        w = discord.ui.Button(label=''.join(s))
        view.add_item(w)
        for i in range(5):
            view.add_item(discord.ui.Button(label=i, row=1))
        await ctx.send('widey', view=view)
        view.stop()










def setup(bot):
    bot.add_cog(Testing(bot))
