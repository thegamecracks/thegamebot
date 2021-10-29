#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import functools

import discord
from . import *


class ApplicationCommandGames(ApplicationCommandsCog):
    @staticmethod
    def make_send_meth(interaction: discord.Interaction):
        @functools.wraps(interaction.response.send_message)
        async def wrapper(*args, **kwargs):
            await interaction.response.send_message(*args, **kwargs)
            return await interaction.original_message()
        return wrapper

    @user_command(
        id=880809891873304636,
        name='Rock Paper Scissors'
    )
    async def rps(self, interaction: discord.Interaction, user: discord.Member):
        command = self.bot.get_command('rps')
        if command is None:
            return await interaction.response.send_message(
                'This command is currently unavailable.',
                ephemeral=True
            )
        elif user.bot:
            return await interaction.response.send_message(
                'You cannot duel a bot!',
                ephemeral=True
            )

        RPSDuelView = command.callback.__globals__['RPSDuelView']
        cog = command.cog
        view = RPSDuelView(
            cog._create_buttons(cog.STANDARD),
            {interaction.user, user},
            timeout=180
        )

        send_meth = self.make_send_meth(interaction)
        await view.start(send_meth)
