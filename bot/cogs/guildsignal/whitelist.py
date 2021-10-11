#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
import functools
import io
import itertools
import re
from typing import Any, Literal, Optional, Union, AsyncGenerator

import abattlemetrics as abm
import discord
from discord.ext import commands, menus
import humanize

from . import format_hour_and_minute, SignalHill
from bot import checks, converters, utils


class SteamIDConverter(commands.Converter):
    """Do basic checks on an integer to see if it may be a valid steam64ID."""
    REGEX = re.compile(r'7656\d{13}')
    INTEGER = 10_000_000_000_000_000

    async def convert(self, ctx, arg):
        if not self.REGEX.match(arg):
            raise commands.BadArgument('Could not parse Steam64ID.')
        return int(arg)


class EmbedPageSourceMixin:
    def get_embed_template(self, menu: menus.MenuPages):
        embed = discord.Embed(
            color=utils.get_bot_color(menu.bot)
        )

        if self.is_paginating():
            max_pages = self.get_max_pages()
            max_pages = '' if max_pages is None else f'/{max_pages}'
            embed.set_author(
                name=f'Page {menu.current_page + 1}{max_pages}'
            )

        return embed


class SessionPageSourceMixin:
    @classmethod
    def format_session(cls, session: abm.Session):
        started_at = session.stop or session.start
        playtime = int(session.playtime)

        # NOTE: humanize.naturaltime() only supports
        # naive local datetimes
        started_at = humanize.naturaltime(
            started_at.astimezone().replace(tzinfo=None)
        )

        return (
            started_at,
            f'Session lasted for {format_hour_and_minute(playtime)}'
            if playtime else 'Session is ongoing'
        )


class LastSessionAsyncPageSource(
        SessionPageSourceMixin, EmbedPageSourceMixin,
        menus.AsyncIteratorPageSource):
    def __init__(self, bm_client, server_id, ids, *, per_page, **kwargs):
        super().__init__(
            self.yield_sessions(bm_client, server_id, per_page + 1, ids),
            # NOTE: per_page + 1 since AsyncIteratorPageSource fetches
            # one extra to know if it has to paginate or not
            per_page=per_page,
            **kwargs
        )

    @staticmethod
    async def yield_sessions(
            bm_client, server_id: int, group_size: int, ids: list):
        """Yield the most recent sessions of a given list of steam/player IDs.

        Args:
            bm_client (abattlemetrics.BattleMetricsClient):
                The client to use for fetching sessions.
            server_id (int): The server's ID to get sessions from.
            group_size (int):
                When there are multiple steam64IDs, this specifies
                how many of those IDs are all matched at once.
                For typical usage in the page source, this should
                be set to per_page + 1.
            ids (Sequence[int]):
                A list of steam64IDs/player IDs to look up.

        Yields:
            Tuple[int, Optional[int], Optional[abattlemetrics.Session]]

        """
        async def fetch_group():
            async def get_session():
                if p_id is None:
                    # no user found for this steam ID
                    return (orig, None, None)

                session = await bm_client.get_player_session_history(
                    p_id, limit=1, server_ids=(server_id,)
                ).flatten()
                if not session:
                    return orig, p_id, None

                return orig, p_id, session[0]

            # Separate steam IDs and player IDs
            steam_ids, player_ids = [], []
            for i, v in enumerate(group):
                if v >= SteamIDConverter.INTEGER:
                    steam_ids.append((i, v))
                else:
                    player_ids.append((i, v, v))

            if steam_ids:
                # Convert steam IDs into player IDs
                results = await bm_client.match_players(
                    *(v for i, v in steam_ids),
                    type=abm.IdentifierType.STEAM_ID
                )
                player_ids.extend((i, v, results[v]) for i, v in steam_ids)
                player_ids.sort()

            for i, orig, p_id in player_ids:
                yield await get_session()

        for n in range(0, len(ids), group_size):
            group = itertools.islice(ids, n, n + group_size)
            async for result in fetch_group():
                yield result

    async def format_page(self, menu: menus.MenuPages, entries):
        embed = self.get_embed_template(menu)
        for i, p_id, session in entries:
            if p_id is None:
                val = 'Unknown steam ID'
            elif session is None:
                val = f'BM ID: {p_id}\n' if i != p_id else ''
                val += 'No session found'
            else:
                val = []
                if i != p_id:
                    val.append(f'BM ID: {p_id}')
                val.append(session.player_name)
                val.extend(self.format_session(session))
                val = '\n'.join(val)

            embed.add_field(name=i, value=val)

        return embed


