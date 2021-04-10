import inflect


def timedelta_string(
        diff,
        years=True, months=True, weeks=True, days=True,
        hours=True, minutes=True, seconds=True,
        inflector=None):
    """Return a string representation of a timedelta.

    Can show years, months, weeks, day, hours, and minutes.

    """
    def s(n):
        return 's' if n != 1 else ''

    inflector = inflector or inflect.engine()

    message = []
    if diff.years and years:
        message.append(f"{diff.years:,} Year{s(diff.years)}")
    if diff.months and months:
        message.append(f"{diff.months:,} Month{s(diff.months)}")
    if diff.weeks and weeks:
        message.append(f"{diff.weeks:,} Week{s(diff.weeks)}")
    if diff.days and days:
        message.append(f"{diff.days:,} Day{s(diff.days)}")
    if diff.hours and hours:
        message.append(f"{diff.hours:,} Hour{s(diff.hours)}")
    if diff.minutes and minutes:
        message.append(f"{diff.minutes:,} Minute{s(diff.minutes)}")
    if diff.seconds and seconds:
        message.append(f"{diff.seconds:,} Second{s(diff.seconds)}")
    return inflector.join(message)
