import datetime

from discord.ext import commands


class Uptime(commands.Cog):
    """Track the uptime of the bot."""
    qualified_name = 'Uptime'

    UPTIME_ALLOWED_DOWNTIME = 10

    def __init__(self, bot):
        self.bot = bot





    def update_last_connect(self, *, force_update=False):
        if not self.bot.uptime_is_online:
            # Calculate downtime
            now = datetime.datetime.now().astimezone()
            diff = now - self.bot.uptime_last_disconnect

            # Only update last connect if downtime was long,
            # else record the downtime
            if force_update or (diff.total_seconds()
                                > self.UPTIME_ALLOWED_DOWNTIME):
                self.bot.uptime_last_connect = now
                self.bot.uptime_last_connect_adjusted = now
                self.bot.uptime_total_downtime = datetime.timedelta()

                if force_update:
                    print('Uptime: forced uptime reset')
                else:
                    print(
                        'Uptime: Downtime of {} seconds exceeded allowed '
                        'downtime ({} seconds); resetting uptime'.format(
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
                print('Uptime:', 'Recorded downtime of',
                      diff.total_seconds(), 'seconds')

            self.bot.uptime_is_online = True


    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        """Used for tracking processed commands."""
        self.bot.info_processed_commands[ctx.command.qualified_name] += 1

    @commands.Cog.listener()
    async def on_connect(self):
        """Used for uptime tracking.

        Triggered when waking up from computer sleep.
        As there is no way to tell how long the computer went for sleep,
        this forces the last_connect time to be updated.

        """
        self.update_last_connect(force_update=True)


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










def setup(bot):
    bot.add_cog(Uptime(bot))
