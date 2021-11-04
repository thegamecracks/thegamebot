"""A database for storing users' reminders.

Table dependencies:
    Users
"""
#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
from typing import Optional, TypedDict

from . import database as db


class PartialReminderEntry(TypedDict):
    user_id: int
    channel_id: int
    due: datetime.datetime
    content: str


class ReminderEntry(PartialReminderEntry):
    reminder_id: int


class ReminderDatabase(db.Database):
    """Provide an interface to a UserDatabase with a Reminders table."""

    TABLE_NAME = 'Reminders'
    TABLE_SETUP = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        reminder_id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
        user_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        due TIMESTAMP,
        content TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES Users(id)
            ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS ix_reminders_users ON {TABLE_NAME}(user_id);
    CREATE INDEX IF NOT EXISTS ix_reminders_channels ON {TABLE_NAME}(channel_id);
    CREATE INDEX IF NOT EXISTS ix_reminders_user_channel ON {TABLE_NAME}(user_id, channel_id);
    """

    async def add_reminder(
            self, user_id: int, channel_id: int,
            due: datetime.datetime, content: str):
        """Add a reminder to the Reminders table.

        Args:
            user_id (int): The user that created the reminder.
            channel_id (int): The channel to send the reminder.
            due (datetime.datetime): When the reminder should be sent.
            content (str): The content of the reminder.

        """
        user_id = int(user_id)

        return await self.add_row(
            self.TABLE_NAME,
            {'user_id': user_id,
             'channel_id': channel_id,
             'due': due.astimezone(datetime.timezone.utc).replace(tzinfo=None),
             # NOTE: due to a bug with sqlite3.dbapi2.convert_timestamp,
             # timezones cannot be included when the microsecond
             # is omitted by isoformat()
             'content': content}
        )

    async def delete_reminder_by_id(self, reminder_id: int, pop=False):
        """Delete a reminder from the Reminders table.

        Args:
            reminder_id (int)
            pop (bool): If True, gets the reminders before deleting them.

        Returns:
            None
            List[sqlite3.Row]: A list of deleted entries if pop is True.

        """
        reminder_id = int(reminder_id)

        return await self.delete_rows(
            self.TABLE_NAME, {'reminder_id': reminder_id}, pop=pop
        )

    async def delete_reminder_by_user_id(
            self, user_id: int, entry_num: int, pop=False):
        """Delete a reminder from the Reminders table by user_id and entry_num."""
        user_id = int(user_id)

        reminders = await self.get_reminders(user_id)
        reminder_id = reminders[entry_num]['reminder_id']
        return await self.delete_rows(
            self.TABLE_NAME, {'reminder_id': reminder_id}, pop=pop
        )

    async def get_reminders(self, user_id: int, *columns: str):
        """Get one or more reminders for a user.

        Args:
            user_id (int): The id of the user to get reminders from.
            columns (str): The columns to extract.
                If no columns are provided, returns all columns.

        """
        user_id = int(user_id)

        return await self.get_rows(
            self.TABLE_NAME, *columns, where={'user_id': user_id})
