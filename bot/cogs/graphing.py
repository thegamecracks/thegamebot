#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import collections
import datetime
import decimal
from decimal import Decimal
import io
import itertools
from pathlib import Path
import random
import string
from typing import Literal

import discord
from discord.ext import commands
import humanize
import matplotlib
from matplotlib.axes import Axes
from matplotlib.figure import Figure
import matplotlib.animation as animation
from matplotlib import dates as mdates
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np

from bot import utils
from main import Context, TheGameBot


def format_dollars(dollars: Decimal):
    dollars = round_dollars(dollars)
    sign = '-' if dollars < 0 else ''
    dollar_part = abs(int(dollars))
    cent_part = abs(int(dollars % 1 * 100))
    return '{}${:,}.{:02d}'.format(sign, dollar_part, cent_part)


class DollarConverter(commands.Converter):
    """A :class:`decimal.Decimal` converter that strips leading dollar signs
    and can round to the nearest cent.
    """

    def __init__(self, *, nearest_cent=True):
        super().__init__()
        self.nearest_cent = nearest_cent

    async def convert(self, ctx, arg):
        arg = arg.lower()
        thousands = 1000 if arg.endswith('k') else 1
        arg = arg.replace(',', '').lstrip('$').rstrip('k')
        try:
            d = Decimal(arg) * thousands
        except decimal.InvalidOperation:
            raise commands.BadArgument(f'Dollar syntax error: {arg!r}')
        return round_dollars(d) if self.nearest_cent else d


class PercentConverter(commands.Converter):
    """A Decimal converter that supports specifying percentages."""
    async def convert(self, ctx, arg):
        try:
            if arg.endswith('%'):
                arg = arg.rstrip('%')
                return Decimal(arg) / 100
            return Decimal(arg)
        except decimal.InvalidOperation:
            raise commands.BadArgument(f'Decimal syntax error: {arg!r}')


def round_dollars(d) -> Decimal:
    """Rounds a number-like object to the nearest cent."""
    cent = Decimal('0.01')
    return Decimal(d).quantize(cent, rounding=decimal.ROUND_HALF_UP)


def interest_simple_compound(p: Decimal, r: Decimal, t: int, n: int):
    """Returns a list of terms and a dictionary mapping the principal
    and interest over those terms.

    :param p: The principal.
    :param r: The interest rate.
    :param t: The investment term.
    :param n: The number of compounding periods per term.

    """
    samples = t*n + 1

    terms = np.linspace(0, t, samples)

    # Decimal() arrays can't be created with linspace()
    # (see numpy #8909), so this linear space has to be done manually.
    payments = np.ndarray((samples,), dtype=Decimal)
    start = Decimal()
    step = Decimal(t) / (t * n)
    for i in range(samples):
        payments[i] = start
        start += step

    principal = np.full(terms.shape, p, dtype=Decimal)

    simple_interest = p * r * payments
    compound_amount = p * (1 + r/n) ** (n * payments)
    compound_interest = compound_amount - principal - simple_interest

    return terms, {
        'Principal': principal,
        'Simple': simple_interest,
        'Compound': compound_interest
    }


def interest_stackplot(
    ctx: Context, p: Decimal, r: Decimal, t: int, n: int
) -> tuple[io.BytesIO, str]:
    """Graphs the interest of an investment over a given term.

    :param ctx: The command context.
    :param p: The principal.
    :param r: The interest rate.
    :param t: The investment term.
    :param n: The number of compounding periods per term.
    :returns: The generated image and a message describing the interest.

    """
    bot_color = '#' + hex(ctx.bot.get_bot_color())[2:]

    terms, data = interest_simple_compound(p, r, t, n)

    fig: Figure
    ax: Axes
    fig, ax = plt.subplots()

    # Graph stack plot
    ax.stackplot(terms, data.values(), labels=data.keys())
    ax.legend(loc='upper left')

    # Move y-lim so principal won't take up the majority of the plot
    simple_interest = data['Simple'][-1]
    compound_interest = data['Compound'][-1]
    maximum = p + simple_interest + compound_interest
    minimum = p - p * Decimal('0.05')
    ax.set_ylim(float(minimum), float(maximum))

    # Add labels
    ax.set_title('Simple and Compound Interest')
    ax.set_xlabel('Term')
    ax.set_ylabel('Amount')

    # Remove the x-axis margins
    ax.margins(x=0)

    # Force integer ticks
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))

    # Set colors and add shadow to labels
    for item in itertools.chain(
            (ax.title, ax.xaxis.label, ax.yaxis.label),
            ax.get_xticklabels(), ax.get_yticklabels(),
            ax.get_legend().get_texts()):
        item.set_color(bot_color)
        item.set_path_effects([
            path_effects.withSimplePatchShadow(
                offset=(1, -1),
                alpha=Graphing.TEXT_SHADOW_ALPHA
            )
        ])

    # Color the spines and ticks
    for spine in ax.spines.values():
        spine.set_color(bot_color)
    ax.tick_params(colors=bot_color)

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
    f.seek(0)

    plt.close(fig)
    return f, message


