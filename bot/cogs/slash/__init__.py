#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import copy
from dataclasses import dataclass, field
import enum
from typing import Union, Optional, Callable, Any, Coroutine

import discord
from discord.ext import commands
import discord.http



MISSING = object()


@dataclass(frozen=True)
class OptionChoice:
    name: str
    value: Union[str, int, float]

    def to_json(self) -> dict:
        return {'name': self.name, 'value': self.value}


class OptionType(enum.Enum):
    SUB_COMMAND = 1
    SUB_COMMAND_GROUP = 2
    STRING = 3
    INTEGER = 4
    BOOLEAN = 5
    USER = 6
    CHANNEL = 7
    ROLE = 8
    MENTIONABLE = 9
    NUMBER = 10


@dataclass
class Option:
    type: OptionType
    name: str
    description: str
    required: bool = False
    choices: Optional[list[OptionChoice]] = None
    options: Optional[list['Option']] = None

    def to_json(self) -> dict:
        payload = {
            'type': self.type.value,
            'name': self.name,
            'description': self.description
        }
        if self.required:
            payload['required'] = True
        if self.choices:
            payload['choices'] = [c.to_json() for c in self.choices]
        if self.options:
            payload['options'] = [o.to_json() for o in self.options]

        return payload

    @classmethod
    def from_json(cls, data: dict):
        choices = data.get('choices')
        options = data.get('options')
        if choices is not None:
            choices = [OptionChoice(**d) for d in data.get('choices', ())]
        if options is not None:
            options = [cls.from_json(d) for d in options]

        return cls(
            type=OptionType(data['type']),
            name=data['name'],
            description=data['description'],
            required=data.get('required', False),
            choices=choices,
            options=options
        )


class ApplicationCommandType(enum.Enum):
    CHAT_INPUT = 1
    USER       = 2
    MESSAGE    = 3


@dataclass
class ApplicationCommand:
    """The base class for application commands."""
    type: ApplicationCommandType
    name: str
    description: str
    default_permission: bool = True
    options: Optional[list[Option]] = None
    guild_id: Optional[int] = None

    # Supplied by the API
    id: Optional[int] = None
    application_id: Optional[int] = None

    # Supplied by ApplicationCommandsCog.__new__
    cog: Optional['ApplicationCommandsCog'] = field(
        default=None, init=False, repr=False, hash=False)

    async def create(self, bot: discord.Client):
        app_id = self.application_id or bot.application_id
        if app_id is None:
            raise ValueError('Bot does not have application_id available')

        if self.guild_id:
            route = discord.http.Route(
                'POST', '/applications/{application_id}/guilds/{guild_id}/commands',
                application_id=bot.application_id, guild_id=self.guild_id
            )
        else:
            route = discord.http.Route(
                'POST', '/applications/{application_id}/commands',
                application_id=bot.application_id
            )

        response: dict = await bot.http.request(route, json=self.to_json())
        return self._update(response)

    async def delete(self, bot: discord.Client):
        if self.id is None:
            await self.fetch(bot)

        if self.guild_id:
            route = discord.http.Route(
                'DELETE', '/applications/{application_id}/guilds/{guild_id}/commands/{command_id}',
                application_id=bot.application_id, guild_id=self.guild_id,
                command_id=self.id
            )
        else:
            route = discord.http.Route(
                'DELETE', '/applications/{application_id}/commands/{command_id}',
                application_id=bot.application_id, command_id=self.id
            )

        await bot.http.request(route)

    async def edit(
        self, bot: discord.Client, *,
        name: str = MISSING,
        description: str = MISSING,
        default_permission: bool = MISSING,
        options: list[Option] = MISSING
    ):
        if self.id is None:
            await self.fetch(bot)

        payload = {}
        if name is not MISSING:
            payload['name'] = name
        if description is not MISSING:
            payload['description'] = description
        if default_permission is not MISSING:
            payload['default_permission'] = default_permission
        if options is not MISSING:
            payload['options'] = [o.to_json() for o in options]

        if not payload:
            raise ValueError('No parameters specified to be edited')

        if self.guild_id:
            route = discord.http.Route(
                'PATCH', '/applications/{application_id}/guilds/{guild_id}/commands/{command_id}',
                application_id=bot.application_id, guild_id=self.guild_id,
                command_id=self.id
            )
        else:
            route = discord.http.Route(
                'PATCH', '/applications/{application_id}/commands/{command_id}',
                application_id=bot.application_id, command_id=self.id
            )

        response: dict = await bot.http.request(route, json=payload)
        return self._update(response)

    async def fetch(self, bot: discord.Client):
        if self.guild_id:
            route = discord.http.Route(
                'GET', '/applications/{application_id}/guilds/{guild_id}/commands/{command_id}',
                application_id=bot.application_id, guild_id=self.guild_id,
                command_id=self.id
            )
        else:
            route = discord.http.Route(
                'GET', '/applications/{application_id}/commands/{command_id}',
                application_id=bot.application_id, command_id=self.id
            )

        response: dict = await bot.http.request(route)
        return self._update(response)

    def is_global(self) -> bool:
        return self.guild_id is None

    def to_json(self) -> dict:
        payload = {
            'name': self.name,
            'description': self.description,
            'default_permission': self.default_permission,
            'type': self.type.value
        }
        if self.options:
            payload['options'] = [o.to_json() for o in self.options]
        return payload

    def _parse_interaction(
        self, bot: discord.Client, interaction: discord.Interaction
    ) -> tuple[tuple, dict]:
        data = interaction.data
        state = bot._connection

        if self.type == ApplicationCommandType.CHAT_INPUT:
            # TODO: implement slash commands
            return (), {}
        elif self.type == ApplicationCommandType.USER:
            user: Union[discord.User, discord.Member]

            target_id, resolved = data['target_id'], data['resolved']
            user_data = resolved['users'][target_id]
            member_data = resolved['members'].get(target_id)
            if member_data:
                member_data['user'] = user_data  # type: ignore
                user = discord.Member(
                    data=member_data,  # type: ignore
                    guild=interaction.guild,
                    state=state
                )
            else:
                user = discord.User(data=user_data, state=state)

            return (user,), {}
        elif self.type == ApplicationCommandType.MESSAGE:
            message: discord.Message

            target_id, resolved = data['target_id'], data['resolved']
            message = discord.Message(
                data=resolved['messages'][target_id],  # type: ignore
                channel=interaction.channel,  # type: ignore
                state=state
            )

            return (message,), {}

        return (), {}

    def _update(self, data: dict):
        options = data.get('options')
        if options is not None:
            options = [Option.from_json(d) for d in options]

        self.id = int(data['id'])
        self.application_id = int(data['application_id'])
        self.name = data['name']
        self.description = data['description']
        self.options = options
        self.default_permission = data.get('default_permission', True)
        # self.type = ApplicationCommandType(data.get('type', 1))
        # self.guild_id = data.get('guild_id')

        return self

    @classmethod
    def from_json(cls, data: dict):
        options = data.get('options')
        if options is not None:
            options = [Option.from_json(d) for d in options]

        return cls(
            id=int(data['id']),
            type=ApplicationCommandType(data.get('type', 1)),
            application_id=int(data['application_id']),
            guild_id=int(data.get('guild_id')),
            name=data['name'],
            description=data['description'],
            options=options,
            default_permission=data.get('default_permission', True)
        )

    @staticmethod
    async def callback(interaction: discord.Interaction, *args, **kwargs):
        """The callback to execute when this command is used."""


