#  Copyright (C) 2022 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import ast
import configparser
import os
import pprint
import shutil
from typing import Any
import uuid

from disnake.ext import commands

SETTINGS_TYPE = dict[str, dict[str, Any]]

def create_parser():
    return configparser.ConfigParser(default_section='general')


def rename_enumerate(src, dst, **kwargs):
    """Rename a file and automatically enumerate the filename
    if a current file exists with that name:
    foo.bar.bak
    foo1.bar.bak
    foo2.bar.bak
    ...
    Note that this will also skip names used by directories even when
    given a file, and vice versa.
    """
    if not os.path.exists(dst):
        return os.rename(src, dst, **kwargs)

    root, exts = splitext_all(dst)
    ext = ''.join(exts)

    n = 1
    while os.path.exists(dst_new := f'{root}{n}{ext}'):
        n += 1

    return os.rename(src, dst_new, **kwargs)


def splitext_all(path: str) -> tuple[str, list[str]]:
    """Like os.path.splitext except this returns all extensions
    instead of just one.

    :param path:
        The path to split extensions on.
    :return:
        The path root and its list of extensions such that
        the following is true: `root + ''.join(exts) == path`

    """
    root, ext = os.path.splitext(path)

    extensions = [ext]
    root_new, ext = os.path.splitext(root)
    while ext:
        extensions.append(ext)
        root = root_new
        root_new, ext = os.path.splitext(root)
    return root, extensions[::-1]