class PlayerListPageSource(
        SessionPageSourceMixin, EmbedPageSourceMixin,
        menus.AsyncIteratorPageSource):
    def __init__(
            self, list_players, get_session, ids, **kwargs):
        super().__init__(
            self.yield_players(list_players, get_session, ids),
            **kwargs
        )
        self.ids = ids

    @staticmethod
    async def yield_players(list_players, get_session, ids: list):
        """Yield players and optionally their last sessions.

        Args:
            list_players: The BattleMetricsClient.list_players()
                method, which can be partially supplied with
                whatever parameters are desired aside from
                `limit` and `search`.
            get_session
                (Optional[Callable[[int],
                          abattlemetrics.AsyncSessionIterator]]):
                If session data is desired, the
                BattleMetricsClient.get_player_session_history()
                method can be provided for fetching session data.
            ids (Sequence[Union[int, str]]):
                A list of identifiers to look up.

        Yields:
            Tuple[abattlemetrics.Player, Optional[abattlemetrics.Session]]

        """
        max_search = 100
        groups = [
            itertools.islice(ids, n, n + max_search)
            for n in range(0, len(ids), max_search)
        ]
        for g in groups:
            search = '|'.join([str(i) for i in g])
            async for p in list_players(limit=max_search, search=search):
                session = None
                if get_session:
                    try:
                        session = await get_session(p.id, limit=1).next()
                    except StopAsyncIteration:
                        pass

                yield (p, session)

    async def format_page(self, menu: menus.MenuPages, entries):
        embed = self.get_embed_template(menu)

        embed.set_footer(
            text=f'{len(self.ids)} whitelisted players'
        )

        for player, session in entries:
            # Get steam ID
            s_id = discord.utils.get(
                player.identifiers,
                type=abm.IdentifierType.STEAM_ID
            )
            name = s_id.name if s_id else '\u200b'

            val = [
                f'BM ID: {player.id}',
                player.name
            ]
            if session:
                val.extend(self.format_session(session))
            val.append('\u200b')  # helps readability on mobile
            val = '\n'.join(val)

            embed.add_field(name=name, value=val)

        return embed


class WhitelistPageSource(EmbedPageSourceMixin, menus.AsyncIteratorPageSource):
    def __init__(self, channels):
        super().__init__(
            self.yield_pages(self.yield_tickets(channels)),
            per_page=1
        )
        self.channels = channels

    @staticmethod
    def get_ticket_number(channel) -> int:
        m = re.search(r'\d+', channel.name)
        if m:
            return int(m.group())
        return 0

    @functools.cached_property
    def channel_span(self):
        start, end = self.channels[0], self.channels[-1]
        if start == end:
            return str(self.get_ticket_number(start))
        return '{}-{}'.format(
            self.get_ticket_number(start),
            self.get_ticket_number(end)
        )

    @staticmethod
    async def yield_pages(tickets: AsyncGenerator[str, Any]):
        paginator = commands.Paginator(prefix='', suffix='', max_size=4096)
        page_number = 0
        # Yield pages as they are created
        async for line in tickets:
            paginator.add_line(line)

            # Use _pages to not prematurely close the current page
            pages = paginator._pages
            if len(pages) > page_number:
                yield pages[page_number]
                page_number += 1

        yield paginator.pages[-1]

    @staticmethod
    async def yield_tickets(channels):
        async def check(m):
            nonlocal match_
            if m.author.bot:
                return False

            author = member_cache.get(m.author.id)
            if author is None:
                author = m.author
            elif isinstance(author, int):
                return author

            if not isinstance(author, discord.Member):
                try:
                    author = await m.guild.fetch_member(author.id)
                except discord.NotFound:
                    # Return ID to indicate the player has left
                    member_cache[author.id] = author.id
                    return author.id
                member_cache[author.id] = author

            # Optimized way of checking for staff role
            if not author._roles.get(811415496075247649):
                return False
            match_ = converters.CodeBlock.from_search(m.content)
            return match_ is not None and SteamIDConverter.REGEX.search(match_.code)

        member_cache: dict[int, Union[discord.Member, discord.User, int]] = {}

        match_: Optional[converters.CodeBlock] = None
        for c in channels:
            if not re.match(r'.+-\d+', c.name):
                continue

            async for message in c.history():
                status = await check(message)
                if status:
                    break
            else:
                yield f'{c.mention}: no message found'
                continue

            if isinstance(status, int):
                yield f'{c.mention}: <@{status}> has left'
            else:
                match_: converters.CodeBlock
                yield (
                    '{c}: {a} ([Jump to message]({j}))\n`{m}`'.format(
                        c=c.mention,
                        a=message.author.mention,
                        m=match_.code,
                        j=message.jump_url
                    )
                )

    async def format_page(self, menu: menus.MenuPages, page: str):
        embed = self.get_embed_template(menu)
        embed.description = page
        embed.set_author(
            name=(
                f'{embed.author.name} ({self.channel_span})'
                if embed.author else f'Tickets {self.channel_span}'
            )
        ).set_footer(
            text=f'{len(self.channels)} tickets'
        )
        return embed


