#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
from dataclasses import dataclass
import datetime
import logging

from discord.ext import commands, tasks

from main import TheGameBot

logger = logging.getLogger('discord')


@dataclass(frozen=True)
class DowntimePeriod:
    start: datetime.datetime
    end: datetime.datetime

    @property
    def diff(self):
        return self.end - self.start

    def total_seconds(self):
        return self.diff.total_seconds()


class Uptime(commands.Cog):
    """Track the uptime of the bot."""
    qualified_name = 'Uptime'

    UPTIME_ALLOWED_DOWNTIME = 10

    def __init__(self, bot: TheGameBot):
        self.bot = bot
        self.last_running_check = datetime.datetime.now().astimezone()
        self.running_check.start()

    def cog_unload(self):
        self.running_check.cancel()

    def add_downtime_record(self, start: datetime.datetime,
                            end: datetime.datetime, vacuum=True):
        """Record a period of downtime."""
        self.bot.uptime_downtimes.append(DowntimePeriod(start, end))
        if vacuum:
            self.vacuum_downtimes(before=datetime.timedelta(days=1))

    def vacuum_downtimes(
        self, *,
        before: datetime.datetime | datetime.timedelta = None,
        limit: int = None
    ):
        """Remove the oldest downtime entries.

        Each parameter applies its own filter on the downtimes,
        so least one of the parameters must be passed.

        :param before:
            Removes downtimes before this datetime. If a timedelta
            is given, it is subtracted from the current time.
        :param limit:
            Removes datetimes until the deque size is at most this.
        :raises TypeError:
            No parameters were given.

        """
        downtimes = self.bot.uptime_downtimes
        applied_filter = False

        if before is not None:
            applied_filter = True

            before_dt = before
            if isinstance(before_dt, datetime.timedelta):
                before_dt = datetime.datetime.now().astimezone() - before_dt
            while downtimes[0].end < before_dt:
                del downtimes[0]

        if limit is not None:
            applied_filter = True

            to_remove = len(downtimes) - limit
            for _ in range(to_remove):
                del downtimes[0]

        if not applied_filter:
            raise TypeError('No vacuum filters given')

    def update_last_connect(self, *, force_update=False):
        if not self.bot.uptime_is_online:
            # Calculate downtime
            now = datetime.datetime.now().astimezone()
            diff = now - self.bot.uptime_last_disconnect
            self.add_downtime_record(self.bot.uptime_last_disconnect, now)

            # If downtime was long or force_update is True,
            # update last connect, else record the downtime
            if force_update or (diff.total_seconds()
                                > self.UPTIME_ALLOWED_DOWNTIME):
                self.bot.uptime_last_connect = now
                self.bot.uptime_last_connect_adjusted = now
                self.bot.uptime_total_downtime = datetime.timedelta()

                if force_update:
                    logger.info('Uptime: forced uptime reset')
                else:
                    logger.info(
                        'Uptime: Resetting uptime after downtime of '
                        '{} seconds (>{} seconds)'.format(
                            diff.total_seconds(),
                            self.UPTIME_ALLOWED_DOWNTIME
                        )
                    )
            else:
                self.bot.uptime_total_downtime += diff
                self.bot.uptime_last_connect_adjusted = (
                    self.bot.uptime_last_connect
                    + self.bot.uptime_total_downtime
                )
                logger.info(
                    'Uptime: Recorded downtime of %.2f seconds',
                    diff.total_seconds()
                )

            self.bot.uptime_is_online = True

    def run_check(self):
        now = datetime.datetime.now().astimezone()
        if now - self.last_running_check > datetime.timedelta(minutes=2):
            # Missed a check; assume downtime lasted for the entire duration
            logger.info('Uptime: Running check was delayed by over 2 minutes')
            self.bot.uptime_last_disconnect = self.last_running_check
            self.bot.uptime_is_online = False
            self.update_last_connect()
        self.last_running_check = now

    @tasks.loop(minutes=1)
    async def running_check(self):
        """Do a continuously running test to make sure that the bot is running
        the entire time. If the host goes into sleep mode, this will detect
        a large time discrepancy between checks and record it as downtime.
        """
        self.run_check()

    @commands.Cog.listener()
    async def on_connect(self):
        """Triggered when waking up from computer sleep.
        Triggers the running check immediately."""
        self.bot.uptime_is_online = True
        self.run_check()

    @commands.Cog.listener()
    async def on_disconnect(self):
        """Used for uptime tracking."""
        if self.bot.uptime_is_online:
            self.bot.uptime_last_disconnect = datetime.datetime.now().astimezone()
            self.bot.uptime_is_online = False

    @commands.Cog.listener()
    async def on_resumed(self):
        """Used for uptime tracking.

        Triggered when reconnecting from an internet loss.

        """
        self.update_last_connect()


async def setup(bot: TheGameBot):
    await bot.add_cog(Uptime(bot))
