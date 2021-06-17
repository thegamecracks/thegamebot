#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import json
import os
import pprint
import shutil

from discord.ext import commands

from bot import utils


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
    DEFAULT_SETTINGS_PATH = 'bot/settings_default.json'
    SETTINGS_PATH = 'settings.json'

    EMPTY = object()

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

    def clear(self):
        """Clear the settings cache."""
        self._cache = None

    def get(self, key, default=EMPTY):
        """Get a setting.

        Raises:
            KeyError

        """
        config = self.load()
        if default is self.EMPTY:
            return config[key]
        return config.get(key, default)

    def load(self, *, force=False, autosetup=True):
        """Load the current settings.

        Args:
            force (bool): Forces a cache reset.
            autosetup (bool): Set up the config file
                if the file does not exist. This will still
                raise json.JSONDecodeError if the file is corrupted.

        Returns:
            dict

        Raises:
            FileNotFoundError
            json.JSONDecodeError

        """
        if self._cache is None or force:
            if autosetup:
                self.setup(check_corrupt=False)

            with open(self.path, encoding='utf-8') as f:
                self._cache = json.load(f)

        return self._cache

    def pop(self, key, default=EMPTY):
        """Pop one of the settings."""
        if default is self.EMPTY:
            return self.load().pop(key)
        return self.load().pop(key, default)

    def save(self, ignore_cache=True):
        """Save the current settings to disk.

        This returns self if you want to chain method calls together.

        Args:
            ignore_cache (bool): If the settings are not cached, this will
                automatically load the cache and skip saving
                instead of raising a ValueError.

        Raises:
            ValueError: `ignore_cache` was False and settings were not cached.
            TypeError: The cache could not be serialized.

        """
        if self._cache is None:
            if ignore_cache:
                self.load()
                return self
            else:
                raise ValueError('Settings have not yet been cached')

        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(
                self._cache, f,
                indent=4,
                sort_keys=True
            )

        return self

    def set(self, key: str, value):
        """Add or change a setting.

        This returns self if you want to chain method calls together.

        """
        key = str(key)
        self.load()[key] = value
        return self

    def setup(self, *, force_wipe=False,
              check_existing=True, check_corrupt=True):
        """Set up the config file.

        Saves the generated cache and returns it.

        When copying the default settings, the previous
        settings are backed up.

        Args:
            force_wipe (bool): Force the config file to be set up,
                regardless if it already exists or not.
                This will backup the previous settings if it exists.
            check_existing (bool): If the config file does not exist,
                copies the default settings instead of raising
                FileNotFoundError.
            check_corrupt (bool): If it fails to load the config file,
                copies the default settings instead of raising
                configparser.Error.

        Returns:
            dict

        Raises:
            FileNotFoundError
            configparser.Error

        """
        existing = os.path.isfile(self.path)
        if force_wipe or check_existing and not existing:
            if existing:
                utils.rename_enumerate(self.path, self.path + '.bak')
            shutil.copy(self.default_path, self.path)

        try:
            return self.load(autosetup=False)
        except json.JSONDecodeError:
            if check_corrupt and not force_wipe:
                return self.setup(force_wipe=True)
            raise

    @commands.group(name='cache', hidden=True)
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
        """Display the contents of the settings cache in DMs."""
        await ctx.author.send(pprint.pformat(self._cache))


def setup(bot):
    bot.add_cog(Settings(bot))