def frequency_analysis(ctx: Context, text: str):
    """Creates a frequency analysis graph of a given text."""
    bot_color = '#' + hex(ctx.bot.get_bot_color())[2:]

    text = text.lower()

    char_count = [text.count(c) for c in string.ascii_lowercase]

    max_char_count = max(char_count)
    letter_colors = plt.cm.hsv(
        [0.8 * i / max_char_count for i in char_count]
    )

    fig: Figure
    ax: Axes
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

    # Set colors and add shadow to labels
    for item in itertools.chain(
            (ax.title, ax.xaxis.label, ax.yaxis.label),
            ax.get_xticklabels(), ax.get_yticklabels()):
        item.set_color(bot_color)
        item.set_path_effects([
            path_effects.withSimplePatchShadow(
                offset=(1, -1),
                alpha=Graphing.TEXT_SHADOW_ALPHA
            )
        ])

    # Color the spines and ticks
    for spine in ax.spines.values():
        spine.set_color(bot_color)
    ax.tick_params(colors=bot_color)

    f = io.BytesIO()
    fig.savefig(f, format='png', bbox_inches='tight', pad_inches=0)
    # bbox_inches, pad_inches: removes padding around the graph
    f.seek(0)

    plt.close(fig)
    return f


def word_count_pie(ctx: Context, text: str, max_words: int = 15):
    """Count the number of each word and return a pie chart.

    :param ctx: The command context.
    :param text: The text to summarize.
    :param max_words: The max number of words to display in the graph.
        All other words are aggregated into one slice.
    :returns: The generated image as an in-memory file.

    """
    bot_color = '#' + hex(ctx.bot.get_bot_color())[2:]

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

    top_words = words.most_common(max_words)
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

    # if len(words) > len(top_words):
    #     # Words were left out; add an "other" size
    #     other_count = total_words - sum(count for word, count in top_words)
    #     sizes.append(other_count / total_words)
    #     labels.append(f'Other ({other_count})')
    #     # Use #808080 (grey)
    #     word_colors = np.append(word_colors, [[.5, .5, .5, 1]], 0)

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
            f'Top {max_words} Words '
            f'({total_words:,} total)\n'
            f'for {ctx.author.display_name}\n'
        )
    # NOTE: newline is appended at the end just to pad it from the labels

    # Set font styles
    all_text = texts + autotexts
    for item in ([ax.title] + all_text):
        item.set_color(bot_color)
    for item in all_text:
        # Add shadow
        item.set_path_effects([
            path_effects.withSimplePatchShadow(
                offset=(1, -1),
                alpha=Graphing.TEXT_SHADOW_ALPHA
            )
        ])
    for item in texts:
        item.set_fontsize(16)
    for item in autotexts:
        item.set_fontsize(12)

    f = io.BytesIO()
    fig.savefig(f, format='png', bbox_inches='tight', pad_inches=0)
    # bbox_inches, pad_inches: removes padding around the graph
    f.seek(0)

    plt.close(fig)
    return f


