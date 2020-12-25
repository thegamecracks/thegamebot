import datetime

DAYS = {
    k: value
    for days, value in (
        (('mon', 'monday'), 0),
        (('tue', 'tuesday'), 1),
        (('wed', 'wednesday'), 2),
        (('thu', 'thur', 'thursday'), 3),
        (('fri', 'friday'), 4),
        (('sat', 'saturday'), 5),
        (('sun', 'sunday'), 6)
    ) for k in days
}


class Time:
    """A time object that stores minutes.

    Note: adding or subtracting time can over/underflow.

    Note: when adding or subtracting datetime.datetime/datetime.time,
        the second part is rounded to the nearest minute.

    """
    def __init__(self, total_minutes):
        if not 0 <= total_minutes < 1440:
            raise ValueError(
                f'total_minutes out of bounds ({total_minutes})')
        self.total_minutes = total_minutes

    def __add__(self, other):
        if isinstance(other, self.__class__):
            h = self.hour + other.hour
            m = self.minute + other.minute
            total_minutes = (h*60 + m) % 1440
            return self.__class__(total_minutes)
        elif isinstance(other, (datetime.datetime, datetime.time)):
            h = self.hour + other.hour
            m = self.minute + (other.minute + round(other.second / 60))
            total_minutes = (h*60 + m) % 1440
            return self.__class__(total_minutes)
        raise NotImplemented

    def __sub__(self, other):
        if isinstance(other, self.__class__):
            h = self.hour - other.hour
            m = self.minute - other.minute
            total_minutes = (h*60 + m) % 1440
            return self.__class__(total_minutes)
        elif isinstance(other, (datetime.datetime, datetime.time)):
            h = self.hour - other.hour
            m = self.minute - (other.minute + round(other.second / 60))
            total_minutes = (h*60 + m) % 1440
            return self.__class__(total_minutes)
        raise NotImplemented

    def __eq__(self, other):
        if isinstance(other, (
                self.__class__,
                datetime.datetime, datetime.time)):
            return self.hour == other.hour and self.minute == other.minute
        raise NotImplemented

    def __lt__(self, other):
        if isinstance(other, (
                self.__class__,
                datetime.datetime, datetime.time)):
            if self.hour < other.hour:
                return True
            elif self.hour == other.hour and self.minute < other.minute:
                return True
            return False
        raise NotImplemented

    def __gt__(self, other):
        if isinstance(other, (
                self.__class__,
                datetime.datetime, datetime.time)):
            if self.hour > other.hour:
                return True
            elif self.hour == other.hour and self.minute > other.minute:
                return True
            return False
        raise NotImplemented

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, self.total_minutes)

    def __str__(self):
        return self.as_string(format_12h=True)

    def as_string(self, format_12h=False):
        if format_12h:
            hour, minute = self.hour_and_minute()

            suffix = 'am' if hour < 12 else 'pm'

            if hour == 0:
                hour_str = '12'
            elif hour <= 12:
                hour_str = str(hour)
            else:
                hour_str = str(hour - 12)

            return '{}:{:02d}{}'.format(hour_str, minute, suffix)
        else:
            return '{:02d}:{:02d}'.format(*self.hour_and_minute())

    @property
    def hour(self):
        return self.total_minutes // 60

    def hour_and_minute(self):
        return divmod(self.total_minutes, 60)

    @property
    def minute(self):
        return self.total_minutes % 60

    @classmethod
    def from_hour_and_minute(cls, hour, minute):
        total_minutes = hour * 60 + minute
        return cls(total_minutes)

    @classmethod
    def from_string(cls, s):
        """Create a Time object from a string.

        Supports 12h format and 24h format.

        Does not casefold or strip whitespace.

        Examples of allowed input:
            8am  # Hour only
            12pm  # Two-digit hour
            804am  # No colon
            0310pm  # Extra spacing
            11:16pm  # With colon
            04:00pm
            # Respective times in 24h
            0800
            1200
            0804
            1510
            23:16
            16:00

        """
        def has_proper_suffix(s, *, raise_exception=False):
            condition = s.endswith('am') or s.endswith('pm')
            if not condition and raise_exception:
                if s.endswith('m'):
                    raise ValueError('improper 12h suffix in string')
                raise ValueError('no 12h suffix in string')
            return condition

        def partition(s):
            length = len(s)
            if length == 3:
                if s.endswith('m'):
                    # 1am (pm is already compensated outside of function)
                    return int(s[0]), 0
                else:
                    # 123 (incorrect 24h format)
                    raise ValueError('expected 4 digits in 24h format')
            elif length == 4:
                if s.endswith('m'):
                    # 12am
                    return int(s[:2]), 0
                else:
                    # 0234 (24h time)
                    return int(s[:2]), int(s[2:])
            elif length == 5:
                # 123am (one digit hour)
                return int(s[0]), int(s[1:3])
            elif length == 6:
                # 1234am
                return int(s[:2]), int(s[2:4])

        s = s.replace(':', '')

        hour = 0
        minute = 0

        if s.endswith('m'):
            # 12h
            has_proper_suffix(s, raise_exception=True)

            if s.endswith('pm'):
                hour += 12

            h, m = partition(s)

            if h == 12:
                # In 12h format, 12 actually means 0 hours
                h = 0

            if h > 12:
                raise ValueError('hour is over 12, contradicting 12h suffix')
            if m >= 60:
                raise ValueError('minute given is over 60')

            hour += h
            minute = m
        else:
            # 24h
            h, m = partition(s)

            if m >= 60:
                raise ValueError('minute given is over 60')

            hour = h
            minute = m

        return cls.from_hour_and_minute(hour, minute)