class _SignalHill_Whitelist(commands.Cog):
    WHITELIST_TICKET_REGEX = re.compile(
        r'(?P<name>.+)-(?P<n>\d+)'
        r'(?:-?(?P<flags>([crt][adpsw])+))?'
        r'(?:-(?P<staff>.+))?'
    )
    WHITELISTED_PLAYERS_CHANNEL_ID = 824486812709027880

    def __init__(self, bot, base: SignalHill):
        self.bot = bot
        self.base = base

    @property
    def whitelist_channel(self):
        return self.bot.get_channel(self.WHITELISTED_PLAYERS_CHANNEL_ID)

    @commands.Cog.listener('on_raw_message_delete')
    @commands.Cog.listener('on_raw_message_edit')
    async def on_whitelist_update(self, payload):
        """Nullify the stored last message ID for the whitelist channel
        if a delete or edit was done inside the channel.
        This is so the "whitelist expired" command knows to refetch
        the list of player IDs.
        """
        if payload.channel_id == self.WHITELISTED_PLAYERS_CHANNEL_ID:
            settings = self.bot.get_cog('Settings')
            if not settings.get('checkwhitelist-last_message_id', None):
                settings.set('checkwhitelist-last_message_id', None).save()

    @commands.group(name='whitelist')
    @commands.has_role('Staff')
    @checks.used_in_guild(SignalHill.GUILD_ID)
    async def client_whitelist(self, ctx):
        """Commands for managing whitelists."""


    async def _whitelist_get_player_ids(self) -> list[int]:
        settings = self.bot.get_cog('Settings')
        ids = settings.get('checkwhitelist-ids', None)
        last_message_id = settings.get('checkwhitelist-last_message_id', None)
        if (self.whitelist_channel.last_message_id != last_message_id
                or ids is None):
            ids = {}  # Use dict to maintain order and uniqueness

            # Fetch IDs from channel
            async for m in self.whitelist_channel.history(
                    limit=None, oldest_first=True):
                for match in SteamIDConverter.REGEX.finditer(m.content):
                    ids[int(match.group())] = None

            # Turn back into list
            ids = list(ids)

            # Cache them in settings
            settings.set(
                'checkwhitelist-ids', ids
            ).set(
                'checkwhitelist-last_message_id',
                self.whitelist_channel.last_message_id
            ).save()

        return ids


    @client_whitelist.command(name='active')
    @commands.cooldown(1, 120, commands.BucketType.default)
    async def client_whitelist_active(self, ctx):
        """Upload a file with two lists for active and expired whitelists."""
        def get_steam_or_bm_id(player: abm.Player) -> int:
            s_id = discord.utils.get(
                player.identifiers,
                type=abm.IdentifierType.STEAM_ID
            )
            return int(s_id.name) if s_id else player.id

        def write_players(players: list[abm.Player]):
            for p in players:
                f.write('{} = {}\n'.format(
                    p.name,
                    get_steam_or_bm_id(p)
                ))

        def sorted_players(players: list[abm.Player]) -> list[abm.Player]:
            mapping = {get_steam_or_bm_id(p): p for p in players}
            new = []
            for i in ids:
                p = mapping.pop(i, None)
                if p is not None:
                    new.append(p)
            new.extend(mapping.values())
            return new

        async with ctx.typing():
            ids = await self._whitelist_get_player_ids()

            # Fetch all whitelisted players
            source = PlayerListPageSource.yield_players(
                functools.partial(
                    self.base.bm_client.list_players,
                    public=False,
                    search='|'.join([str(n) for n in ids]),
                    include_identifiers=True
                ),
                functools.partial(
                    self.base.bm_client.get_player_session_history,
                    server_ids=(self.base.BM_SERVER_ID_INA,)
                ),
                ids
            )

            active, expired = [], []
            old = discord.utils.utcnow() - datetime.timedelta(weeks=2)
            async for player, session in source:
                if session is None or (session.stop or session.start) < old:
                    expired.append(player)
                else:
                    active.append(player)

            f = io.StringIO()
            f.write('===== ACTIVE =====\n\n')
            write_players(sorted_players(active))
            f.write('\n===== EXPIRED =====\n\n')
            write_players(sorted_players(expired))

        f.seek(0)
        await ctx.send(file=discord.File(f, filename='whitelists.txt'))


    @client_whitelist.command(name='accepted', aliases=('approved',))
    @commands.cooldown(2, 60, commands.BucketType.default)
    @commands.max_concurrency(1, commands.BucketType.user)
    async def client_whitelist_accepted(
            self, ctx, open: Literal['open'] = None):
        """List whitelist tickets that have been approved.
This searches up to 100 messages in each whitelist ticket for acceptance from staff.

open: If True, looks through the open whitelist tickets instead of closed tickets."""
        category_id = 824502569652322304 if open else 824502754751152138
        category = ctx.bot.get_channel(category_id)

        if not category.text_channels:
            return await ctx.send('No whitelist tickets are open!')

        menu = menus.MenuPages(
            WhitelistPageSource(category.text_channels),
            clear_reactions_after=True
        )
        async with ctx.typing():
            await menu.start(ctx)

        if menu.should_add_reactions():
            # Wait for menu to finish outside of typing()
            # so it doesn't keep typing but max concurrency is still upheld
            await menu._event.wait()


    @client_whitelist.group(name='expired', invoke_without_command=True)
    @commands.cooldown(2, 60, commands.BucketType.default)
    @commands.max_concurrency(1, commands.BucketType.user)
    async def client_whitelist_expired(self, ctx, sessions: bool = False):
        """Check which whitelisted players have not been online within the last two weeks.
This looks through the steam IDs in the <#824486812709027880> channel.

sessions: If true, fetches session data for each player, including the last time they played. This may make queries slower."""
        async with ctx.typing():
            ids = await self._whitelist_get_player_ids()

        get_session = None
        if sessions:
            get_session = functools.partial(
                self.base.bm_client.get_player_session_history,
                server_ids=(self.base.BM_SERVER_ID_INA,)
            )

        menu = menus.MenuPages(
            PlayerListPageSource(
                functools.partial(
                    self.base.bm_client.list_players,
                    public=False,
                    search='|'.join([str(n) for n in ids]),
                    last_seen_before=discord.utils.utcnow() - datetime.timedelta(weeks=2),
                    include_identifiers=True
                ),
                get_session,
                ids,
                per_page=9
            ),
            clear_reactions_after=True
        )
        async with ctx.typing():
            try:
                await menu.start(ctx)
            except IndexError:
                await ctx.send(
                    f'All {len(ids)} whitelisted players have been active '
                    'within the last 2 weeks!'
                )

        if menu.should_add_reactions():
            # Wait for menu to finish outside of typing()
            # so it doesn't keep typing but max concurrency is still upheld
            await menu._event.wait()


    @client_whitelist_expired.command(name='dump')
    @commands.cooldown(1, 120, commands.BucketType.default)
    async def client_whitelist_expired_dump(self, ctx):
        """Send a list of the expired whitelists."""
        async with ctx.typing():
            ids = await self._whitelist_get_player_ids()
            now = discord.utils.utcnow()

            source = PlayerListPageSource.yield_players(
                functools.partial(
                    self.base.bm_client.list_players,
                    public=False,
                    search='|'.join([str(n) for n in ids]),
                    last_seen_before=now - datetime.timedelta(weeks=2),
                    include_identifiers=True
                ),
                functools.partial(
                    self.base.bm_client.get_player_session_history,
                    server_ids=(self.base.BM_SERVER_ID_INA,)
                ),
                ids
            )

            results = []
            async for player, session in source:
                s_id: Optional[abm.Identifier] = discord.utils.get(
                    player.identifiers,
                    type=abm.IdentifierType.STEAM_ID
                )
                id_: str = s_id.name if s_id else f'{player.id} (BM ID)'

                if session is not None:
                    started_at = session.stop or session.start
                    diff = now - started_at
                    diff_string = utils.timedelta_abbrev(diff)

                    results.append((
                        '{} = {} [{} {}]'.format(
                            player.name,
                            id_,
                            started_at.strftime('%m/%d').lstrip('0'),
                            diff_string
                        ),
                        started_at.timestamp()
                    ))
                else:
                    results.append((
                        '{} = {} [way outdated]'.format(player.name, id_),
                        0
                    ))

        # Sort by most recent
        results.sort(key=lambda x: x[1], reverse=True)

        paginator = commands.Paginator(prefix='', suffix='')
        for line, _ in results:
            paginator.add_line(line)

        for page in paginator.pages:
            await ctx.send(page)


    @client_whitelist.command(name='sort')
    @commands.bot_has_guild_permissions(manage_channels=True)
    @commands.cooldown(1, 120, commands.BucketType.default)
    @commands.max_concurrency(1, commands.BucketType.default)
    async def client_whitelist_sort(self, ctx, labels: bool = True):
        """Sort all the open whitelist tickets.

labels: Group channels together by their labels rather than a simple alphabetical sort."""
        def key(x):
            c, m = x
            if m is None:
                # Place unknown formats at the top
                return '  ' + c.name
            elif labels:
                new_name = '{flags}{n}{name}'.format(**m.groupdict())
                flags = m.group('flags')
                if not flags:
                    # Place unlabeled tickets at the bottom
                    return '~' + new_name
                elif 'a' in flags:
                    # Group accepted tickets together
                    return ' ' + new_name
                return new_name
            return c.name

        await ctx.message.add_reaction('\N{PERMANENT PAPER SIGN}')

        category = ctx.bot.get_channel(824502569652322304)
        tickets = [
            (c, self.WHITELIST_TICKET_REGEX.match(c.name))
            for c in category.text_channels
        ]

        sorted_tickets = sorted(tickets, key=key)

        min_pos = min(c.position for c, m in tickets)
        for i, (ch, _) in enumerate(sorted_tickets, start=min_pos):
            if ch.position == i:
                continue
            await ch.edit(position=i)

        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')





    @commands.command(name='lastsession')
    @commands.has_role('Staff')
    @checks.used_in_guild(SignalHill.GUILD_ID)
    @commands.max_concurrency(1, commands.BucketType.user)
    async def client_last_session(self, ctx, *ids: int):
        """Get one or more players' last session played on the I&A server.

ids: A space-separated list of steam64IDs or battlemetrics player IDs to check."""
        if len(ids) > 100:
            return await ctx.send('You are only allowed to provide 100 IDs at a time.')
        # Remove duplicates while retaining order using dict
        ids = dict.fromkeys(ids)

        menu = menus.MenuPages(
            LastSessionAsyncPageSource(
                self.base.bm_client, self.base.BM_SERVER_ID_INA, ids, per_page=6),
            clear_reactions_after=True
        )
        async with ctx.typing():
            await menu.start(ctx)

        if menu.should_add_reactions():
            # Wait for menu to finish outside of typing()
            # so it doesn't keep typing but max concurrency is still upheld
            await menu._event.wait()





    @commands.command(name='playtime')
    @commands.has_role('Staff')
    @checks.used_in_guild(SignalHill.GUILD_ID)
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def client_playtime(self, ctx, steam_id: SteamIDConverter):
        """Get someone's server playtime in the last month for the I&A server."""
        steam_id: int
        async with ctx.typing():
            results = await self.base.bm_client.match_players(
                steam_id, type=abm.IdentifierType.STEAM_ID)

            try:
                player_id = results[steam_id]
            except KeyError:
                return await ctx.send('Could not find a user with that steam ID!')

            player = await self.base.bm_client.get_player_info(player_id)

            stop = datetime.datetime.now(datetime.timezone.utc)
            start = stop - datetime.timedelta(days=30)
            datapoints = await self.base.bm_client.get_player_time_played_history(
                player_id, self.base.BM_SERVER_ID_INA, start=start, stop=stop)

        total_playtime = sum(dp.value for dp in datapoints)

        if not total_playtime:
            # May be first time joiner and hasn't finished their session
            try:
                session = await self.base.bm_client.get_player_session_history(
                    player_id, limit=1, server_ids=(self.base.BM_SERVER_ID_INA,)
                ).next()
            except StopAsyncIteration:
                return await ctx.send(
                    f'Player: {player.name}\n'
                    'They have never played on this server.'
                )

            if session.stop is None:
                total_playtime = (
                    discord.utils.utcnow() - session.start
                ).total_seconds()
            else:
                total_playtime = session.playtime

        await ctx.send(
            'Player: {}\nPlaytime in the last month: {}'.format(
                player.name, format_hour_and_minute(total_playtime)
            )
        )
