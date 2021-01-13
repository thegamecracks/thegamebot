import json
import os
import random

import aiohttp
import discord
from discord.ext import commands

from bot import utils

CAT_API_URL = 'https://api.thecatapi.com/'
CAT_API_KEY = os.getenv('PyDiscordBotAPICatKey')
DOG_API_URL = 'https://api.thedogapi.com/'
DOG_API_KEY = os.getenv('PyDiscordBotAPIDogKey')


async def query_thatapiguy(url, key):
    search = 'v1/images/search?mime_types=jpg,png'

    async with aiohttp.ClientSession(
            headers={'x-api-key': key}) as session:
        async with session.get(url + search) as response:
            if response.status >= 400:
                raise ValueError(response.status, response.reason)

            # Acquire the json, disabling content-type check
            return (await response.json(content_type=None))[0]


def embed_thatapiguy(ctx, response: dict):
    return discord.Embed(
        color=utils.get_user_color(ctx.author)
    ).set_footer(
        text=f'Requested by {ctx.author.name}',
        icon_url=ctx.author.avatar_url
    ).set_image(
        url=response['url']
    )


class Images(commands.Cog):
    qualified_name = 'Images'
    description = 'Commands for getting images.'

    def __init__(self, bot):
        self.bot = bot





    @commands.command(name='meow')
    @commands.cooldown(1, 20, commands.BucketType.channel)
    @commands.max_concurrency(3)
    async def client_getcatimage(self, ctx):
        """\N{CAT FACE}"""
        if CAT_API_KEY is None:
            await ctx.send(
                'Sorry, but the bot currently cannot query for a cat image.',
                delete_after=10
            )
            return await asyncio.sleep(10)

        await ctx.trigger_typing()

        try:
            cat = await query_thatapiguy(CAT_API_URL, CAT_API_KEY)
        except ValueError as e:
            return await ctx.send(
                f'Could not get a cat image; status code {e.args[1]}',
                delete_after=8
            )

        await ctx.send(embed=embed_thatapiguy(ctx, cat))





    @commands.command(name='woof')
    @commands.cooldown(1, 20, commands.BucketType.channel)
    @commands.max_concurrency(3)
    async def client_getdogimage(self, ctx):
        """\N{DOG FACE}"""
        if DOG_API_KEY is None:
            await ctx.send(
                'Sorry, but the bot currently cannot query for a dog image.',
                delete_after=10
            )
            return await asyncio.sleep(10)

        await ctx.trigger_typing()

        try:
            dog = await query_thatapiguy(DOG_API_URL, DOG_API_KEY)
        except ValueError as e:
            return await ctx.send(
                f'Failed to query a dog image; status code {e.args[1]}',
                delete_after=8
            )

        await ctx.send(embed=embed_thatapiguy(ctx, dog))










def setup(bot):
    bot.add_cog(Images(bot))
