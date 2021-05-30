#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import discord
from discord.ext import commands


class Testing(commands.Cog, command_attrs={'hidden': True}):
    """Testing commands."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return await ctx.bot.is_owner(ctx.author)





    @commands.Cog.listener('on_socket_response')
    async def on_button_interaction(self, m):
        def map_buttons():
            buttons = {}
            for action_row in d['message']['components']:
                for component in action_row['components']:
                    custom_id = component.get('custom_id')
                    if custom_id:
                        buttons[custom_id] = component
            return buttons

        if m['t'] != 'INTERACTION_CREATE':
            return

        d = m['d']
        data = d['data']

        if 'component_type' not in data:
            return

        route = discord.http.Route(
            'POST', '/interactions/{id}/{token}/callback',
            id=d['id'], token=d['token']
        )

        # Get the button that was clicked
        button = map_buttons()[data['custom_id']]

        # send initial response
        payload = {'type': 4, 'data': {
            'content': f"Clicked {button['label']}",
            'flags': 64  # makes message ephemeral/hidden
        }}
        await self.bot.http.request(route, json=payload)










def setup(bot):
    bot.add_cog(Testing(bot))
