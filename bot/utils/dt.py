#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
from dateutil.relativedelta import relativedelta
import inflect


def timedelta_string(
        diff: relativedelta,
        years=True, months=True, weeks=True, days=True,
        hours=True, minutes=True, seconds=True,
        capitalize=False, inflector: inflect.engine = None):
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