def test_bar_graphs_3d_plot(bot: TheGameBot) -> tuple[Figure, Axes]:
    """Generates four 2D bar graphs layered in a 3D plot.

    Code from: https://matplotlib.org/3.3.3/gallery/mplot3d/bars3d.html#sphx-glr-gallery-mplot3d-bars3d-py

    """
    bot_color = '#' + hex(bot.get_bot_color())[2:]

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

    # Set colors
    for item in itertools.chain(
            (ax.xaxis.label, ax.yaxis.label, ax.zaxis.label),
            ax.get_xticklabels(), ax.get_yticklabels(),
            ax.get_zticklabels()):
        item.set_color(bot_color)

    # Set spine and pane colors
    for axis in (ax.w_xaxis, ax.w_yaxis, ax.w_zaxis):
        axis.line.set_color(bot_color)
        axis.set_pane_color((1, 1, 1, 0.1))

    # Set tick colors
    ax.tick_params(colors=bot_color)

    return fig, ax


def test_bar_graphs_3d_image(bot: TheGameBot, elevation=None, azimuth=None):
    """Generates a PNG image from test_bar_graphs_3d."""
    fig, ax = test_bar_graphs_3d_plot(bot)

    # Rotate graph projection
    ax.view_init(elevation, azimuth)

    f = io.BytesIO()
    fig.savefig(f, format='png', bbox_inches='tight', pad_inches=0)
    # bbox_inches, pad_inches: removes padding around the graph
    f.seek(0)

    plt.close(fig)
    return f


def test_bar_graphs_3d_gif(
    bot: TheGameBot, fp: str,
    start=300, frames=30,
    direction: Literal[1, -1] = -1,
    duration=3
):
    """Generates a rotating 3D plot GIF from test_bar_graphs_3d.

    Unfortunately there is no way to save these GIFs into memory, so
    the file has to be written to disk.

    Resources:
        FuncAnimation: https://matplotlib.org/api/_as_gen/matplotlib.animation.FuncAnimation.html
        Animating a rotating graph: https://stackoverflow.com/questions/18344934/animate-a-rotating-3d-graph-in-matplotlib
        Saving to GIF: https://holypython.com/how-to-save-matplotlib-animations-the-ultimate-guide/

    :param fp: The filepath to save the animation to.
    :param start: The azimuth to start at.
    :param frames: The number of azimuths to generate.
    :param direction:
         1: Rotate right
        -1: Rotate left
    :param duration: The time span the animation should last in seconds.

    """
    fig, ax = test_bar_graphs_3d_plot(bot)

    def azimuth_rotation():
        """Generates the azimuths rotating around the graph."""
        step = direction * 360 / frames

        azimuth = start
        for _ in range(frames):
            yield azimuth
            azimuth += step

    def run(data):
        """Takes an azimuth from generate_azimuths."""
        ax.view_init(elev=30, azim=data)
        return ()

    anim = animation.FuncAnimation(
        fig, run, list(azimuth_rotation()),
        interval=duration / frames,
        blit=True
    )

    anim.save(fp, writer='pillow', fps=frames / duration)

    plt.close(fig)


