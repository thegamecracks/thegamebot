#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
import sqlite3
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils import ConfirmationView, paging
from bot import utils
from main import TheGameBot
from .querier import TagDict, TagQuerier

TAG_MAX_NAME_LENGTH = 50


async def assert_tag_availability(querier: TagQuerier, guild_id: int, name: str):
    """Asserts that the given name can be used for a tag or an alias.

    :raises ValueError: The name is either too long or already exists.

    """
    name = name.casefold()

    diff = len(name) - TAG_MAX_NAME_LENGTH
    if diff > 0:
        raise ValueError(f'The given name is {diff:,} characters too long.')

    tag = await querier.get_tag(guild_id, name, include_aliases=True)
    if tag is not None:
        ref = 'tag' if tag['tag_name'] == name else 'alias'
        raise ValueError(f'A {ref} already exists with the given name.')


def get_querier(bot: TheGameBot):
    return TagQuerier(bot.db)


class VerboseTagDict(TagDict):
    """Provides more details about a given tag.

    from_alias:
        A boolean indicating if the tag was referenced from an alias.
        This is a shorthand for comparing `tag_name` to `raw_name`.
    raw_name:
        The name of the tag typed by the user.

    """
    from_alias: bool
    raw_name: str


class CreateTagModal(discord.ui.Modal, title='Creating your tag...'):
    name = discord.ui.TextInput(label='Name')
    content = discord.ui.TextInput(label='Content', style=discord.TextStyle.paragraph, max_length=2000)

    async def on_submit(self, interaction: discord.Interaction):
        bot = cast(TheGameBot, interaction.client)
        querier = get_querier(bot)

        tag = await querier.get_tag(interaction.guild_id, self.name, include_aliases=True)
        if tag is not None:
            ref = 'tag' if tag['tag_name'] == self.name else 'alias'
            return await interaction.response.send_message(
                '{} already exists with the name "{}".'.format(
                    bot.inflector.a(ref).capitalize(), self.name
                ), ephemeral=True
            )

        await querier.add_tag(
            interaction.guild_id, self.name,
            self.content, interaction.user.id
        )
        await interaction.response.send_message(
            f'Created the tag "{self.name}"!',
            ephemeral=True
        )


class EditTagModal(discord.ui.Modal, title='Editing your tag...'):
    content = discord.ui.TextInput(label='Content', style=discord.TextStyle.paragraph, max_length=2000)

    def __init__(self, name: str, **kwargs):
        super().__init__(**kwargs)
        self.name = name

    async def on_submit(self, interaction: discord.Interaction):
        bot = cast(TheGameBot, interaction.client)
        querier = get_querier(bot)

        await querier.edit_tag(interaction.guild_id, self.name, self.content)
        await interaction.response.send_message(
            'Successfully edited your tag!',
            ephemeral=True
        )


class ExistingTagTransformer(app_commands.Transformer):
    """Fetches a tag from the database."""
    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: str) -> VerboseTagDict:
        querier = get_querier(interaction.client)
        tag = await querier.get_tag(interaction.guild_id, value.casefold(), include_aliases=True)
        if tag is None:
            raise app_commands.AppCommandError(f'The tag "{value}" does not exist.')

        d = dict(tag)
        d['from_alias'] = (d['tag_name'] != value)
        d['raw_name'] = value
        return d


class NewTagTransformer(app_commands.Transformer):
    """Asserts the validity of a new tag name."""
    @classmethod
    async def transform(cls, interaction: discord.Interaction, value: str) -> str:
        assert interaction.guild_id is not None

        querier = get_querier(interaction.client)
        value = value.casefold()

        await assert_tag_availability(querier, interaction.guild_id, value)
        return value


ExistingTagTransform = app_commands.Transform[VerboseTagDict, ExistingTagTransformer]
NewTagTransform = app_commands.Transform[str, NewTagTransformer]


