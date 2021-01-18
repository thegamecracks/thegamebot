import asyncio
import collections
import contextlib
import decimal
import functools
import io
##import multiprocessing
from pathlib import Path
import random
import string
import textwrap
import typing
import warnings

import aiohttp
import discord
from discord.ext import commands
import humanize
import matplotlib
import matplotlib.animation as animation
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np

from bot import checks
from bot import utils


##def conn_wrapper(conn, func):
##    @functools.wraps
##    def wrapper(*args, **kwargs):
##        output = func(*args, **kwargs)
##        conn.send(output)
##        return output
##    return wrapper


def format_dollars(dollars: decimal.Decimal):
    dollars = round_dollars(dollars)
    sign = '-' if dollars < 0 else ''
    dollar_part = abs(int(dollars))
    cent_part = abs(int(dollars % 1 * 100))
    return '{}${:,}.{:02d}'.format(sign, dollar_part, cent_part)


class DollarConverter(commands.Converter):
    """A decimal.Decimal converter that strips leading dollar signs
    and can round to the nearest cent."""

    def __init__(self, *, nearest_cent=True):
        super().__init__()
        self.nearest_cent = nearest_cent

    async def convert(self, ctx, arg):
        arg = arg.lower()
        thousands = 1000 if arg.endswith('k') else 1
        arg = arg.replace(',', '').lstrip('$').rstrip('k')
        try:
            d = decimal.Decimal(arg) * thousands
        except decimal.InvalidOperation:
            raise commands.BadArgument(f'Dollar syntax error: {arg!r}')
        return round_dollars(d) if self.nearest_cent else d


class PercentConverter(commands.Converter):
    """A decimal.Decimal converter that supports specifying percentages."""
    async def convert(self, ctx, arg):
        try:
            if arg.endswith('%'):
                arg = arg.rstrip('%')
                return decimal.Decimal(arg) / 100
            return decimal.Decimal(arg)
        except decimal.InvalidOperation:
            raise commands.BadArgument(f'Decimal syntax error: {arg!r}')


def round_dollars(d) -> decimal.Decimal:
    """Round a number-like object to the nearest cent."""
    cent = decimal.Decimal('0.01')
    return decimal.Decimal(d).quantize(cent, rounding=decimal.ROUND_HALF_UP)


