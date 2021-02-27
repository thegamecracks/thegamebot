import datetime

from discord.ext import commands, ipc

from bot import utils


class IPC(commands.Cog):
    """Provide IPC methods for the webserver."""

    def __init__(self, bot):
        self.bot = bot

    @ipc.server.route()
    async def do_restart(self, data):
        """Restart the bot."""
        print('Initiating restart from IPC')
        return await self.bot.restart()

    @ipc.server.route()
    async def do_shutdown(self, data):
        """Shutdown the bot."""
        print('Initiating shutdown from IPC')
        return await self.bot.logout()

    @ipc.server.route()
    async def get_number_commands(self, data) -> int:
        """Return the number of commands the bot has."""
        return len(self.bot.commands)

    @ipc.server.route()
    async def get_number_commands_processed(self, data) -> int:
        """Return the number of commands that have been processed."""
        return sum(self.bot.info_processed_commands.values())

    @ipc.server.route()
    async def get_number_guilds(self, data) -> int:
        """Return the number of guilds the bot is in."""
        return len(self.bot.guilds)

    @ipc.server.route()
    async def get_number_members(self, data) -> dict:
        """Return the number of members the bot can see,
        excluding other bots.

        When members intent is disabled, uses an approximate member count.

        {'member_count': int,
         'is_approximate': bool}

        """
        is_approximate = not self.bot.intents.members
        if is_approximate:
            member_count = sum(g.member_count for g in self.bot.guilds)
        else:
            member_count = sum(not u.bot for u in self.bot.users)

        return {'member_count': member_count, 'is_approximate': is_approximate}

    @ipc.server.route()
    async def get_uptime_date(self, data) -> str:
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

    @ipc.server.route()
    async def get_uptime_online(self, data) -> bool:
        """Check if the bot is online or not."""
        return self.bot.uptime_is_online


def setup(bot):
    bot.add_cog(IPC(bot))
