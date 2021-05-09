#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
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
        diff,
        years=True, months=True, weeks=True, days=True,
        hours=True, minutes=True, seconds=True,
        capitalize=False, inflector=None):
    """Return a string representation of a relativedelta.

    Can show years, months, weeks, day, hours, and minutes.

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