class Graphing(commands.Cog):
    qualified_name = 'Graphing'
    description = (
        'Commands for graphing things.\n'
        'Most of the text-related commands can support obtaining text by: '
        'the "text" parameter; file attachment; replying to a message; '
        'or the last message that was sent.'
    )

    TEXT_ANALYSIS_FILESIZE_LIMIT = 300_000
    # Maximum file size allowed for client_frequencyanalysis in number of bytes

    WORD_COUNT_NUM_TO_SHOW = 15
    # Number of words to be included in the graph; the rest are aggregated
    # into one entry

    TEXT_SHADOW_ALPHA = 0.6

    TEST_3D_GRAPH_ANIMATION_PATH = 'data/3D Graph Animation Test.gif'

    def __init__(self, bot):
        self.bot = bot





    async def get_text(self, ctx, text: str, *, message=None):
        """Obtain text from the user either in an attachment or from
        the text argument.

        Lookup strategy:
            1. Check the invoker's attachments for downloadable text files
            2. Check the invoker's content
            3. Check the referenced message's attachments (if available)
            4. Check the referenced message's content
            5. Check the last message's attachments (before the invokation)
            6. Check the last message's content
        Note that steps 3-6 are done via recursion. 

        Returns:
            Tuple[bool, str]:
                The boolean indicates whether it was successful at getting
                the input or not. If False, the following string should
                be sent to the user.

        """
        using_ctx_message = message is None
        if message is None:
            message = ctx.message

        if message.attachments:
            a = message.attachments[0]

            if a.width is not None:
                # Image/video file
                return False, 'Attachment must be a text file.'

            if a.size >= self.TEXT_ANALYSIS_FILESIZE_LIMIT:
                return (
                    False, 
                    'Unfortunately I cannot analyse files '
                    'over {} in size.'.format(
                        humanize.naturalsize(
                            self.TEXT_ANALYSIS_FILESIZE_LIMIT
                        )
                    )
                )

            text = (await a.read()).decode('utf-8')
            # Raises: discord.HTTPException, discord.Forbidden,
            # discord.NotFound, UnicodeError

        if not text and not using_ctx_message:
            # message argument was passed; check the message content
            # and if that is empty, keep it at one level of recursion
            text = message.content
            if not text:
                return False, 'There is no text to analyse.'

        ref = ctx.message.reference
        perms = ctx.me.permissions_in(ctx.channel)

        if not text and ref is not None:
            # Try recursing into the message the user replied to.
            # First check the cache, then fetch the message
            message = ref.resolved

            if isinstance(message, discord.DeletedReferencedMessage):
                return False, 'The given message was deleted.'
            elif message is None:
                return False, 'Could not resolve your replied message.'
            else:
                return await self.get_text(ctx, text, message=message)

        if not text and perms.read_message_history:
            # Try recursing into the last message sent
            # (will not work if there is no message before it or
            #  the bot is missing Read Message History perms)
            message = await ctx.channel.history(
                limit=1, before=ctx.message).flatten()

            if message:
                ref_text = await self.get_text(ctx, text, message=message[0])
                if ref_text[0] is True:
                    return ref_text

        if not text:
            response = 'There is no text to analyse.'
            if not perms.read_message_history:
                if ref is not None:
                    response = (
                        'I need the Read Message History permission to be '
                        'able to read the message you replied to.'
                    )
                else:
                    response = (
                        'I need the Read Message History permission to be '
                        'able to read the last message that was sent.'
                    )
            return False, response

        lowered_text = text.lower()
        if not any(c in lowered_text for c in string.ascii_lowercase):
            return False, 'There are no english letters in this text.'

        return True, text





    def interest_simple_compound(self, p, r, t, n):
        """Return a list of terms and a dictionary mapping the principal
        and interest over those terms."""
        terms = np.linspace(0, t, t * n, dtype=int)
        principal = np.full(terms.shape, p, dtype=decimal.Decimal)
        simple_interest = p * r * terms
        compound_amount = p * (1 + r/n) ** (n * terms)
        compound_interest = compound_amount - principal - simple_interest

        return terms, {
            'Principal': principal,
            'Simple': simple_interest,
            'Compound': compound_interest
        }


    def interest_stackplot(self, ctx, p, r, t, n):
        """Graph the interest of an investment over a given term.

        Args:
            ctx (discord.ext.commands.Context)
            p (decimal.Decimal): The principal.
            r (decimal.Decimal): The interest rate.
            t (int): The investment term.
            n (int): The number of compounding periods per term.

        Returns:
            Tuple[BytesIO, str]: The image and a message paired
                along with it.

        """
        bot_color = '#' + hex(utils.get_bot_color())[2:]

        terms, data = self.interest_simple_compound(p, r, t, n)

        fig, ax = plt.subplots()

        # Graph stackplot
        ax.stackplot(terms, data.values(), labels=data.keys())
        ax.legend(loc='upper left')

        # Move ylim so principal won't take up the majority of the plot
        simple_interest = data['Simple'][-1]
        compound_interest = data['Compound'][-1]
        maximum = p + simple_interest + compound_interest
        minimum = p - p * decimal.Decimal('0.05')
        ax.set_ylim([minimum, maximum])

        # Add labels
        ax.set_title('Simple and Compound Interest')
        ax.set_xlabel('Term')
        ax.set_ylabel('Amount')

        # Force integer ticks
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))

        # Set fonts
        labels = (
            [ax.title, ax.xaxis.label, ax.yaxis.label]
            + ax.get_legend().get_texts() + ax.get_xticklabels()
            + ax.get_yticklabels()
        )
        for item in labels:
            item.set_family('calibri')
            item.set_color(bot_color)
            item.set_fontsize(16)
        ax.title.set_fontsize(18)
        for item in labels:
            # Add shadow
            item.set_path_effects([
                path_effects.withSimplePatchShadow(
                    offset=(1, -1),
                    alpha=self.TEXT_SHADOW_ALPHA
                )
            ])

        # Hide the right and top spines
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)
        # Color the spines and ticks
        for spine in ax.spines.values():
            spine.set_color(bot_color)
        ax.tick_params(colors=bot_color)

        # Remove the x-axis margins
        ax.margins(x=0)

        # Create transparent background
        ax.set_facecolor('#00000000')
        fig.patch.set_facecolor('#36393F4D')

        # Create message
        simple_amount = p + simple_interest
        message = (
            'Present Value: {}\n'
            'Future Values: {} simple; {} compound'
        ).format(format_dollars(p), format_dollars(simple_amount),
                 format_dollars(maximum))

        f = io.BytesIO()
        fig.savefig(f, format='png', bbox_inches='tight', pad_inches=0)
        # bbox_inches, pad_inches: removes padding around the graph

        return f, message


    @commands.command(name='interest')
    @commands.cooldown(3, 60, commands.BucketType.channel)
    @commands.max_concurrency(3, wait=True)
    async def client_interest(
            self, ctx, principal: DollarConverter, rate: PercentConverter,
            term: int, periods: int = 1):
        """Calculate simple and compound interest.

principal: The initial investment.
rate: The interest rate. Can be specified as a percentage.
term: The number of terms.
periods: The number of compounding periods in each term."""
        if not 0 < rate <= 1:
            return await ctx.send(
                'The interest rate must be greater than 0% and under 100%.',
                delete_after=6
            )
        elif not 0 < term <= 100:
            return await ctx.send(
                'The term must be between 1 and 100.',
                delete_after=6
            )
        elif not 0 < periods <= 52:
            return await ctx.send(
                'The number of periods must be between 1 and 52.',
                delete_after=6
            )

        await ctx.trigger_typing()

        loop = asyncio.get_running_loop()

        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            f, content = await loop.run_in_executor(
                None, self.interest_stackplot, ctx,
                principal, rate, term, periods
            )
        f.seek(0)

        await ctx.send(
            content, file=discord.File(f, 'Word Count Pie Chart.png'))





