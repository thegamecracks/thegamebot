import asyncio
import json
import io
import os
import random
import textwrap
from typing import Optional

import aiohttp
import discord
from discord.ext import commands
import inflect
from PIL import Image, ImageDraw, ImageFont

from bot import utils

CAT_API_URL = 'https://api.thecatapi.com/'
CAT_API_KEY = os.getenv('PyDiscordBotAPICatKey')
DOG_API_URL = 'https://api.thedogapi.com/'
DOG_API_KEY = os.getenv('PyDiscordBotAPIDogKey')

inflector = inflect.engine()


async def query_thatapiguy(url, key):
    search = 'v1/images/search?mime_types=jpg,png'

    async with aiohttp.ClientSession(
            headers={'x-api-key': key}) as session:
        async with session.get(url + search) as response:
            if response.status >= 400:
                raise ValueError(response.status, response.reason)

            # Acquire the json, disabling content-type check
            return (await response.json(content_type=None))[0]


def embed_thatapiguy(ctx, response: dict):
    return discord.Embed(
        color=utils.get_user_color(ctx.author)
    ).set_footer(
        text=f'Requested by {ctx.author.name}',
        icon_url=ctx.author.avatar_url
    ).set_image(
        url=response['url']
    )


class Images(commands.Cog):
    """Commands for getting images."""
    qualified_name = 'Images'

    BACKGROUND_DISCORD_TRANSPARENT = (54, 57, 63, 77)

    FONT_AMONGUS = 'data/fonts/AmongUs-Regular.ttf'

    WRITE_BORDER = 0.1
    # Specifies the border around write_* commands as a percentage.

    def __init__(self, bot):
        self.bot = bot





    @commands.command(name='meow')
    @commands.cooldown(1, 20, commands.BucketType.channel)
    @commands.max_concurrency(3, wait=True)
    async def client_getcatimage(self, ctx):
        """\N{CAT FACE}"""
        if CAT_API_KEY is None:
            await ctx.send(
                'Sorry, but the bot currently cannot query for a cat image.',
                delete_after=10
            )
            return await asyncio.sleep(10)

        await ctx.trigger_typing()

        try:
            cat = await query_thatapiguy(CAT_API_URL, CAT_API_KEY)
        except ValueError as e:
            return await ctx.send(
                f'Could not get a cat image; status code {e.args[1]}',
                delete_after=8
            )

        await ctx.send(embed=embed_thatapiguy(ctx, cat))





    @commands.command(name='woof')
    @commands.cooldown(1, 20, commands.BucketType.channel)
    @commands.max_concurrency(3, wait=True)
    async def client_getdogimage(self, ctx):
        """\N{DOG FACE}"""
        if DOG_API_KEY is None:
            await ctx.send(
                'Sorry, but the bot currently cannot query for a dog image.',
                delete_after=10
            )
            return await asyncio.sleep(10)

        await ctx.trigger_typing()

        try:
            dog = await query_thatapiguy(DOG_API_URL, DOG_API_KEY)
        except ValueError as e:
            return await ctx.send(
                f'Failed to query a dog image; status code {e.args[1]}',
                delete_after=8
            )

        await ctx.send(embed=embed_thatapiguy(ctx, dog))





    @staticmethod
    def get_text_size(s, font):
        """Determine the x and y sizes of text rendered with a given font.

        For some reason font.getsize() does not give proper numbers,
        at least with certain fonts like Among Us,
        so this calculates it using the max height and width of a line and
        the number of lines there are.

        """
        lines = s.split('\n')

        sizes = [font.getsize(line) for line in lines]
        width = max(x for x, y in sizes)
        height = max(y for x, y in sizes) * len(lines)

        return width, height


    @staticmethod
    def clean_amongustext(s, width=None):
        """Clean up text for the Among Us font."""
        # Uppercase and remove unknown characters
        whitelist = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZ \n')
        chars = [c.upper() for c in s if c.upper() in whitelist]
        s = ''.join(chars)

        # Wrap to given width while maintaining existing newlines
        if width is not None:
            lines = s.split('\n')
            for i, line in enumerate(lines):
                lines[i] = textwrap.fill(line, width=width)
            s = '\n'.join(lines)

        return s


    def write_amongustext(self, ctx, text, transparent=False):
        font = ImageFont.truetype(self.FONT_AMONGUS, 96)

        # Calculate image size and border around text
        x_size, y_size = self.get_text_size(text, font)
        x = y = round(min(x_size, y_size) * self.WRITE_BORDER)

        # Draw the text
        image_size = (x_size + x * 2, y_size + y * 2)
        if transparent:
            image = Image.new('RGBA', image_size, self.BACKGROUND_DISCORD_TRANSPARENT)
        else:
            image = Image.new('L', image_size, 255)

        draw = ImageDraw.Draw(image)
        draw.text((x, y), text, font=font)

        f = io.BytesIO()
        image.save(f, format='png')
        f.seek(0)

        return f


    @commands.command(name='amongus', aliases=('among',))
    @commands.cooldown(3, 15, commands.BucketType.channel)
    @commands.max_concurrency(3, wait=True)
    async def client_write_amongustext(
            self, ctx, transparent: Optional[bool] = False, *, text):
        """Write some text with an Among Us font. Max of 140 characters/10 lines.

Only alphabetic letters are supported.

Credits to Leona Sky for the free font: https://www.dafont.com/among-us.font"""
        text = self.clean_amongustext(text)

        if (length := len(text.replace(' ', ''))) == 0:
            return await ctx.send('Only alphabetic characters are allowed.')
        elif (size := length - 140) > 0:
            return await ctx.send(inflector.inflect(
                "Your text is {s} plural('character', {s}) too long.".format(
                    s=size)
            ))
        elif (size := text.count('\n') - 9) > 0:
            return await ctx.send(inflector.inflect(
                "Your text is {s} plural('line', {s}) too long.".format(
                    s=size)
            ))

        await ctx.trigger_typing()

        loop = asyncio.get_running_loop()

        f = await loop.run_in_executor(
            None, self.write_amongustext, ctx,
            text, transparent
        )

        file = discord.File(f, filename='image.png')
        await ctx.send(file=file)










def setup(bot):
    bot.add_cog(Images(bot))
