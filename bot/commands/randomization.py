import asyncio
import random

from discord.ext import commands

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
    '{mention} I choose {choice}.',
    '{mention} I pick {choice}.',
    '{mention} I select {choice}.',
)


class Randomization(commands.Cog):
    qualified_name = 'Randomization'
    description = 'Commands with randomized interactions.'

    def __init__(self, bot):
        self.bot = bot





    @commands.command(
        name='coinflip',
        aliases=('coin',))
    @commands.cooldown(1, 1.5, commands.BucketType.user)
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
        await ctx.send(result)





    @commands.command(
        name='dice',
        aliases=('roll',))
    @commands.cooldown(1, 1.5, commands.BucketType.user)
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

        if 'd' in dice:
            amount, sides = dice.split('d')[:2]
            if not amount:
                # "/sides" syntax
                amount = 1
            else:
                amount = int(amount)
            if not sides:
                sides = 6
            else:
                sides = int(sides)
        else:
            # "amount/" syntax
            amount, sides = int(dice), 6

        skip_delay = False

        if amount <= 0:
            result = 'Cannot roll less than zero dice.'
            skip_delay = True
        elif sides <= 0:
            result = 'Cannot roll with less than zero sides.'
            skip_delay = True
        elif sides > 20:
            result = 'Cannot roll with over 20 sides.'
            skip_delay = True
        elif amount == 1:
            result = f'Rolled a __{roll()}__.'
        elif amount <= 20:
            if '-s' in args:
                result = ['Results: ```']
                i_padding = len(str(amount))
                r_padding = len(str(sides))
                for i in range(1, amount + 1):
                    result.append(f'{i:>{i_padding}}: {roll():>{r_padding}}')
                result.append('```')
                result = '\n'.join(result)
            else:
                dice = random.randint(amount, amount * sides)
                result = f'Rolled a total of __{dice}__.'
        else:
            result = 'Cannot roll over 20 dice.'
            skip_delay = True

        if not skip_delay:
            await ctx.trigger_typing()
            await asyncio.sleep(1.5)
        await ctx.send(result)





    @commands.command(
        name='8ball',
        aliases=('eightball',))
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def client_eightball(self, ctx, *, question: str = ''):
        """Answers a yes or no question."""
        await ctx.trigger_typing()
        await asyncio.sleep(random.randint(1, 5))
        await ctx.send(
            f'{ctx.author.mention} {random.choice(CLIENT_EIGHTBALL)}')





    @commands.command(
        name='pick',
        aliases=('choose', 'select'))
    async def client_pick(self, ctx, choice1, choice2, *choices):
        """Select one of your given choices.
Ayana command used as reference."""
        choices = list(choices)
        choices += [choice1, choice2]
        await ctx.trigger_typing()
        await asyncio.sleep(1)
        await ctx.send(
            random.choice(CLIENT_PICK_DIALOGUE).format(
                choice=random.choice(choices),
                mention=ctx.author.mention
            )
        )










def setup(bot):
    bot.add_cog(Randomization(bot))
