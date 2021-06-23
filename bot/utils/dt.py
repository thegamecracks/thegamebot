#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime

from dateutil.relativedelta import relativedelta
import inflect


def strftime_zone(dt, naive='%c', aware='%c %Z (%z)', aware_utc='%c %Z') -> str:
    """A shorthand for turning a datetime into a string,
    including timezone information.

    Args:
        dt (datetime.datetime): The datetime to format.
        naive (str): The format to use when the datetime is timezone-naive.
        aware (str): The format to use when the datetime is timezone-aware.
        aware_utc (str): The format to use when the datetime is localized

    Returns:
        str

    """
    utcoffset = dt.utcoffset()
    if utcoffset is None:
        return dt.strftime(naive)
    elif utcoffset:
        return dt.strftime(aware)
    return dt.strftime(aware_utc)


def timedelta_string(
        diff: relativedelta,
        years=True, months=True, weeks=True, days=True,
        hours=True, minutes=True, seconds=True,
        capitalize=False, inflector=None):
    """Return a string representation of a relativedelta.

    Can show years, months, weeks, day, hours, minutes, and seconds.

    """
    units = ('years', 'months', 'weeks', 'days', 'hours', 'minutes', 'seconds')

    inflector = inflector or inflect.engine()

    message = []
    for u in units:
        n = getattr(diff, u)
        if n and locals()[u]:
            message.append('{:,} {}'.format(
                n,
                u[:-1] if n == 1 else u
            ))

    return inflector.inflect(inflector.join(message))


def timedelta_abbrev(
        diff: datetime.timedelta, *,
        precise: bool = False,
        sep=''
    ) -> str:
    """Return a string abbreviation of a timedelta.

    Args:
        diff (datetime.timedelta): The timedelta to abbreviate.
        precise (bool): If True, shows every applicable unit of time
            rather than only the greatest unit.
            This also displays the number of seconds
            with a decimal precision of 6.
        sep (str): The separator to use when joining the time units
            together. Only useful when precise=True.

    """
    abbreviations = (
        ('y', 31536000), ('mo', 2592000), ('d', 86400),
        ('h', 3600), ('m', 60), ('s', 1)
    )

    seconds = diff.total_seconds()
    is_neg = seconds < 0
    seconds = abs(seconds)
    if not precise:
        seconds = round(seconds)

    abbr = []
    for unit, size in abbreviations:
        if precise and unit == 's':
            n = round(seconds / size, 6)
        else:
            n = seconds // size

        if n:
            abbr.append(f'{n}{unit}')
            if not precise:
                break
    else:
        if not abbr:
            return '0s'

    return '-' * is_neg + sep.join(abbr)
