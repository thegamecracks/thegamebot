import asyncio
import random

from discord.ext import commands
from discord_slash.utils import manage_commands
from discord_slash import cog_ext as dslash_cog
from discord_slash import SlashContext

from bot import utils

CLIENT_EIGHTBALL = (
    'It is certain.',
    'It is decidedly so.',
    'Without a doubt.',
    'Yes - definitely.',
    'You may rely on it.',
    'As I see it, yes.',
    'Most likely.',
    'Outlook good.',
    'Yes.',
    'Signs point to yes.',

    'Reply hazy, try again.',
    'Ask again later.',
    'Better not tell you now.',
    'Cannot predict now.',
    'Concentrate and ask again.',

    "Don't count on it.",
    'My reply is no.',
    'My sources say no.',
    'Outlook not so good.',
    'Very doubtful.'
)
CLIENT_PICK_DIALOGUE = (
    'I choose {choice}.',
    'I pick {choice}.',
    'I select {choice}.',
    'My choice is {choice}.'
)


class DiceConverter(commands.Converter):
    """Convert a dice into a tuple of (number, sides)."""
    async def convert(self, ctx, argument):
        if 'd' in argument:
            number, sides = argument.split('d')
            number = int(number) if number else 1
            sides = int(sides) if sides else 6
        else:
            # implied sides
            number, sides = int(argument), 6

        return number, sides


class Randomization(commands.Cog):
    """Commands with randomized interactions."""
    qualified_name = 'Randomization'

    def __init__(self, bot):
        self.bot = bot





    @commands.command(
        name='coinflip',
        aliases=('coin',))
    @commands.cooldown(3, 20, commands.BucketType.user)
    async def client_coinflip(self, ctx, n: int = 1):
        """Flip a number of coins.
Example:
    coinflip
    coin 5
Maximum amount of flips allowed is 20.

Design based on https://repl.it/@AllAwesome497/ASB-DEV-again."""
        def flip(sides=('Heads', 'Tails')):
            return random.choice(sides)

        skip_delay = False

        if n <= 0:
            result = 'Cannot flip less than zero coins.'
            skip_delay = True
        elif n == 1:
            result = f'Flipped __{flip()}__.'
        elif n <= 20:
            result = ['Results: ```diff']
            padding = len(str(n))
            for i in range(1, n + 1):
                coin = flip()
                color = '+' if coin == 'Heads' else '-'
                result.append(f'{color}{i:{padding}}: {coin}')
            result.append('```')
            result = '\n'.join(result)
        else:
            result = 'Cannot flip over 20 coins.'
            skip_delay = True

        if not skip_delay:
            await ctx.trigger_typing()
            await asyncio.sleep(1.5)
        await ctx.send(result, reference=ctx.message)





    @commands.command(
        name='dice',
        aliases=('roll',))
    @commands.cooldown(4, 20, commands.BucketType.user)
    async def client_dice(self, ctx, dice='d6', *args):
        """Roll a number of dice.
Example:
    dice         # 1 6-side
    roll 2       # 2 6-side, shows total value
    roll d20     # 1 20-side
    roll 2d12 -s # 2 12-side, shows each dice
Maximum amount of dice and sides allowed is 20.

Design based on https://repl.it/@AllAwesome497/ASB-DEV-again."""
        def roll():
            return random.randint(1, sides)

        number, sides = dice

        skip_delay = False

        if number <= 0:
            result = 'Cannot roll less than zero dice.'
            skip_delay = True
        elif sides <= 0:
            result = 'Cannot roll with less than zero sides.'
            skip_delay = True
        elif sides > 20:
            result = 'Cannot roll with over 20 sides.'
            skip_delay = True
        elif number == 1:
            result = f'Rolled a __{roll()}__.'
        elif number <= 20:
            if '-s' in args:
                result = ['Results: ```']
                i_padding = len(str(number))
                r_padding = len(str(sides))
                for i in range(1, number + 1):
                    result.append(f'{i:>{i_padding}}: {roll():>{r_padding}}')
                result.append('```')
                result = '\n'.join(result)
            else:
                dice = random.randint(number, number * sides)
                result = f'Rolled a total of __{dice}__.'
        else:
            result = 'Cannot roll over 20 dice.'
            skip_delay = True

        if not skip_delay:
            await ctx.trigger_typing()
            await asyncio.sleep(1.5)
        await ctx.send(result, reference=ctx.message)





    @commands.command(
        name='8ball',
        aliases=('eightball',))
    @commands.cooldown(2, 12, commands.BucketType.user)
    async def client_eightball(self, ctx, *, question: str = ''):
        """Answers a yes or no question."""
        await ctx.trigger_typing()
        await asyncio.sleep(random.randint(1, 5))
        await ctx.send(random.choice(CLIENT_EIGHTBALL), reference=ctx.message)





    @dslash_cog.cog_slash(
        name='8ball',
        options=[manage_commands.create_option(
            name='question',
            description='The question to ask. Can be left empty.',
            option_type=3,
            required=False
        )]
    )
    async def client_slash_eightball(self, ctx: SlashContext, question=''):
        """Shake an eight-ball for a question."""
        await ctx.respond()
        await ctx.send(random.choice(CLIENT_EIGHTBALL))





    @commands.command(
        name='pick',
        aliases=('choose', 'select'))
    @commands.cooldown(4, 20, commands.BucketType.user)
    async def client_pick(self, ctx, choice1, choice2, *choices):
        """Select one of your given choices.
Ayana command used as reference."""
        choices = list(choices)
        choices += [choice1, choice2]
        selected = random.choice(CLIENT_PICK_DIALOGUE).format(
            choice=random.choice(choices))
        await ctx.trigger_typing()
        await asyncio.sleep(1)
        await ctx.send(selected, reference=ctx.message)

    @dslash_cog.cog_slash(
        name='pick',
        options=[manage_commands.create_option(
            name='first',
            description='The first option.',
            option_type=3,
            required=True
        ), manage_commands.create_option(
            name='second',
            description='The second option.',
            option_type=3,
            required=True
        ), manage_commands.create_option(
            name='extra',
            description='Extra options, separated by spaces. '
                        'Use quotes for multi-word choices ("one choice").',
            option_type=3,
            required=False
        )]
    )
    async def client_slash_pick(self, ctx: SlashContext,
                                choice1, choice2, extra=None):
        """Choose one of the given options."""
        await ctx.respond()

        if extra is not None:
            choices = utils.parse_var_positional(extra)
        else:
            choices = []
        choices.append(choice1)
        choices.append(choice2)

        selected = random.choice(CLIENT_PICK_DIALOGUE).format(
            choice=random.choice(choices))

        await ctx.send(selected)










def setup(bot):
    bot.add_cog(Randomization(bot))
