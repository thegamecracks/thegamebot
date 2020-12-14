import asyncio
import functools
import io
import multiprocessing
import string
import typing
import warnings

import aiohttp
import discord
from discord.ext import commands
import humanize
import matplotlib.pyplot as plt
import numpy as np

from bot import utils


def conn_wrapper(conn, func):
    @functools.wraps
    def wrapper(*args, **kwargs):
        output = func(*args, **kwargs)
        conn.send(output)
        return output
    return wrapper


class Graphing(commands.Cog):
    qualified_name = 'Graphing'
    description = 'Commands for graphing certain things.'

    FREQUENCY_ANALYSIS_FILESIZE_LIMIT = 100_000
    # Maximum file size allowed for client_frequencyanalysis in number of bytes

    def __init__(self, bot):
        self.bot = bot


##    def frequency_analysis(self, conn, ctx, text):
    def frequency_analysis(self, ctx, text):
        """Create a frequency analysis graph of a given text.

        Args:
            ctx (discord.ext.commands.Context)
            text (str)

        Returns:
            BytesIO

        """
        def get_bot_color_hex():
            return '#' + hex(utils.get_bot_color())[2:]

        text = text.lower()

        char_count = [text.count(c) for c in string.ascii_lowercase]

        max_char_count = max(char_count)
        letter_colors = plt.cm.hsv(
            [0.8 * i / max_char_count for i in char_count]
        )

        fig, ax = plt.subplots()

        # Graph bars
        ax.bar(list(string.ascii_lowercase),
               char_count,
               color=letter_colors)
        # Remove ticks
        ax.tick_params(axis='x', bottom=False)
        # Add labels
        ax.set_title(
            f'Frequency Analysis for {ctx.author.display_name}',
            color='#FF8002')
        ax.set_xlabel('Letter', fontname='calibri', color=get_bot_color_hex())
        ax.set_ylabel('Count', fontname='calibri', color=get_bot_color_hex())

        # Create transparent background
        ax.set_facecolor('#00000000')
        fig.patch.set_facecolor('#36393F4D')

        # Hide the right and top spines
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)
        # Color the spines and ticks
        ax.spines['bottom'].set_color(get_bot_color_hex())
        ax.spines['left'].set_color(get_bot_color_hex())
        ax.tick_params(colors=get_bot_color_hex())

        f = io.BytesIO()
        fig.savefig(f, format='png', bbox_inches='tight', pad_inches=0)
        # bbox_inches, pad_inches: removes padding around the graph

##        conn.send(f)
        return f


    @commands.command(
        name='analysefrequency',
        aliases=('analyzefrequency', 'frequencyanalysis'))
    @commands.cooldown(2, 40, commands.BucketType.channel)
    @commands.max_concurrency(3, wait=True)
    async def client_frequencyanalysis(self, ctx, *, text=''):
        """Do a frequency analysis of a given text.
This only processes letters from the english alphabet.

Text can be provided in the command or as a file uploaded with the message."""
        if ctx.message.attachments:
            a = ctx.message.attachments[0]

            if a.width is not None:
                # Image/video file
                return await ctx.send('Attachment must be a text file.')

            if a.size >= self.FREQUENCY_ANALYSIS_FILESIZE_LIMIT:
                return await ctx.send(
                    'Unfortunately I cannot analyse files '
                    'over {} in size.'.format(
                        humanize.naturalsize(
                            self.FREQUENCY_ANALYSIS_FILESIZE_LIMIT)
                        )
                    )

            text = (await a.read()).decode('utf-8')
            # Raises: discord.HTTPException, discord.Forbidden,
            # discord.NotFound, UnicodeError

        if not text:
            return await ctx.send('There is no text to analyse.')

        lowered_text = text.lower()
        if not any(c in lowered_text for c in string.ascii_lowercase):
            return await ctx.send('There are no english letters in this text.')

        await ctx.trigger_typing()

        loop = asyncio.get_running_loop()
##
##        parent_conn, child_conn = multiprocessing.Pipe()
##        p = multiprocessing.Process(
##            target=self.frequency_analysis,
##            args=(child_conn, ctx, text)
##        )
##        p.start()
##
##        await loop.run_in_executor(None, p.join)
##        f = parent_conn.recv()
##        parent_conn.close()
##        child_conn.close()

        with warnings.catch_warnings():
            # Suppress warning from matplotlib saying that opening GUI
            # in alternate thread will likely fail; we are only saving
            # the figure to be uploaded, not showing it
            warnings.simplefilter('ignore', UserWarning)
            f = await loop.run_in_executor(
                None, self.frequency_analysis, ctx, text)

        f.seek(0)

        await ctx.send(file=discord.File(f, 'Frequency Analysis.png'))










def setup(bot):
    bot.add_cog(Graphing(bot))
