import datetime

from discord.ext import commands, ipc

from bot import utils


class IPC(commands.Cog):
    """Provide IPC methods for the webserver."""

    def __init__(self, bot):
        self.bot = bot

    @ipc.server.route()
    async def get_uptime_date(self, data) -> datetime.datetime:
        """Get the datetime when the bot last connected."""
        dt = self.bot.uptime_last_connect.astimezone(
            datetime.timezone.utc
        )
        
        return dt.strftime('%Y/%m/%d %a %X UTC')

    @ipc.server.route()
    async def get_uptime_diff(self, data) -> str:
        """Get the timedelta since the bot last connected as a string."""
        diff = utils.datetime_difference(
            datetime.datetime.now().astimezone(),
            self.bot.uptime_last_connect_adjusted
        )
        return utils.timedelta_string(diff)










def setup(bot):
    bot.add_cog(IPC(bot))