def slash_command(
    *, id: int, name: str, description: str, options: list[Option],
    default_permission: bool = True, guild_id: Optional[int] = None
) -> Callable[[Callable[..., Coroutine[Any, Any, Any]]], ApplicationCommand]:
    def decorator(func):
        command = ApplicationCommand(
            type=ApplicationCommandType.CHAT_INPUT,
            name=name,
            description=description,
            options=options,
            default_permission=default_permission,
            guild_id=guild_id,
            id=id
        )
        command.callback = func
        return command
    return decorator


def user_command(
    *, id: int, name: str,
    default_permission: bool = True, guild_id: Optional[int] = None
) -> Callable[[Callable[[discord.Interaction, discord.User], Coroutine[Any, Any, Any]]], ApplicationCommand]:
    def decorator(func):
        command = ApplicationCommand(
            type=ApplicationCommandType.USER,
            name=name,
            description='',
            options=None,
            default_permission=default_permission,
            guild_id=guild_id,
            id=id
        )
        command.callback = func
        return command
    return decorator


def message_command(
    *, id: int, name: str,
    default_permission: bool = True, guild_id: Optional[int] = None
) -> Callable[[Callable[[discord.Interaction, discord.Message], Coroutine[Any, Any, Any]]], ApplicationCommand]:
    def decorator(func):
        command = ApplicationCommand(
            type=ApplicationCommandType.MESSAGE,
            name=name,
            description='',
            options=None,
            default_permission=default_permission,
            guild_id=guild_id,
            id=id
        )
        command.callback = func
        return command
    return decorator


class ApplicationCommandsCogMeta(commands.CogMeta):
    __application_commands__: dict[tuple[Optional[int], int], ApplicationCommand]

    def __new__(cls, *args, **kwargs):
        new_cls = super().__new__(cls, *args, **kwargs)

        application_commands = {}
        for base in reversed(new_cls.__mro__):
            for val in base.__dict__.values():
                if not isinstance(val, ApplicationCommand):
                    continue

                key = (val.guild_id, val.id)
                if val.id is None:
                    raise ValueError(
                        f'"{val.name}" application command must have an id'
                    )
                elif key in application_commands:
                    raise ValueError(
                        f'"{val.name}" application command cannot be '
                        f'registered in the same cog twice'
                    )

                application_commands[key] = val

        new_cls.__application_commands__ = application_commands

        return new_cls


class ApplicationCommandsCog(commands.Cog, metaclass=ApplicationCommandsCogMeta):
    application_commands: dict[tuple[Optional[int], int], ApplicationCommand]

    def __new__(cls, *args, **kwargs):
        obj = super().__new__(cls)

        # Inject the cog into the application commands
        application_commands = {}
        for k, v in cls.__application_commands__.items():
            v = copy.deepcopy(v)
            v.cog = obj
            application_commands[k] = v
        obj.application_commands = application_commands

        return obj

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener('on_interaction')
    async def _on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.application_command:
            return

        command_id = int(interaction.data['id'])
        key = (interaction.guild_id, command_id)
        command = (
            self.application_commands.get(key)
            or self.application_commands.get((None, command_id))
        )
        if command is None:
            return

        args, kwargs = command._parse_interaction(self.bot, interaction)
        if command.cog is not None:
            await command.callback(
                command.cog,  # type: ignore
                interaction, *args, **kwargs
            )
        else:
            await command.callback(interaction, *args, **kwargs)


def setup(bot):
    from . import test, games

    for cls in (
            test.ApplicationCommandTest,
            games.ApplicationCommandGames):
        cog = cls(bot)
        bot.add_cog(cog)
