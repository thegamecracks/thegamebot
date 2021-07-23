#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import enum
import io
import os
import textwrap
from typing import Optional

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
import qrcode
import qrcode.exceptions

from bot import utils

CAT_API_URL = 'https://api.thecatapi.com/'
CAT_API_KEY = os.getenv('CatAPIKey')
DOG_API_URL = 'https://api.thedogapi.com/'
DOG_API_KEY = os.getenv('DogAPIKey')


async def query_thatapiguy(session, url, key):
    search = 'v1/images/search?mime_types=jpg,png'

    async with session.get(url + search, headers={'x-api-key': key}) as response:
        if response.status >= 400:
            raise ValueError(response.status, response.reason)

        # Acquire the json, disabling content-type check
        return (await response.json(content_type=None))[0]


def embed_thatapiguy(ctx, response: dict):
    return discord.Embed(
        color=utils.get_user_color(ctx.bot, ctx.author)
    ).set_footer(
        text=f'Requested by {ctx.author.name}',
        icon_url=ctx.author.avatar.url
    ).set_image(
        url=response['url']
    )


class QRCodeECL(enum.IntEnum):
    L = qrcode.ERROR_CORRECT_L
    M = qrcode.ERROR_CORRECT_M
    Q = qrcode.ERROR_CORRECT_Q
    H = qrcode.ERROR_CORRECT_H


class QRCodeECConverter(commands.Converter):
    """Convert to an error correction level for qrcode.QRCode."""
    async def convert(self, ctx, arg) -> QRCodeECL:
        arg = arg.strip().casefold()

        if arg in ('l', 'low'):
            return QRCodeECL.L
        elif arg in ('m', 'medium'):
            return QRCodeECL.M
        elif arg == 'q':
            return QRCodeECL.Q
        elif arg in ('h', 'high'):
            return QRCodeECL.H

        raise commands.UserInputError(f'Unknown error correction level: {arg!r}')


class QRCodeVersionConverter(commands.Converter):
    """Convert to a QR code version between 1 and 40."""
    async def convert(self, ctx, argument) -> int:
        try:
            n = int(argument)
        except ValueError:
            raise commands.UserInputError
        if 1 <= n <= 40:
            return n
        raise commands.UserInputError(f'Unknown QR code version: {n}')


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
                'Sorry, but the bot currently cannot query for a cat image.')
            return await asyncio.sleep(10)

        try:
            cat = await query_thatapiguy(
                ctx.bot.session, CAT_API_URL, CAT_API_KEY)
        except ValueError as e:
            return await ctx.send(
                f'Could not get a cat image; status code {e.args[1]}')

        await ctx.send(embed=embed_thatapiguy(ctx, cat))





    @commands.command(name='woof')
    @commands.cooldown(1, 20, commands.BucketType.channel)
    @commands.max_concurrency(3, wait=True)
    async def client_getdogimage(self, ctx):
        """\N{DOG FACE}"""
        if DOG_API_KEY is None:
            await ctx.send(
                'Sorry, but the bot currently cannot query for a dog image.')
            return await asyncio.sleep(10)

        try:
            dog = await query_thatapiguy(
                ctx.bot.session, DOG_API_URL, DOG_API_KEY)
        except ValueError as e:
            return await ctx.send(
                f'Failed to query a dog image; status code {e.args[1]}')

        await ctx.send(embed=embed_thatapiguy(ctx, dog))





    @commands.command(name='qrcode')
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.max_concurrency(3, wait=True)
    async def client_qrcode(
            self, ctx,
            version: Optional[QRCodeVersionConverter],
            ec_level: Optional[QRCodeECConverter], *, text):
        """Generate a QR code.

version: The QR code version to use (1-40). This corresponds to how much data can be held.
Every
If not given, uses the smallest version possible.
ec_level: The error correction level to use. The higher the level, the more dense the QR code will be.
If not given, defaults to Level M.
    L: up to 7% of errors can be corrected
    M: up to 15%
    Q: up to 25%
    H: up to 30%
text: The message to encode."""
        if ec_level is None:
            ec_level = QRCodeECL.M

        qr = qrcode.QRCode(
            version=version,
            error_correction=ec_level
        )
        qr.add_data(text)
        try:
            qr.make(fit=False)
        except qrcode.exceptions.DataOverflowError:
            s = 'Too much data to fit in the QR code.'
            if ec_level != qrcode.ERROR_CORRECT_L:
                s += ' Try lowering the error correction level.'
            return await ctx.send(s)

        img = await ctx.bot.loop.run_in_executor(None, qr.make_image)

        f = io.BytesIO()
        img.save(f, format='png')
        f.seek(0)

        await ctx.send(
            f'Version {qr.version} QR code with '
            f'error correction level {ec_level.name}:',
            file=discord.File(f, filename='qrcode.png')
        )





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
            return await ctx.send(ctx.bot.inflector.inflect(
                "Your text is {s} plural('character', {s}) too long.".format(
                    s=size)
            ))
        elif (size := text.count('\n') - 9) > 0:
            return await ctx.send(ctx.bot.inflector.inflect(
                "Your text is {s} plural('line', {s}) too long.".format(
                    s=size)
            ))

        f = await ctx.bot.loop.run_in_executor(
            None, self.write_amongustext, ctx,
            text, transparent
        )

        file = discord.File(f, filename='image.png')
        await ctx.send(file=file)










def setup(bot):
    bot.add_cog(Images(bot))
