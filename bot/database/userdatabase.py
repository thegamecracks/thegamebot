"""A database for storing user IDs.

Table dependencies:
    None
"""
#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
from typing import Optional

import pytz

from . import database as db


class UserDatabase(db.Database):
    """Provide an interface to a database with a Users table."""

    TABLE_NAME = 'Users'
    TABLE_SETUP = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        id INTEGER PRIMARY KEY NOT NULL,
        timezone TEXT,
        timezone_public BOOLEAN NOT NULL DEFAULT false
    );
    """

    async def add_user(
            self, user_id: int,
            *, timezone: pytz.BaseTzInfo = None) -> bool:
        """Add a user to the database if the user does not exist.

        Returns:
            bool: whether a new row was added or not.

        """
        user_id, timezone = int(user_id), getattr(timezone, 'zone', timezone)

        if await self.get_user(user_id) is None:
            await self.add_row(
                self.TABLE_NAME, {
                    'id': user_id,
                    'timezone': timezone
                }
            )
            return True
        return False


    async def delete_user(self, user_id: int):
        """Delete a user from the database."""
        user_id = int(user_id)
        return await self.delete_rows(self.TABLE_NAME, {'id': user_id})

    async def convert_timezone(self, row) -> Optional[pytz.BaseTzInfo]:
        """Get the timezone of a given user from a row provided
        by get_user().

        In the case that an invalid timezone is inserted into the database,
        this will nullify it and then propagate the exception.

        Args:
            row (sqlite3.Row): The user row to produce the timezone from.
                Technically this could be any object, so long as
                the "timezone" and "id" keys exist.

        """
        timezone = row['timezone']
        if timezone is None:
            return

        try:
            return pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            await self.update_rows(self.TABLE_NAME, {'timezone': None},
                                   where={'id': row['id']})
            raise

    async def get_user(self, user_id: int):
        """Get a user record from the database.

        If the user is not found, returns None.

        """
        user_id = int(user_id)
        return await self.get_one(self.TABLE_NAME, where={'id': user_id})
