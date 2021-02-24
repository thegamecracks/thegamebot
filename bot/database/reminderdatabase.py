"""A database for storing user's reminders.

Table dependencies:
    Users
"""
from . import userdatabase as user_db

TABLE_REMINDERS = """
CREATE TABLE IF NOT EXISTS Reminders (
    reminder_id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    user_id INTEGER NOT NULL,
    due TIMESTAMP,
    content TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES Users(id)
        ON DELETE CASCADE
);
"""


class ReminderDatabase(user_db.UserDatabase):
    """Provide an interface to a UserDatabase with a Reminders table."""

    async def add_reminder(self, user_id: int, due,
                           content: str, *, add_user=True):
        """Add a reminder to the Reminders table.

        Args:
            user_id (int)
            due (datetime.datetime)
            content (str)
            add_user (bool):
                If True, automatically adds the user_id to the Users table.
                Otherwise, the user_id foreign key can be violated.

        """
        user_id = int(user_id)

        if add_user:
            await self.add_user(user_id)

        return await self.add_row('Reminders', {
            'user_id': user_id,
            'due': due,
            'content': content
        })

    async def delete_reminder_by_id(
            self, reminder_id: int, pop=False):
        """Delete a reminder from the Reminders table.

        reminder_id is not escaped.

        Args:
            reminder_id (int)
            pop (bool): If True, gets the reminders before deleting them.

        Returns:
            None
            List[aiosqlite.Row]: A list of deleted entries if pop is True.

        """
        reminder_id = int(reminder_id)

        return await self.delete_rows(
            'Reminders', where=f'reminder_id={reminder_id}', pop=pop)

    async def delete_reminder_by_user_id(
            self, user_id: int, entry_num: int):
        """Delete a reminder from the Reminders table by user_id and entry_num.

        user_id is not escaped.

        """
        user_id = int(user_id)

        reminders = await self.get_reminders(user_id)
        reminder_id = reminders[entry_num]['reminder_id']
        await self.delete_rows(
            'Reminders', where=f'reminder_id={reminder_id}')

    async def get_reminders(self, user_id: int, *, as_row=True):
        """Get one or more reminders for a user.

        user_id is not escaped.

        Args:
            user_id (int): The id of the user to get reminders from.
            as_row (bool)

        """
        user_id = int(user_id)

        return await self.get_rows(
            'Reminders', where=f'user_id={user_id}', as_row=as_row)


def setup(connection):
    """Set up the Reminders table with a sqlite3 connection."""
    with connection as conn:
        conn.execute(TABLE_REMINDERS)
