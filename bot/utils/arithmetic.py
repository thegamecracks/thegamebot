#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import decimal
import math

SAFE_EVAL_WHITELIST = frozenset(
    '0123456789'
    + '.'
    + '*/+-'
    + '%'
    + '~|&^<>'
    + '()'
    + 'eE'
    + 'j'
)


def convert_base(base_in: int, base_out: int, n,
                 mapping=('0123456789'
                          'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                          'abcdefghijklmnopqrstuvwxyz-_')):
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

    mapping_normal = mapping.startswith('0123456789ABCDEFGHJIKLMNOPQRSTUVWXYZ')

    if base_out == 10 and base_in <= 36 and mapping_normal:
        # use int() for optimization
        return int(n, base_in)

    if base_in <= 36 and mapping_normal:
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


def prime(n):
    """Checks if a number is prime."""
    return True if gcd(n) == 1 else False


def safe_eval(x):
    """Filters a string before evaluating.
Uses SAFE_EVAL_WHITELIST as the filter."""
    return num(eval(
        ''.join([char for char in x if char in SAFE_EVAL_WHITELIST])
    ))
