import asyncio
import collections
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
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
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

    WORD_COUNT_NUM_TO_SHOW = 15
    # Number of words to be included in the graph; the rest are aggregated
    # into one entry

    TEXT_SHADOW_ALPHA = 0.6

    def __init__(self, bot):
        self.bot = bot





    async def get_text(self, ctx, text):
        """Obtain text from the user either in an attachment or from
        the text argument.

        Returns:
            Tuple[bool, str]:
                The boolean indicates whether it was successful at getting
                the input or not. If False, the following string should
                be sent to the user.

        """
        if ctx.message.attachments:
            a = ctx.message.attachments[0]

            if a.width is not None:
                # Image/video file
                return False, 'Attachment must be a text file.'

            if a.size >= self.FREQUENCY_ANALYSIS_FILESIZE_LIMIT:
                return (
                    False, 
                    'Unfortunately I cannot analyse files '
                    'over {} in size.'.format(
                        humanize.naturalsize(
                            self.FREQUENCY_ANALYSIS_FILESIZE_LIMIT
                        )
                    )
                )

            text = (await a.read()).decode('utf-8')
            # Raises: discord.HTTPException, discord.Forbidden,
            # discord.NotFound, UnicodeError

        if not text:
            return False, 'There is no text to analyse.'

        lowered_text = text.lower()
        if not any(c in lowered_text for c in string.ascii_lowercase):
            return False, 'There are no english letters in this text.'

        return True, text





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
        ax.set_title(f'Frequency Analysis for {ctx.author.display_name}')
        ax.set_xlabel('Letter')
        ax.set_ylabel('Count')

        # Force integer ticks
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))

        # Set fonts
        for item in ([ax.title, ax.xaxis.label, ax.yaxis.label]
                     + ax.get_xticklabels() + ax.get_yticklabels()):
            item.set_family('calibri')
            item.set_fontsize(18)
            item.set_color(get_bot_color_hex())
            # Add shadow
            item.set_path_effects([
                path_effects.withSimplePatchShadow(
                    offset=(1, -1),
                    alpha=self.TEXT_SHADOW_ALPHA
                )
            ])

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
    @commands.cooldown(3, 120, commands.BucketType.channel)
    @commands.max_concurrency(3, wait=True)
    async def client_frequencyanalysis(self, ctx, *, text=''):
        """Do a frequency analysis of a given text.
This only processes letters from the english alphabet.

Text can be provided in the command or as a file uploaded with the message."""
        success, text = await self.get_text(ctx, text)
        if not success:
            return await ctx.send(text)

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





    def word_count_pie(self, ctx, text):
        """Count the number of each word and return a pie chart.

        Args:
            ctx (discord.ext.commands.Context)
            text (str)

        Returns:
            BytesIO

        """
        text = text.lower()

        alphabet = frozenset(string.ascii_lowercase)
        words = collections.Counter()

        last_i = 0
        reading_word = False
        for i, c in enumerate(text):
            if c in alphabet:
                reading_word = True
            else:
                if reading_word:
                    words[text[last_i:i]] += 1
                last_i = i + 1
                reading_word = False
        else:
            if reading_word:
                words[text[last_i:]] += 1

        if not sum(words.values()):
            raise ValueError(
                'text must have some words using the english alphabet')

        top_words = words.most_common(self.WORD_COUNT_NUM_TO_SHOW)
        max_word_count = top_words[0][1]

        sizes = [count / max_word_count for word, count in top_words]
        labels = [f'{word.title()} ({count})' for word, count in top_words]

        word_colors = plt.cm.hsv([
            0.8 * i / len(top_words)
            for i in range(len(sizes), 0, -1)
        ])

        fig, ax = plt.subplots()

        # Graph pie
        total_words = sum(words.values())

##        if len(words) > len(top_words):
##            # Words were left out; add an "other" size
##            other_count = total_words - sum(count for word, count in top_words)
##            sizes.append(other_count / total_words)
##            labels.append(f'Other ({other_count})')
##            # Use #808080 (grey)
##            word_colors = np.append(word_colors, [[.5, .5, .5, 1]], 0)

        patches, texts, autotexts = ax.pie(
            sizes, labels=labels, colors=word_colors, autopct='%1.2g%%',
            startangle=0
        )
        # NOTE: `patches` are the wedges, `texts` are the labels, and
        # `autotexts` is the autogenerated labels in the wedges from autopct

        ax.axis('equal')  # keeps the pie's size as a circle

        # Add labels
        if len(words) <= len(top_words):
            ax.set_title(
                f'Top Words ({total_words:,} total)\n'
                f'for {ctx.author.display_name}\n'
            )
        else:
            # Words were left out
            ax.set_title(
                f'Top {self.WORD_COUNT_NUM_TO_SHOW} Words '
                f'({total_words:,} total)\n'
                f'for {ctx.author.display_name}\n'
            )
        # NOTE: newline is appended at the end just to pad it from the labels

        # Set fonts
        all_text = texts + autotexts
        for item in ([ax.title] + all_text):
            item.set_family('calibri')
            item.set_color('#FF8002')
        ax.title.set_fontsize(18)
        for item in all_text:
            # Add shadow
            item.set_path_effects([
                path_effects.withSimplePatchShadow(
                    offset=(1, -1),
                    alpha=self.TEXT_SHADOW_ALPHA
                )
            ])
        for item in texts:
            item.set_fontsize(16)
        for item in autotexts:
            item.set_fontsize(12)

        # Create transparent background
        ax.set_facecolor('#00000000')
        fig.patch.set_facecolor('#36393F4D')

        f = io.BytesIO()
        fig.savefig(f, format='png', bbox_inches='tight', pad_inches=0)
        # bbox_inches, pad_inches: removes padding around the graph

        return f


    @commands.command(name='wordcount')
    @commands.cooldown(3, 120, commands.BucketType.channel)
    @commands.max_concurrency(3, wait=True)
    async def client_wordcount(self, ctx, *, text=''):
        """Count the occurrences of each word in a given text.
This only processes letters from the english alphabet.

Text can be provided in the command or as a file uploaded with the message."""
        success, text = await self.get_text(ctx, text)
        if not success:
            return await ctx.send(text)

        await ctx.trigger_typing()

        loop = asyncio.get_running_loop()

        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            f = await loop.run_in_executor(
                None, self.word_count_pie, ctx, text)

        f.seek(0)

        await ctx.send(file=discord.File(f, 'Word Count Pie Chart.png'))










def setup(bot):
    bot.add_cog(Graphing(bot))