class Settings(commands.Cog):
    """Manage the bot's settings.

    Methods:
        clear  (): Clear the cache.
        get    (section, key[, default]): Get a setting.
        load   (force=False): Get the dictionary of settings.
        save   (): Save the current cache to disk.
        set    (section, key, value): Set a setting.
        setup  (force_wipe=False): Set up the settings file.

    """
    description = "Manage the bot's settings."
    DEFAULT_SETTINGS_PATH = 'bot/settings_default.ini'
    SETTINGS_PATH = 'settings.ini'

    EMPTY = object()

    _PARSER_BOOLEAN_TRUE = {'yes', 'true', 'on'}
    _PARSER_BOOLEAN_FALSE = {'no', 'false', 'off'}

    def __init__(self, bot, path=None, default_path=None):
        self.bot = bot
        self.path = path if path is not None else self.SETTINGS_PATH
        self.default_path = (default_path if default_path is not None
                             else self.DEFAULT_SETTINGS_PATH)
        self._cache = None
        self.setup()

    async def cog_check(self, ctx):
        return await ctx.bot.is_owner(ctx.author)

    def cog_unload(self):
        """Save the settings on unload."""
        self.save()

    def _load_parse(self, val: str, *, eval=False):
        """Try parsing a string value to either a boolean,
        float, integer, or optionally a Python literal.

        :param val: The string to parse.
        :param eval: Attempt parsing using ast.literal_eval.
        :return: A value or the same string if it could not be parsed.

        """
        # Boolean
        if val.lower() in self._PARSER_BOOLEAN_TRUE:
            return True
        elif val.lower() in self._PARSER_BOOLEAN_TRUE:
            return False

        # Float/Integer
        try:
            n = float(val)
        except ValueError:
            pass
        else:
            if n.is_integer():
                return int(val)
            return n

        # Python literal
        if eval:
            try:
                return ast.literal_eval(val)
            except SyntaxError:
                pass

        # String
        return val

    def _load(self, parser: configparser.ConfigParser, *, eval=False):
        """Load the settings from a ConfigParser."""
        d = {}
        for name, section in parser.items():
            d[name] = {k: self._load_parse(v, eval=eval)
                       for k, v in section.items()}
        return d

    def clear(self):
        """Clear the settings cache."""
        self._cache = None

    def get(self, section: str, key: str, default=EMPTY):
        """Get a setting.

        :param section: The section to look up.
        :param key: The key within the section to look up.
        :param default: An optional default value if the lookup fails.
        :return: The value stored in the key.
        :raises KeyError:
            No default value was provided and the section
            or key does not exist.

        """
        section, key = str(section), str(key)

        d = self.load()

        if default is self.EMPTY:
            return d[section][key]

        sect = d.get(section)
        if sect is None:
            return default

        return sect.get(key, default)

    def load(self, *, force=False, autosetup=True, eval=True) -> SETTINGS_TYPE:
        """Returns the dictionary of settings, either loading
        from the file or the cache.

        :param force:
            Forces the settings to be read even if it is cached.
        :param autosetup:
            Calls `self.setup()` when the settings need to be read.
        :param eval:
            Allows Python literals to be parsed when reading the settings.
        :return: A dictionary of dictionaries where the top-level
            is each section and the nested dictionary are the keys.
        :raises FileNotFoundError:
            The settings file was not set up beforehand and `autosetup`
            was set to False.
        :raises configparser.Error:
            The settings file was malformed.

        """
        if self._cache is None or force:
            if autosetup:
                self.setup(check_corrupt=False)

            parser = create_parser()
            with open(self.path, encoding='utf-8') as f:
                parser.read_file(f)

            self._cache = self._load(parser, eval=eval)
        return self._cache

    def save(self):
        """Save the current settings to disk.

        :raises ValueError: The cache was either empty or could not be parsed.

        """
        if self._cache is None:
            raise ValueError('Settings cache does not exist')

        parser = create_parser()
        try:
            parser.read_dict(self._cache)
        except Exception as e:
            raise ValueError('Could not parse cache') from e

        # atomically overwrite the settings
        temp = '{}-{}.tmp'.format(uuid.uuid4(), self.path)
        with open(temp, 'w', encoding='utf-8') as f:
            parser.write(f, space_around_delimiters=False)
        os.replace(temp, self.path)

    def set(self, section: str, key: str, value):
        """Add or change a setting."""
        section, key = str(section), str(key)
        self.load()[section][key] = value

    def setup(self, *, force_wipe=False,
              check_existing=True, check_corrupt=True) -> SETTINGS_TYPE:
        """Sets up the settings file and returns the cached settings.

        :param force_wipe:
            Forces the config file to be set up,
            regardless if it already exists or not.
            This will back up the previous settings if there are any.
        :param check_existing:
            If the config file does not exist, copies the default settings
            instead of raising FileNotFoundError.
        :param check_corrupt:
            If it fails to load the config file, copies the default
            settings instead of raising configparser.Error.
        :return: The cached settings.
        :raises FileNotFoundError:
            The settings file was not present and
            `check_existing` was set to False.
        :raises configparser.Error:
            The settings file was malformed and
            `check_corrupt` was set to False.

        """
        existing = os.path.isfile(self.path)
        if force_wipe or check_existing and not existing:
            if existing:
                rename_enumerate(self.path, self.path + '.bak')
            shutil.copy(self.default_path, self.path)

        try:
            self._cache = self.load(autosetup=False)
            return self._cache
        except configparser.Error:
            if check_corrupt and not force_wipe:
                return self.setup(force_wipe=True)
            raise

    @commands.group(name='cache', hidden=True)
    @commands.is_owner()
    async def cache_group(self, ctx):
        """Manage the settings cache."""

    @cache_group.command(name='wipe', aliases=('dump', 'clear', 'refresh'))
    @commands.max_concurrency(1)
    async def cache_wipe(self, ctx, save: int = 1):
        """Clear the settings cache.

save:
     1: Save the cache to disk before clearing.
     0: Clear the cache without saving.
    -1: Reset to default settings. This reloads the cache."""
        content = 'Cleared the settings cache.'
        if save > 0:
            self.save()
            self.clear()
            content = 'Saved current settings and cleared the cache.'
        elif save == 0:
            self.clear()
            content = 'Cleared the settings cache.'
        elif save < 0:
            self.setup(force_wipe=True)
            content = 'Reset to default settings and reloaded the cache.'
        await ctx.send(content)

    @cache_group.command(name='show', aliases=('display',))
    async def cache_display(self, ctx):
        """Display the contents of the settings cache.

The message will be given in DMs."""
        await ctx.author.send(pprint.pformat(self._cache))


def setup(bot):
    bot.add_cog(Settings(bot))
