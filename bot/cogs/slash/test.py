#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import discord
from . import *


class ApplicationCommandTest(ApplicationCommandsCog):
    @user_command(
        guild_id=297463612870492160,
        id=880622211080261743,
        name='Poke'
    )
    async def poke(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.send_message(
            embeds=[
                discord.Embed(
                    color=interaction.user.color,
                    title=interaction.user.display_name
                ).set_author(
                    name='The Poker'
                ).set_thumbnail(url=interaction.user.display_avatar.url),
                discord.Embed(
                    color=interaction.user.color,
                    title=interaction.user.display_name
                ).set_author(
                    name='The Poked'
                ).set_thumbnail(url=user.display_avatar.url)
            ],
            ephemeral=True
        )

    @message_command(
        guild_id=297463612870492160,
        id=880638641318277201,
        name='Length'
    )
    async def length(self, interaction: discord.Interaction, message: discord.Message):
        await interaction.response.send_message(
            f'This message has {len(message.content):,} characters!',
            ephemeral=True
        )