class TagPageSource(paging.AsyncIteratorPageSource[sqlite3.Row, None, paging.PaginatorView]):
    def __init__(
        self, *args,
        bot: TheGameBot,
        row_format: str,
        empty_message: str,
        title: str = None,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.row_format = row_format
        self.empty_message = empty_message
        self.title = title

    async def format_page(self, view: paging.PaginatorView, page: list[TagDict]):
        def get_extras(row: TagDict):
            user_id = row['user_id']
            uses = row['uses']
            return {
                'owned_by': f"owned by <@{user_id}>" if user_id else 'no owner',
                'n_uses': self.bot.inflector.plural(f'used {uses:,} time', uses)
            }

        if not page:
            return self.empty_message

        start = view.current_index * self.page_size
        lines = [
            self.row_format.format(
                i=i, **get_extras(row), **row
            )  # type: ignore
            for i, row in enumerate(page, start=start + 1)
        ]

        return discord.Embed(
            color=self.bot.get_bot_color(),
            description=f'\n'.join(lines),
            title=self.title
        )


@app_commands.guild_only()
class Tags(commands.GroupCog, name='tag'):
    """Store and use guild-specific tags."""
    TAG_BY_MAX_DISPLAYED = 10
    TAG_LEADERBOARD_MAX_DISPLAYED = 10

    def __init__(self, bot: TheGameBot):
        self.bot = bot
        self.tags = TagQuerier(self.bot.db)

    def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    @app_commands.command(name='send')
    @app_commands.checks.cooldown(1, 2)
    @app_commands.describe(
        tag='The name of the tag to send.'
    )
    async def tag(
        self, interaction: discord.Interaction,
        tag: ExistingTagTransform
    ):
        """Send a tag in the current channel."""
        await interaction.response.send_message(
            tag['content'],
            allowed_mentions=discord.AllowedMentions.none()
        )

        await self.tags.edit_tag(
            interaction.guild_id, tag['tag_name'],
            uses=tag['uses'] + 1,
            record_time=False
        )

    @app_commands.command(name='alias')
    @app_commands.checks.cooldown(1, 10)
    @app_commands.describe(
        tag='The name of the tag you are creating a new alias for.',
        alias='The name of the alias you want to make.'
    )
    async def tag_alias(
        self, interaction: discord.Interaction,
        tag: ExistingTagTransform,
        alias: NewTagTransform
    ):
        """Create an alias for an existing tag."""
        await self.tags.add_alias(
            interaction.guild_id, alias, tag['tag_name'],
            interaction.user.id
        )

        await interaction.response.send_message(
            'Created your new alias!',
            ephemeral=True
        )

    @app_commands.command(name='claim')
    @app_commands.checks.cooldown(1, 5)
    @app_commands.describe(
        tag='The name of the tag you want to claim.'
    )
    async def tag_claim(self, interaction: discord.Interaction, tag: ExistingTagTransform):
        """Claim a tag or alias made by someone that is no longer in the server."""
        ref = 'alias' if tag['from_alias'] else 'tag'

        if tag['user_id'] is not None:
            return await interaction.response.send_message(
                f"This {ref} is already owned by <@{tag['user_id']}>!",
                ephemeral=True
            )

        args = (interaction.guild_id, tag['raw_name'], interaction.user.id)
        if tag['from_alias']:
            await self.tags.set_alias_author(*args)
        else:
            await self.tags.set_tag_author(*args)

        await interaction.response.send_message(
            'You now own the {} "{}"!'.format(ref, tag['raw_name']),
            ephemeral=True
        )

    @app_commands.command(name='create')
    @app_commands.checks.cooldown(1, 10)
    async def tag_create(self, interaction: discord.Interaction):
        """Open a modal to fill out the new tag you want to create."""
        await interaction.response.send_modal(CreateTagModal())

    @app_commands.command(name='delete')
    @app_commands.describe(
        tag='The name of the tag you want to delete.'
    )
    async def tag_delete(self, interaction: discord.Interaction, tag: ExistingTagTransform):
        """Delete one of your tags or aliases (or someone else's, if you have Manage Server permission)."""
        if tag['user_id'] != interaction.user.id and not interaction.permissions.manage_guild:
            return await interaction.response.send_message(
                'You cannot delete a tag made by someone else.',
                ephemeral=True
            )

        tag_name = tag['tag_name']
        if tag['from_alias']:
            await self.tags.delete_alias(interaction.guild_id, tag['raw_name'])
            content = f'Successfully deleted an alias for "{tag_name}"!'
        else:
            await self.tags.delete_tag(interaction.guild_id, tag['raw_name'])
            content = f'Successfully deleted the tag "{tag_name}"!'

        await interaction.response.send_message(content, ephemeral=True)

    @app_commands.command(name='edit')
    @app_commands.describe(
        tag='The name of the tag you want to edit.'
    )
    async def tag_edit(self, interaction: discord.Interaction, tag: ExistingTagTransform):
        """Open a modal to edit one of your tags."""
        if tag['user_id'] != interaction.user.id:
            return await interaction.response.send_message(
                'You cannot edit a tag made by someone else.',
                ephemeral=True
            )

        await interaction.response.send_modal(EditTagModal(tag['tag_name']))

    @app_commands.command(name='info')
    @app_commands.describe(
        tag='The name of the tag you want to inspect.'
    )
    async def tag_info(self, interaction: discord.Interaction, tag: ExistingTagTransform):
        """Display information about a tag."""
        owner_id = tag['user_id']
        owner_mention = f'<@{owner_id}>' if owner_id else 'No owner'

        embed = discord.Embed(
            color=self.bot.get_bot_color()
        ).add_field(
            name='Owner',
            value=owner_mention
        ).add_field(
            name='Time of Creation',
            value=discord.utils.format_dt(tag['created_at'], 'F'),
            inline=False
        )

        if tag['from_alias']:
            title = tag['raw_name']
            embed.add_field(
                name='Original',
                value=tag['tag_name']
            )

        else:
            title = tag['raw_name']
            embed.add_field(
                name='Uses',
                value=format(tag['uses'], ',')
            )

            aliases = await self.tags.get_aliases(interaction.guild_id, tag['raw_name'])
            if aliases:
                embed.add_field(
                    name='Aliases',
                    value=', '.join(r['alias_name'] for r in aliases)
                )

            if tag['edited_at'] is not None:
                embed.add_field(
                    name='Last Edited',
                    value=discord.utils.format_dt(tag['edited_at'], 'F'),
                    inline=False
                )

        embed.description = f'**{title}**'

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='leaderboard')
    @app_commands.checks.cooldown(1, 10)
    async def tag_leaderboard(self, interaction: discord.Interaction):
        """Browse through the top tags used in this server."""
        view = paging.PaginatorView(
            sources=TagPageSource(
                self.tags.yield_tags(interaction.guild_id, column='uses', reverse=True),
                bot=interaction.client,
                row_format='**{i:,}.** {tag_name} ({n_uses}, {owned_by})',
                empty_message='This server currently has no tags to list.',
                title='Tag leaderboard',
                page_size=self.TAG_LEADERBOARD_MAX_DISPLAYED
            ),
            allowed_users={interaction.user.id},
            timeout=60
        )
        await view.start(interaction)
        await view.wait()

    @app_commands.command(name='list')
    @app_commands.checks.cooldown(1, 10)
    @app_commands.describe(
        user='The user to list tags from. If empty, your tags will be listed.'
    )
    async def tag_list(self, interaction: discord.Interaction, user: discord.Member = None):
        """Get a list of the top tags you or someone else owns."""
        user = user or interaction.user

        empty_message = 'This user currently has no tags to list.'
        title = f'Tags owned by {user.display_name}'
        if user == interaction.user:
            empty_message = 'You do not have any tags to list.'
            title = 'Tags owned by you'

        view = paging.PaginatorView(
            sources=TagPageSource(
                self.tags.yield_tags(interaction.guild_id, column='uses', where={'user_id = ?': user.id}, reverse=True),
                bot=interaction.client,
                row_format='**{i:,}.** {tag_name}',
                empty_message=empty_message,
                title=title,
                page_size=self.TAG_LEADERBOARD_MAX_DISPLAYED
            ),
            allowed_users={interaction.user.id},
            timeout=60
        )
        await view.start(interaction)
        await view.wait()

    @app_commands.command(name='raw')
    @app_commands.checks.cooldown(1, 5)
    @app_commands.describe(
        tag='The name of the tag you want to display. Only you will see the content.'
    )
    async def tag_raw(self, interaction: discord.Interaction, *, tag: ExistingTagTransform):
        """Show a tag in its raw form.
Useful for copying a tag with any of its markdown formatting."""
        escaped = utils.rawify_content(tag['content'])
        await interaction.response.send_message(escaped, ephemeral=True)

    @app_commands.command(name='reset')
    @app_commands.checks.cooldown(1, 60, key=lambda interaction: interaction.guild_id)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def tag_reset(self, interaction: discord.Interaction):
        """Remove all tags in the server."""
        view = ConfirmationView(interaction.user)
        await view.start(
            interaction,
            color=self.bot.get_bot_color(),
            title="Are you sure you want to reset the server's tags?"
        )

        if await view.wait_for_confirmation():
            await self.tags.wipe(interaction.guild_id)
            await view.update('Wiped all tags!', color=view.YES)
        else:
            await view.update('Cancelled tag reset.', color=view.NO)


async def setup(bot: TheGameBot):
    await bot.add_cog(Tags(bot))
