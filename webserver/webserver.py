import datetime
import os

from discord.ext import ipc
from quart import Quart, render_template, request, session

app = Quart(__name__)
ipc_client = ipc.Client(
    secret_key=os.getenv('PyDiscordBotIPCKey')
)


@app.route('/')
async def index():
    # Uptime field
    uptime_date = await ipc_client.request('get_uptime_date')
    uptime_diff = await ipc_client.request('get_uptime_diff')

    return await render_template(
        'index.html',
        uptime=f'{uptime_diff} ({uptime_date})'
    )


if __name__ == '__main__':
    # localhost:5000
    app.run()
