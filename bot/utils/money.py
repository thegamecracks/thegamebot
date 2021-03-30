import decimal


def format_cents(cents: int):
    return format_dollars(cents / 100)


def format_dollars(dollars):
    dollars = round_dollars(dollars)
    sign = '-' if dollars < 0 else ''
    dollar_part = abs(int(dollars))
    cent_part = abs(int(dollars % 1 * 100))
    return '{}${}.{:02d}'.format(sign, dollar_part, cent_part)


def parse_dollars(s: str, round_to_cent=True) -> decimal.Decimal:
    """Parse a string into a Decimal.

    Raises:
        ValueError: The string could not be parsed.

    """
    s = s.replace('$', '', 1)
    try:
        d = decimal.Decimal(s)
    except decimal.InvalidOperation as e:
        raise ValueError('Could not parse cents') from e
    return round_dollars(d) if round_to_cent else d


def round_dollars(d) -> decimal.Decimal:
    """Round a number-like object to the nearest cent."""
    cent = decimal.Decimal('0.01')
    return decimal.Decimal(d).quantize(cent, rounding=decimal.ROUND_HALF_UP)