##    def frequency_analysis(self, conn, ctx, text):
    def frequency_analysis(self, ctx, text):
        """Create a frequency analysis graph of a given text.

        Args:
            ctx (discord.ext.commands.Context)
            text (str)

        Returns:
            BytesIO

        """
        bot_color = '#' + hex(utils.get_bot_color())[2:]

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
            item.set_color(bot_color)
            # Add shadow
            item.set_path_effects([
                path_effects.withSimplePatchShadow(
                    offset=(1, -1),
                    alpha=self.TEXT_SHADOW_ALPHA
                )
            ])

        # Hide the right and top spines
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)
        # Color the spines and ticks
        for spine in ax.spines.values():
            spine.set_color(bot_color)
        ax.tick_params(colors=bot_color)

        # Create transparent background
        ax.set_facecolor('#00000000')
        fig.patch.set_facecolor('#36393F4D')

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

To see the different methods you can use to provide text, check the help message for this command's category."""
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
        bot_color = '#' + hex(utils.get_bot_color())[2:]

        text = text.lower()

        alphabet = frozenset(string.ascii_lowercase)
        chars_after_start = frozenset("'")
        words = collections.Counter()

        last_i = 0
        reading_word = False
        for i, c in enumerate(text):
            if c in alphabet or reading_word and c in chars_after_start:
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
        labels = [f'{word.capitalize()} ({count})'
                  for word, count in top_words]

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
                f'Word Count ({total_words:,} total)\n'
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
            item.set_color(bot_color)
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