def parse_timedelta(s, utcnow=None):
    """
    Examples:
        at 10pm [x] (x can be any message)
        in 10 sec/min/h/days [x]
        on wednesday [x]

    Args:
        s (str): The string to parse.
        utcnow (Optional[datetime.datetime]): A naive datetime representing
            what time it currently is in UTC. If None, defaults to
            datetime.datetime.utcnow(). This argument is only needed when
            a time is given in the format of 

    Returns:
        Tuple[datetime.timedelta, str]
    """
    def next_token():
        nonlocal s

        if s is None:
            return ''

        parts = s.split(None, 1)

        length = len(parts)
        if length == 2:
            token, s = parts[0], parts[1]
        elif length == 1:
            token, s = parts[0], ''

        return token.lower()

    if utcnow is None:
        utcnow = datetime.datetime.utcnow()

    preposition = next_token()

    if preposition in ('at', 'in', 'on'):
        when = next_token()

        # Try converting to day
        when_weekday = DAYS.get(when)
        if when_weekday is not None:
            # determine whether it refers to this week or next
            weekday = utcnow.weekday()
            days = when_weekday - weekday + 7*(when_weekday <= weekday)
            td = datetime.timedelta(days=days)
            return td, s

        # Try converting to Time
        try:
            utcwhen = Time.from_string(when)
        except (ValueError, TypeError) as e:
            pass
        else:
            # Get time difference with utcnow rounding down seconds
            # NOTE: Time objects automatically handle underflowing,
            # so no code is needed beyond this
            diff = utcwhen - utcnow.replace(second=0)
            td = datetime.timedelta(hours=diff.hour, minutes=diff.minute)
            return td, s

        # Try converting into time diff
        try:
            num = int(when)
            if num <= 0:
                raise ValueError('time cannot be negative')
        except ValueError:
            pass
        else:
            unit = next_token()
            if unit in ('s', 'sec', 'second', 'seconds'):
                unit = 'seconds'
            elif unit in ('m', 'min', 'minute', 'minutes'):
                unit = 'minutes'
            elif unit in ('h', 'hr', 'hrs', 'hour', 'hours'):
                unit = 'hours'
            elif unit in ('d', 'day', 'days'):
                unit = 'days'
            else:
                unit = None

            if unit is not None:
                kwargs = {unit: num}
                td = datetime.timedelta(**kwargs)
                return td, s

        raise ValueError('Invalid time')
    else:
        raise ValueError(f'Invalid preposition: {preposition!r}')


if __name__ == '__main__':
    # Calculate difference and sum from utcnow to a given Time
    now = datetime.datetime.utcnow().replace(second=0)
    print('Now:', now)
    while True:
        s = input('Time: ')
        when = Time.from_string(s)
        print('When:', when.as_string())
        diff = when - now
        sum_ = when + now
        print('Diff:', diff.as_string())
        print('Sum: ', sum_.as_string())
