import decimal
import io
import math
import string
from typing import Union

from discord.ext import commands
import linecache
import pint

from bot import utils
from bot.other import mathparser

FILE_FIBONACCI = 'data/fibonacci.txt'

PINT_UREG = pint.UnitRegistry()
Q_ = PINT_UREG.Quantity

to_hex = lambda x: decimal.Decimal(int(x, 16))
dec_or_hex = Union[decimal.Decimal, to_hex]


class Mathematics(commands.Cog):
    """Commands for mathematical operations."""
    qualified_name = 'Mathematics'

    def __init__(self, bot):
        self.bot = bot


    async def cog_command_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, OverflowError):
            await ctx.send(error.args[1] + '.')
        elif isinstance(error, ZeroDivisionError):
            await ctx.send('Division by Zero occurred.')





    @commands.command(
        name='add',
        brief='Adds two numbers.',
        aliases=('+', 'sum', 'addi'))
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_add(self, ctx, x: dec_or_hex, y: dec_or_hex):
        """Returns the sum of x and y."""
        await ctx.send(f'{x+y:G}')





    @commands.command(
        name='subtract',
        brief='Subtracts two numbers.',
        aliases=('-', 'minus', 'subi'))
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_subtract(self, ctx, x: dec_or_hex, y: dec_or_hex):
        """Returns the difference of x and y."""
        await ctx.send(f'{x-y:G}')





    @commands.command(
        name='multiply',
        brief='Multiplies two numbers.',
        aliases=('*', 'product', 'muli'))
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_multiply(self, ctx, x: dec_or_hex, y: dec_or_hex):
        """Returns the product of x and y."""
        await ctx.send(f'{x*y:G}')





    @commands.command(
        name='divide',
        brief='Divides two numbers.',
        aliases=('/', 'quotient', 'divi'))
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_divide(self, ctx, x: dec_or_hex, y: dec_or_hex):
        """Returns the quotient of x and y."""
        await ctx.send(f'{x/y:G}')





    @commands.command(
        name='power',
        brief='Raises x to the power of y.',
        aliases=('exp', 'exponent', 'pow', 'raise'))
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_exponent(self, ctx, x: dec_or_hex, y: dec_or_hex):
        """Returns x raised to the power of y."""
        await ctx.send(f'{x**y:G}')





    @commands.command(
        name='sqrt',
        brief='Squares roots a number.',
        aliases=('squareroot',))
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_sqrt(self, ctx, x: dec_or_hex):
        """Returns the 2nd root of x."""
        await ctx.send(f'{x.sqrt():G}')





    @commands.command(
        name='evaluate',
        aliases=('eval',))
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def client_evaluate(self, ctx, *, expr: str):
        """Evaluates a simple mathematical expression.
Syntax:
```yaml
**: Exponentation
//: Floor division
 %: Modulus
 ~: Bitwise NOT
 |: Bitwise OR
 &: Bitwise AND
 ^: Bitwise XOR
<<: Left Shift
>>: Right Shift
``` Example expression: `(1+3) ** -2 - 7 // 9e2`

To reveal the evaluation of your expression, add --debug to your expression."""
        debugging = '--debug' in expr
        if debugging:
            expr = expr.replace('--debug', '').strip()

        msg = []
        with ctx.typing():
            postfix, tokens = mathparser.Postfix.from_infix(expr)
            if debugging:
                msg.append('```\n')
                msg.append('Parsed tokens: {}\n'.format(
                    ' '.join([str(t) for t in tokens]))
                )
                msg.append('Generated postfix:\n  {}'.format(
                    ' '.join([str(t) for t in postfix]))
                )
                with io.StringIO() as debug_output:
                    result = postfix.evaluate(debug_output=debug_output)
                    debug_output.seek(0)
                    for line in debug_output.read().strip().split('\n'):
                        msg.append('\n= ')
                        msg.append(line)
                msg.append('``` ')
            else:
                result = postfix.evaluate()

            msg.append(f'`{expr}` = **{result}**')

        await ctx.send(''.join(msg))


    @client_evaluate.error
    async def client_evaluate_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, SyntaxError):
            await ctx.send(f'Undefined Syntax Error occurred: {error}')
        elif isinstance(error, ValueError):
            await ctx.send(str(error))
        elif isinstance(error, TypeError):
            await ctx.send(str(error))
        elif isinstance(error, decimal.Overflow):
            await ctx.send('Could not calculate due to overflow.')





    @commands.command(
        name='fibonacci')
    @commands.cooldown(2, 15, commands.BucketType.user)
    async def client_fibonacci(self, ctx, n: int, m: int = None):
        """Returns specified fibonacci numbers.

Results are limited to displaying the first 140 characters
and 50 fibonacci numbers at once.

n: First number. If only this is provided, returns the nth fibonacci number.
m: Second number. If this is provided, returns n to m fibonacci numbers."""

        # If m is not given, set to 0 and set m_none to True
        m_none = False
        if m is None:
            m = 0
            m_none = True

        # Convert inputs into integers
        n = int(n) + 1
        m = int(m)

        if not m_none and len(range(n, m)) > 50:
            raise ValueError('The range of requested fibonacci numbers '
                             'must be below 50.')

        # Set limit of fibonacci parameters to amount of
        # lines FILE_FIBONACCI has
        limit = utils.rawincount(FILE_FIBONACCI) - 2
        # Subtract 2 to ignore start and end line

        # Do nothing if n or m is zero or negative
        if min(n-1, m if not m_none else 1) <= 0:
            return
        # Send error message if n or m is more than limit
        if n-1 > limit:
            raise ValueError(f'N is too high. The maximum is {limit:d}.')
        elif m > limit:
            raise ValueError(f'M is too high. The maximum is {limit:d}.')

        # If m is present, return range(n, m + 1) fibonacci numbers
        if m:
            message = []
            # Take the required lines
            for i in range(n, m + 2):
                message.append(linecache.getline(FILE_FIBONACCI, i)[:-1])
            # Join the message into one string
            message = ', '.join(message)

        # If m is not present, get the fibonacci number from the file
        else:
            message = linecache.getline(FILE_FIBONACCI, n)[:-1]

        # Print message
        await ctx.send(utils.truncate_message(message, 140))


    @client_fibonacci.error
    async def client_fibonacci_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, ValueError):
            await ctx.send(str(error))





    @commands.command(
        name='gcd',
        brief='Greatest common divisor/factor.',
        aliases=('gcf',))
    @commands.cooldown(5, 30, commands.BucketType.user)
    async def client_gcd(self, ctx, x: int, y: str):
        """Return the Greatest Common Divisor/Factor of one or two integers.

If y is "low", calculates the lowest divisor of x other than itself.
If y is "high", calculates the highest divisor of x other than itself."""
        await ctx.channel.trigger_typing()

        if x > 1_000_000:
            await ctx.send('X must be below one million.')
        elif y == 'low' or y == 'high':
            await ctx.send(utils.gcd(x, y))
        else:
            try:
                y = int(y)
            except ValueError:
                await ctx.send('Y is not an integer.')
            else:
                if y > 1_000_000:
                    await ctx.send('Y must be below one million.')
                else:
                    await ctx.send(utils.gcd(x, y))





    @commands.command(
        name='isprime',
        aliases=('prime',))
    @commands.cooldown(5, 30, commands.BucketType.user)
    async def client_isprime(self, ctx, n: int, setting: str = 'high'):
        """Checks if a number is prime.
n - The number to test.
setting - low or high: Returns either the lowest or highest divisor
 other than 1 and itself."""
        await ctx.channel.trigger_typing()

        if n < 2:
            return await ctx.send(f'{n} is not a prime number;\n'
                                  'all whole numbers below 3 are not prime.')
        elif n > 1_000_000:
            return await ctx.send('N must be below one million.')


        divisor = utils.gcd(n, setting)

        if divisor == 1 or divisor == n:
            await ctx.send(f'{n} is a prime number.')
        elif setting == 'low':
            await ctx.send(f'{n} is not a prime number;\n\
The lowest divisor is {divisor}, which can be multiplied by {n//divisor}.')
        elif setting == 'high':
            await ctx.send(f'{n} is not a prime number;\n\
The highest divisor is {n//divisor}, which can be multiplied by {divisor}.')





    @staticmethod
    def factors(n):
        """Returns a list of all factors of a number."""
        # Type Assertations
        if isinstance(n, float):
            raise TypeError(
                'Cannot get factors of a float number.')
        if isinstance(n, complex):
            raise TypeError(
                'Cannot get factors of a complex number.')
        if not isinstance(n, int):
            raise TypeError(
                f'Expected integer, received object of type {type(n)}')

        # Value Assertations
        if n < 0:
            raise ValueError('Cannot get factors of negative numbers.')

        # Edge Case Assertations
        if n == 0:
            return []
        if n == 1:
            return [1]
        if n == 2:
            return [1, 2]

        factors = [1, n]
        highestFactor = int(math.sqrt(n) + 1)

        for possibleFactor in range(2, highestFactor + 1):
            # range generates unnecessary numbers to test; make own generator?
            if n % possibleFactor == 0:
                factors.insert(-1, possibleFactor)

        for factor in factors[1:-1][::-1]:
            newFactor = n // factor
            if newFactor not in factors:
                factors.insert(-1, newFactor)

        return factors





    @commands.command(
        name='factors',
        aliases=('factor',))
    @commands.cooldown(5, 30, commands.BucketType.user)
    async def client_factors(self, ctx, n: int):
        """Returns all factors of a number.
n - The number to test.
The maximum number to check factors is 10000."""
        if n > 10000:
            return await ctx.send('N must be below ten thousand.')

        await ctx.channel.trigger_typing()

        factors = self.factors(n)

        if not factors:
            return await ctx.send(f'There are no factors of {n}.')

        message = ', '.join([str(i) for i in factors])
        await ctx.send(f'Factors of {n}:\n {message}')


    @client_factors.error
    async def client_factors_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, ValueError):
            await ctx.send(str(error))
        elif isinstance(error, TypeError):
            await ctx.send(str(error))





    @commands.command(
        name='convert',
        aliases=('unit', 'units'))
    @commands.cooldown(5, 10, commands.BucketType.user)
    async def client_convertunit(self, ctx, measurement, to, *, unit=None):
        """Converts a unit into another unit.
Examples:
    convert 1e2 m to ft
        # Scientific notation only works when the unit is separated
        # Counterexample: convert 1e2m to ft
    convert 100m ft
    convert 1lb to g
    convert 1m ft

    convert 0.5km to m
    convert .1km m
Temperature conversions:
    convert 32 fahrenheit to celsius
        # Fahrenheit to Celsius
    convert 32 degF to degC
        # Fahrenheit to Celsius
    convert 273.15 kelvin to degR
        # Kelvin to Rankine
    convert 273.15 K to degC"""
        def separate(m):
            for i, s in enumerate(measurement):
                # Issue: should optimize by creating a function for this,
                # using a constant containing a set of valid characters
                if not s.isnumeric() and s not in '.-+':
                    break
            return utils.safe_eval(measurement[:i]), measurement[i:]

        if unit is None:
            # "convert 1m ft" syntax
            unit = to
            unit_val, unit_str = separate(measurement)
        else:
            args = unit.split()
            if len(args) == 1:
                # "convert 1m to ft" syntax
                unit_val, unit_str = separate(measurement)
                unit = args[0]
            elif args[0].casefold() == 'to':
                # "convert 1 m to ft" syntax
                unit_val, unit_str = utils.safe_eval(measurement), to
                unit = args[1]
            else:
                # "convert 1 m ft" syntax
                # Ignores extra arguments as to be consistent with
                # how discord API handles it
                unit_val, unit_str = utils.safe_eval(measurement), to
                unit = args[0]

        # Temperature capitalization corrections
        # Pint doesn't catch these
        if unit == 'Fahrenheit':
            unit = 'fahrenheit'
        elif unit == 'Celsius':
            unit = 'celsius'

        # Parse the measurement
        try:
            parsed_unit = Q_(unit_val, unit_str)
            converted_unit = parsed_unit.to(unit)
        except (pint.DimensionalityError,
                pint.OffsetUnitCalculusError,
                pint.UndefinedUnitError) as e:
            return await ctx.send(str(e))

        # Round quantity to 3 digits or as integer
        quantity = decimal.Decimal(f'{converted_unit.magnitude:.3f}')

        await ctx.send('{quantity}{unit:~} ({unit})'.format(
            quantity=quantity,
            unit=converted_unit.units
        ))





    @commands.command(
        name='numberbase',
        aliases=('base',))
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def client_numberbase(self, ctx,
        base_in: int, base_out: int, n,
            mapping: str = None):
        """Converts a number to another base.
Accepted bases are 2, 64, and all in-between.
Base 64 uses the URL safe mapping of 0-9, A-Z, a-z, "-", and "_".
Decimals cannot be converted.
When base_in <= 36 and the mapping is the default,
letters are case-insensitive but will print out capitalized.

base_in: The number's base.
base_out: The base to output as.
n: The number to convert."""
        if mapping is None:
            mapping = (string.digits + string.ascii_uppercase
                       + string.ascii_lowercase + '-_')
        await ctx.send(
            utils.convert_base(
                base_in, base_out, n,
                mapping[:max(base_in, base_out)]
            )
        )


    @client_numberbase.error
    async def client_numberbase_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, ValueError):
            msg = str(error)
            if msg == 'substring not found':
                msg = 'There is an unknown character(s) in the number.'
            elif 'invalid literal for int()' in msg:
                # Find the first number in message; it should be the base
                # n[:-1] - Remove the colon next to the number
                num = [n[:-1] for n in msg.split() if n[:-1].isnumeric()][0]
                msg = ('There is a character within the number not part of'
                       f' base {num}.')
            await ctx.send(msg)
        elif isinstance(error, TypeError):
            await ctx.send(str(error))










def setup(bot):
    bot.add_cog(Mathematics(bot))