To see the different methods you can use to provide text, check the help message for this command's category."""
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





    def test_bar_graphs_3d(self):
        """Generates four 2D bar graphs layered in a 3D plot.

        Code from: https://matplotlib.org/3.3.3/gallery/mplot3d/bars3d.html#sphx-glr-gallery-mplot3d-bars3d-py

        Returns:
            Tuple[Figure, Axes]

        """
        bot_color = '#' + hex(utils.get_bot_color())[2:]

        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')

        colors = ['r', 'g', 'b', 'y']
        yticks = [3, 2, 1, 0]
        scale = random.uniform(0.2, 100)
        for c, k in zip(colors, yticks):
            # Generate the random data for the y=k 'layer'.
            xs = np.arange(20)
            ys = np.random.rand(20) * scale

            # Plot the bar graph given by xs and ys on the plane y=k
            # with 80% opacity.
            ax.bar(xs, ys, zs=k, zdir='y', color=[c] * len(xs), alpha=0.8)

        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_zlabel('Z')

        # On the y axis let's only label the discrete values that
        # we have data for.
        ax.set_yticks(yticks)

        # Set fonts
        for item in ([ax.xaxis.label, ax.yaxis.label, ax.zaxis.label]
                     + ax.get_xticklabels() + ax.get_yticklabels()
                     + ax.get_zticklabels()):
            item.set_family('calibri')
            item.set_color(bot_color)

        # Set spine and pane colors
        for axis in (ax.w_xaxis, ax.w_yaxis, ax.w_zaxis):
            axis.line.set_color(bot_color)
            axis.set_pane_color((1, 1, 1, 0.1))

        # Set tick colors
        ax.tick_params(colors=bot_color)

        # Create transparent background
        ax.set_facecolor('#00000000')
        fig.patch.set_facecolor('#36393F4D')

        return fig, ax


    def test_bar_graphs_3d_image(self, elevation=None, azimuth=None):
        """Generates a PNG image from test_bar_graphs_3d.

        Returns:
            BytesIO

        """
        fig, ax = self.test_bar_graphs_3d()

        # Rotate graph projection
        ax.view_init(elevation, azimuth)

        f = io.BytesIO()
        fig.savefig(f, format='png', bbox_inches='tight', pad_inches=0)
        # bbox_inches, pad_inches: removes padding around the graph

        return f


    @commands.command(name='test3dgraph')
    @commands.cooldown(3, 120, commands.BucketType.channel)
    @commands.max_concurrency(3, wait=True)
    async def client_test3dgraph(
            self, ctx, elevation: int = None, azimuth: int = None):
        """Generate a graph with some random data."""
        await ctx.trigger_typing()

        loop = asyncio.get_running_loop()

        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            f = await loop.run_in_executor(
                None, self.test_bar_graphs_3d_image, elevation, azimuth)
        f.seek(0)

        await ctx.send(file=discord.File(f, '3D Graph Test.png'))





    def test_bar_graphs_3d_gif(
            self, fp=None, start=300, frames=30, direction=-1, duration=3):
        """Generates a rotating 3D plot GIF from test_bar_graphs_3d.

        Unfortunately there is no way to save these GIFs into memory, so
        the file has to be written to disk.

        Resources:
            FuncAnimation: https://matplotlib.org/api/_as_gen/matplotlib.animation.FuncAnimation.html
            Animating a rotating graph: https://stackoverflow.com/questions/18344934/animate-a-rotating-3d-graph-in-matplotlib
            Saving to GIF: https://holypython.com/how-to-save-matplotlib-animations-the-ultimate-guide/

        Args:
            fp (Optional[str]): The filepath to save the animation to.
                If not supplied, defaults to self.TEST_3D_GRAPH_ANIMATION_PATH.
            start (float): The azimuth to start at.
            frames (int): The number of azimuths to generate.
            direction (Literal[1, -1]):
                 1: Rotate right
                -1: Rotate left
            duration (float): The time in seconds for the animation to last.

        Returns:
            str: The filepath that the animation was saved to.

        """
        if fp is None:
            fp = self.TEST_3D_GRAPH_ANIMATION_PATH
        fig, ax = self.test_bar_graphs_3d()

        def azimuth_rotation():
            "Generates the azimuths rotating around the graph."
            step = direction * 360 / frames

            azimuth = start
            for _ in range(frames):
                yield azimuth
                azimuth += step

        def run(data):
            "Takes an azimuth from generate_azimuths."
            ax.view_init(elev=30, azim=data)
            return ()

        anim = animation.FuncAnimation(
            fig, run, list(azimuth_rotation()),
            interval=duration / frames,
            blit=True
        )

        anim.save(fp, writer='pillow', fps=frames / duration)

        return fp


    @commands.command(name='test3dgraphanimation')
    @commands.cooldown(1, 30, commands.BucketType.default)
    @commands.max_concurrency(1, wait=True)
    @checks.is_bot_owner()
    async def client_test3dgraphanimation(
            self, ctx, frames: int = 30, duration: int = 3):
        """Generate an animating graph with some random data."""
        loop = asyncio.get_running_loop()

        if duration < 1:
            return await ctx.send(
                'Duration must be at least 1 second.', delete_after=6)
        if frames < 1:
            return await ctx.send(
                'There must be at least 1 frame.', delete_after=6)

        func = functools.partial(
            self.test_bar_graphs_3d_gif,
            frames=frames,
            duration=duration
        )

        with ctx.typing():
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                fp = await loop.run_in_executor(None, func)

        filesize_limit = (ctx.guild.filesize_limit if ctx.guild is not None
                          else 8_000_000)
        filesize = Path(fp).stat().st_size
        if filesize > filesize_limit:
            return await ctx.send(
                'Unfortunately the file is too large to upload.',
                delete_after=10
            )

        with open(fp, 'rb') as f:
            await ctx.send(file=discord.File(f, '3D Graph Animation Test.gif'))










def setup(bot):
    bot.add_cog(Graphing(bot))