class Graphing(commands.Cog):
    """Commands for graphing things.
Most of the text-related commands can support obtaining text using:
the "text" parameter; file attachment; replying to a message;
or using the last message that was sent."""
    qualified_name = 'Graphing'

    TEXT_ANALYSIS_FILESIZE_LIMIT = 300_000
    # Maximum file size allowed for client_frequencyanalysis in number of bytes

    WORD_COUNT_NUM_TO_SHOW = 15
    # Number of words to be included in the graph; the rest are aggregated
    # into one entry

    TEXT_SHADOW_ALPHA = 0.6

    TEST_3D_GRAPH_ANIMATION_PATH = 'data/3D Graph Animation Test.gif'

    def __init__(self, bot: TheGameBot):
        self.bot = bot

    def RelativeDateFormatter(
            self, now=None, unit=None, when_absolute=None,
            absolute_fmt='%Y-%m-d'):
        """Format a matplotlib date as a relative time.

        Args:
            now (Optional[datetime.datetime]):
                The current time. Works with timezones.
            unit (Optional[str]): The unit of time to use for relative formatting.
                Can be one of 'second', 'minute', 'hour', 'day', or None
                to use automatic units (may result in duplicate tick labels).
            when_absolute (Optional[int]): Formats datetimes as absolute when
                the difference from now is greater than this number of seconds.
            absolute_fmt (str): The format to use for absolute datetimes.

        """
        units_mapping = {
            'day': 86400,
            'hour': 3600,
            'minute': 60,
            'second': 1
        }
        now = now or datetime.datetime.now().astimezone(datetime.timezone.utc)
        if now.tzinfo != datetime.timezone.utc:
            now = now.astimezone(datetime.timezone.utc)

        def actual_relative_formatter(x, pos):
            def get_unit():
                n = units_mapping.get(unit)
                if n is not None:
                    return unit, n

                for name, n in units_mapping.items():
                    if seconds // n:
                        return name, n

                return 'second', 1

            def format_relative():
                name, n = get_unit()
                converted = int(seconds // n)
                return '{:,d} {}{}\nago'.format(
                    converted,
                    name,
                    's' if n != 1 else ''
                )

            dt = mdates.num2date(x)
            seconds = (now - dt).total_seconds()

            if when_absolute is not None and seconds > when_absolute:
                return dt.strftime(absolute_fmt)

            return format_relative()

        return actual_relative_formatter

    async def get_text(
        self, ctx: Context, text: str, *, message: discord.Message = None
    ) -> tuple[bool, str]:
        """Obtains text from the user, either in an attachment or from
        the text argument.

        Lookup strategy::
            1. Check the invoker's attachments for downloadable text files
            2. Check the invoker's content
            3. Check the referenced message's attachments (if available)
            4. Check the referenced message's content
            5. Check the last message's attachments (before the invokation)
            6. Check the last message's content
        Note that steps 3-6 are done via recursion. 

        :param ctx: The command context.
        :param text: The text argument passed to the command.
            If this is not empty, it is simply used as the result.
        :param message: The
        :returns:
            A boolean indicating whether it was successful at getting
            the input, along with a string which is either the retrieved
            content or a failure message.

        """
        if text:
            return True, text

        using_ctx_message = message is None
        message = message or ctx.message

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
            # discord.NotFound, UnicodeDecodeError

        if not text and not using_ctx_message:
            # message argument was passed; check the message content
            # and if that is empty, keep it at one level of recursion
            text = message.content
            if not text:
                return False, 'There is no text to analyse.'

        ref = ctx.message.reference
        perms = ctx.channel.permissions_for(ctx.me)

        if not text and ref is not None:
            # Try recursing into the message the user replied to
            message = ref.resolved

            if isinstance(message, discord.DeletedReferencedMessage):
                return False, 'The given message was deleted.'
            elif message is None:
                return False, 'Could not resolve your replied message.'
            else:
                return await self.get_text(ctx, text, message=message)

        if not text and perms.read_message_history:
            # Try recursing into the last message sent
            message = await anext(
                ctx.channel.history(limit=1, before=ctx.message)
            )

            if message is not None:
                success, last_text = await self.get_text(ctx, text, message=message)
                if success:
                    return success, last_text

        if not text:
            response = 'There is no text to analyse.'
            if not perms.read_message_history:
                if ref is not None:
                    response = (
                        'I need the Read Message History permission to '
                        'read the message you replied to.'
                    )
                else:
                    response = (
                        'I need the Read Message History permission to '
                        'read the last message that was sent.'
                    )
            return False, response

        lowered_text = text.lower()
        if not any(c in lowered_text for c in string.ascii_lowercase):
            return False, 'There are no english letters in this text.'

        return True, text

    @staticmethod
    def set_axes_aspect(ax: Axes, ratio: int | float, *args, **kwargs):
        """Set an Axes's aspect ratio.

        This is based off of https://www.statology.org/matplotlib-aspect-ratio/.

        :param ax: The Axes to set the aspect ratio for.
        :type ax: matplotlib.axes.Axes
        :param ratio: The ratio of height to width,
            i.e. a ratio of 2 will make the height 2 times the width.
        
        Extra arguments are passed through to `ax.set_aspect()`.

        """
        x_left, x_right = ax.get_xlim()
        y_low, y_high = ax.get_ylim()
        x_size = x_right - x_left
        y_size = y_low - y_high
        current_ratio = abs(x_size / y_size)
        ax.set_aspect(
            current_ratio * ratio,  # type: ignore # aspect can be a float
            *args, **kwargs
        )

    @commands.command(name='interest')
    @commands.cooldown(3, 60, commands.BucketType.channel)
    @commands.max_concurrency(3, wait=True)
    async def graph_interest(
        self, ctx: Context,
        principal: DollarConverter,
        rate: PercentConverter,
        term: int,
        periods: int = 1
    ):
        """Calculate simple and compound interest.

principal: The initial investment.
rate: The interest rate. Can be specified as a percentage.
term: The number of terms.
periods: The number of compounding periods in each term."""
        principal: int
        rate: Decimal
        if not 0 < rate <= 100:
            return await ctx.send(
                'The interest rate must be between 0% and 100,000%.')
        elif term * periods > min(36500.0, 36500000 / principal):
            # This tries keeping the numbers within a reasonable amount
            return await ctx.send(
                'The principal/term/periods are too large to calculate.')

        async with ctx.typing():
            f, content = await asyncio.to_thread(
                interest_stackplot,
                ctx, principal, rate, term, periods
            )

        await ctx.send(
            content, file=discord.File(f, 'Word Count Pie Chart.png'))

    @graph_interest.error
    async def graph_interest_error(self, ctx: Context, error):
        error = getattr(error, 'original', error)

        if isinstance(error, decimal.InvalidOperation):
            await ctx.send('The calculations were too large to handle...')
            ctx.handled = True

    @commands.command(
        name='frequencyanalysis',
        aliases=('analyzefrequency', 'analysefrequency')
    )
    @commands.cooldown(3, 120, commands.BucketType.channel)
    @commands.max_concurrency(3, wait=True)
    async def graph_frequency_analysis(self, ctx: Context, *, text=''):
        """Do a frequency analysis of a given text in the english alphabet.

To see the different methods you can use to provide text, check the help message for this command's category."""
        success, text = await self.get_text(ctx, text)
        if not success:
            return await ctx.send(text)

        async with ctx.typing():
            f = await asyncio.to_thread(frequency_analysis, ctx, text)

        await ctx.send(file=discord.File(f, 'Frequency Analysis.png'))

    @commands.command(name='wordcount')
    @commands.cooldown(3, 120, commands.BucketType.channel)
    @commands.max_concurrency(3, wait=True)
    async def graph_word_count(self, ctx: Context, *, text=''):
        """Count the occurrences of each word in a given text.
This only processes letters from the english alphabet.

To see the different methods you can use to provide text, check the help message for this command's category."""
        success, text = await self.get_text(ctx, text)
        if not success:
            return await ctx.send(text)

        async with ctx.typing():
            f = await asyncio.to_thread(word_count_pie, ctx, text)

        await ctx.send(file=discord.File(f, 'Word Count Pie Chart.png'))

    @commands.command(name='test3dgraph')
    @commands.cooldown(3, 120, commands.BucketType.channel)
    @commands.max_concurrency(3, wait=True)
    async def graph_3d_test(
        self, ctx: Context, elevation: int = None, azimuth: int = None
    ):
        """Generate a graph with some random data."""
        async with ctx.typing():
            f = await asyncio.to_thread(
                test_bar_graphs_3d_image,
                ctx.bot, elevation, azimuth
            )

        await ctx.send(file=discord.File(f, '3D Graph Test.png'))

    @commands.command(name='test3dgraphanimation')
    @commands.cooldown(1, 30, commands.BucketType.default)
    @commands.max_concurrency(1, wait=True)
    @commands.is_owner()
    async def graph_3d_animation_test(
        self, ctx: Context, frames: int = 30, duration: int = 3
    ):
        """Generate an animating graph with some random data."""
        if duration < 1:
            return await ctx.send('Duration must be at least 1 second.')
        if frames < 1:
            return await ctx.send('There must be at least 1 frame.')

        path = self.TEST_3D_GRAPH_ANIMATION_PATH

        async with ctx.typing():
            await asyncio.to_thread(
                test_bar_graphs_3d_gif,
                ctx.bot, path, frames=frames, duration=duration
            )

        filesize_limit = (ctx.guild.filesize_limit if ctx.guild is not None
                          else 8_000_000)
        filesize = Path(path).stat().st_size
        if filesize > filesize_limit:
            return await ctx.send(
                'Unfortunately the file is too large to upload.')

        await ctx.send(file=discord.File(path, '3D Graph Animation Test.gif'))


async def setup(bot: TheGameBot):
    await bot.add_cog(Graphing(bot))
