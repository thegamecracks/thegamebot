import datetime
import decimal
import itertools  # rawincount()
import math
import pathlib    # exception_message()
import string
import sys        # exception_message()
import traceback  # exception_message()

from dateutil.relativedelta import relativedelta
import discord
import inflect

from bot import settings
from bot.other import discordlogger

inflector = inflect.engine()

# Whitelist Digits, Decimal Point, Main Arithmetic,
# Order of Operations, Function Arithmetic (modulus,),
# Binary Arithmetic (bitwise NOT, OR, AND, XOR, shifts)
# Scientific Notation, and Imaginary Part for evaluate command
CLIENT_EVALUATE_WHITELIST = set(
    string.digits
    + '.'
    + '*/+-'
    + '%'
    + '~|&^<>'
    + '()'
    + 'e'
    + 'E'
    + 'j'
)

logger = discordlogger.get_logger()


def convert_base(base_in: int, base_out: int, n,
        mapping='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
    """Converts a number to another base.
    Accepted bases are 2, 36, and all in-between.
    Base 36 uses 0-9 and a-z (case-insensitive).
    Decimals cannot be converted.

    Args:
        base_in (int): The number's base.
        base_out (int): The base to output as.
        n (int): The number to convert.
        mapping (str): The string mapping.

    """
    if max(base_in, base_out) > len(mapping):
        raise ValueError(f'Given base is greater than {len(mapping)}.')
    elif min(base_in, base_out) < 2:
        raise ValueError('Given base is less than 2.')

    if base_out == 10 and base_in <= 36 \
           and mapping == '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        # int() already represents in base 10, use that for optimization
        # unless base_in is larger than int()'s maximum base allowed
        # or the mapping is different that what int() uses
        # ("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        return int(n, base_in)

    if base_in <= 36 and mapping:
        n_int = int(n, base_in)
    else:
        n_int = 0
        for place, i_val in enumerate(n[::-1]):
            n_int += mapping.index(i_val) * base_in ** place
    n_max_place = int(math.log(n_int, base_out))
    n_out = ''

    # For every digit place
    for i in range(n_max_place, -1, -1):
        i_val = n_int // base_out ** i
        n_out += mapping[i_val]
        n_int -= base_out ** i * i_val

    return n_out


def datetime_difference(current, prior):
    """Return a relativedelta of current - prior."""
    return relativedelta(current, prior)


def datetime_difference_string(current, prior):
    """Return the difference from prior to current as a string.

    Can show years, months, weeks, day, hours, and minutes.

    """
    diff = datetime_difference(current, prior)
    s = []
    if diff.years:
        s.append(f"{diff.years} Year{'s' if diff.years != 1 else ''}")
    if diff.months:
        s.append(f"{diff.months} Month{'s' if diff.months != 1 else ''}")
    if diff.weeks:
        s.append(f"{diff.weeks} Week{'s' if diff.weeks != 1 else ''}")
    if diff.days:
        s.append(f"{diff.days} Day{'s' if diff.days != 1 else ''}")
    if diff.minutes:
        s.append(f"{diff.minutes} Minute{'s' if diff.minutes != 1 else ''}")
    return inflector.join(s)


def dec_addi(x, y):
    """Convert x and y into decimal.Decimal and return their sum."""
    return decimal.Decimal(x) + decimal.Decimal(y)


def dec_subi(x, y):
    """Convert x and y into decimal.Decimal and return their difference."""
    return decimal.Decimal(x) - decimal.Decimal(y)


def dec_muli(x, y):
    """Convert x and y into decimal.Decimal and return their product."""
    return decimal.Decimal(x) + decimal.Decimal(y)


def dec_divi(x, y):
    """Convert x and y into decimal.Decimal and return their quotient."""
    return decimal.Decimal(x) / decimal.Decimal(y)


def dec_divf(x, y):
    """Convert x and y into decimal.Decimal and return their floor quotient."""
    return decimal.Decimal(x) // decimal.Decimal(y)


def dec_pow(x, y):
    """Raise x to the power of y."""
    return decimal.Decimal(x) ** decimal.Decimal(y)


def exception_message(
        exc_type=None, exc_value=None, exc_traceback=None,
        header: str = '', log_handler=logger) -> str:
    """Create a message out of the last exception handled by try/except.

    Args:
        header (Optional[str]): The header to place above the message.
        log_handler (Optional): The logger to run the exception() method on.

    Returns:
        str: The string containing the exception message.

    """
    if exc_type is None and exc_value is None and exc_traceback is None:
        exc_type, exc_value, exc_traceback = sys.exc_info()
    elif exc_type is None or exc_value is None or exc_traceback is None:
        raise ValueError('An exception type/value/traceback was passed '
                         'but is missing the other values')

    # Header message with padded border
    msg = ''
    if header:
        msg = '{:=^{length}}\n'.format(
            header, length=len(header) * 2 + len(header) % 2)

    if log_handler is not None:
        # Log the exception; doesn't require creating a message
        log_handler.exception(msg)

    # Create the message to return, containing the traceback and exception
    for frame in traceback.extract_tb(exc_traceback):
        if frame.name == '<module>':
            # Bottom of the stack; stop here
            break

        msg += f'Frame {frame.name!r}\n'
        # Show only the path starting from project using instead of
        # just the full path inside frame.filename
        project_path = pathlib.Path().resolve()
        trace_path = pathlib.Path(frame.filename)
        try:
            filename = trace_path.relative_to(project_path)
        except ValueError:
            # Trace must be outside of project; use that then
            filename = trace_path

        msg += f'Within file "{filename}"\n'
        msg += f'at line number {frame.lineno}:\n'
        msg += f'   {frame.line}\n'
    msg += f'\n{exc_type.__name__}: {exc_value}'

    return msg


def gcd(a, b='high'):
    """Calculate the Greatest Common Divisor of a and b.

    Unless b == 0, the result will have the same sign as b (so that when
    b is divided by it, the result comes out positive).

    If b is low, calculates the low divisor of a other than itself.
    If b is high, calculates the highest divisor of a other than itself.

    """
    if b == 'low' or b == 'high':
        lookUpTo = math.ceil(math.sqrt(a))
        for i in range(2 if b == 'low' else lookUpTo,
                       lookUpTo + 1 if b == 'low' else 1,
                       1 if b == 'low' else -1):
            if a % i == 0:
                a = i if b == 'low' else a // i
                break
    else:
        while b:
            a, b = b, a % b
    return a


def get_user_color(
        user, default_color=None):
    "Return a user's role color if they are in a guild, else default_color."
    return (
        user.color if isinstance(user, discord.Member)
        else default_color if default_color is not None
        else int(settings.get_setting('bot_color'), 16)
    )


# This function is not done and is not currently in use.
##def message_snip(message):
##    """Returns a list of messages split by maximum message size in settings.
##
##    If the amount of messages exceeds message_limit, raises an OverflowError.
##
##    """
##    message_size
##    if len(message) > message_size:
##        max_length = message_size * message_limit
##        # If too many messages are required, return error message and True
##        if len(message) > max_length:
##            raise OverflowError(
##                f'The message is too long to print \
##({len(message)} > {max_length}).')
##
##        message_list = []  # The list containing each new message
##        message_extra = ' '  # Variable to store extra data
##
##        # Split the message into blocks of message_size characters
##        while len(message_extra):
##            message_extra = message[message_size:]
##            message_list.append(message[:message_size])
##            message = message_extra
##
##        # Send messages
##        return message_list
##
##    # If message is not over message_size characters
##    return [message]


def num(x):
    """Convert an object into either a int, float, or complex in that order."""
    try:
        if hasattr(x, 'is_integer') and not x.is_integer():
            raise ValueError
        return int(x)
    except Exception:
        try:
            return float(x)
        except Exception:
            n = complex(x)
            if n.imag == 0:
                return num(n.real)
            return complex(num(n.real), num(n.imag))


def parse_status(status='online'):
    status = status.casefold()

    if status in ('online', 'green', 'on', 'active'):
        return discord.Status.online
    elif status in ('idle', 'yellow', 'away', 'afk'):
        return discord.Status.idle
    elif status in ('dnd', 'red', 'donotdisturb'):
        return discord.Status.dnd
    elif status in ('invisible', 'grey', 'gray', 'black', 'offline', 'off'):
        return discord.Status.invisible
    else:
        raise ValueError('Unknown status')


def prime(n):
    """Checks if a number is prime."""
    return True if gcd(n) == 1 else False


def rawincount(filename):
    """Returns the number of lines in a file.

    Citation needed.

    """
    with open(filename, 'rb') as f:
        bufgen = itertools.takewhile(lambda x: x, (f.raw.read(1024*1024)
                                         for _ in itertools.repeat(None)))
        return sum( buf.count(b'\n') for buf in bufgen ) + 1


def safe_eval(x):
    """Filters a string before evaluating.
Uses CLIENT_EVALUATE_WHITELIST as the filter."""
    return num(eval(
        ''.join([char for char in x if char in CLIENT_EVALUATE_WHITELIST])
    ))


def truncate_message(
        message, size=2000, size_lines=None, placeholder='[...]'):
    """Truncate a message to a given amount of characters or lines.

    This should be used when whitespace needs to be retained as
    `textwrap.shorten` will collapse whitespace.

    Message is stripped of whitespace.

    """
    message = message.strip()

    in_code_block = 0

    lines = message.split('\n')
    chars = 0
    for line_i, line in enumerate(lines):
        if size_lines is not None and line_i == size_lines:
            # Reached maximum lines
            break

        in_code_block = (in_code_block + line.count('```')) % 2

        new_chars = chars + len(line)
        if new_chars > size:
            # This line exceeds max size; truncate it by word
            words = line.split(' ')
            last_word = len(words) - 1  # for compensating space split
            line_chars = chars

            for word_i, word in enumerate(words):
                new_line_chars = line_chars + len(word)

                if new_line_chars > (
                        size - len(placeholder)
                        - in_code_block * 3):
                    # This word exceeds the max size; truncate to here
                    break

                if word_i != last_word:
                    new_line_chars += 1

                line_chars = new_line_chars
            else:
                raise RuntimeError(f'line {line_i:,} exceeded max size but '
                                   'failed to determine where to '
                                   'truncate the line')

            if word_i == 0:
                # Line becomes empty; go back to last line
                # and add placeholder
                break
            else:
                # Truncate line and return new message
                line = ' '.join(words[:word_i] + [placeholder])
                return (
                    '\n'.join(lines[:line_i] + [line])
                    + '```' * in_code_block
                )
        else:
            chars = new_chars
    else:
        # Message did not exceed max size or lines; no truncation
        return message
    # Message exceeded max lines but not max size; truncate to line
    return (
        '\n'.join(lines[:line_i])
        + f' {placeholder}'
        + '```' * in_code_block
    )


# Decorators
def print_error(func):
    """Decorate error handlers to print the error to console
    before running the handler function."""
    async def wrapper(*args, **kwargs):
        logger.exception(f'In {func.__name__}, this error was raised:')
        mode = settings.get_setting('print_error_mode')
        if mode == 'raise':
            print(f'In {func.__name__}, this error was raised:')
            await func(*args, **kwargs)
            raise
        elif mode == 'print':
            print(f'In {func.__name__}, this error was raised:')
            print('\t' + repr(args[2]))
            await func(*args, **kwargs)
    return wrapper
