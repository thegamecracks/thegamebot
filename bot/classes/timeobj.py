import datetime


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
            return self.__class__.from_hour_and_minute(
                (self.hour + other.hour) % 24,
                (self.minute + other.minute) % 60
            )
        elif isinstance(other, (datetime.datetime, datetime.time)):
            return self.__class__.from_hour_and_minute(
                (self.hour + other.hour) % 24,
                (self.minute + other.minute + round(other.second / 60)) % 60
            )
        raise NotImplemented

    def __sub__(self, other):
        if isinstance(other, self.__class__):
            return self.__class__.from_hour_and_minute(
                (self.hour - other.hour) % 24,
                (self.minute - other.minute) % 60
            )
        elif isinstance(other, (datetime.datetime, datetime.time)):
            return self.__class__.from_hour_and_minute(
                (self.hour - other.hour) % 24,
                (self.minute - other.minute + round(other.second / 60)) % 60
            )
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
