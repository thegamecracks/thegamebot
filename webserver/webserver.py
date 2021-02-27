import asyncio
import datetime
import os
import sys

import discord
from discord.ext import ipc
from quart import Quart, render_template, request, session

app = Quart(__name__)
ipc_client = ipc.Client(
    secret_key=os.getenv('PyDiscordBotIPCKey')
)


@app.route('/')
async def index():
    # Uptime field
    uptime_online = await ipc_client.request('get_uptime_online')
    uptime_str = 'Offline'
    if uptime_online:
        uptime_date = await ipc_client.request('get_uptime_date')
        uptime_diff = await ipc_client.request('get_uptime_diff')

        uptime_str = f'{uptime_diff} ({uptime_date})'

    # Version
    vp = sys.version_info
    python_version = f'{vp.major}.{vp.minor}.{vp.micro}'

    # Count
    data = await ipc_client.request('get_number_members')
    is_approximate = data['is_approximate']
    member_count = '{}{:,}'.format(
        '~' if is_approximate else '',
        data['member_count']
    )

    guild_count = await ipc_client.request('get_number_guilds')
    guild_count = f'{guild_count:,}'

    return await render_template(
        'index.html',
        commands=await ipc_client.request('get_number_commands'),
        commands_processed=await ipc_client.request(
            'get_number_commands_processed'),
        guilds=guild_count,
        members=member_count,
        python_version=python_version,
        dpy_version=discord.__version__,
        uptime=uptime_str
    )


@app.route('/shutdown', methods=['POST'])
async def shutdown():
    mode = coro = None
    form = await request.form
    if form['turn_off'] == 'Shutdown':
        mode = 'shutdown'
        coro = ipc_client.request('do_shutdown')
    elif form['turn_off'] == 'Restart':
        mode = 'restart'
        coro = ipc_client.request('do_restart')

    rendered = await render_template(
        'shutdown.html',
        mode=mode
    )

    if coro is not None:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)

    return rendered, 200 + 200 * (mode is None)


if __name__ == '__main__':
    # localhost:5000
    app.run()
