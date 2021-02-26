"""A database for storing user's notes.

Table dependencies:
    Users
"""
import datetime

from . import database as db


class NoteDatabase(db.Database):
    """Provide an interface to a UserDatabase with a Notes table."""

    TABLE_NAME = 'Notes'
    TABLE_SETUP = """
    CREATE TABLE IF NOT EXISTS Notes (
        note_id INTEGER PRIMARY KEY NOT NULL,
        user_id INTEGER NOT NULL,
        time_of_entry TIMESTAMP,
        content TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES Users(id)
            ON DELETE CASCADE
    );
    """

    async def add_note(self, user_id: int, time_of_entry: datetime.datetime,
                       content: str):
        """Add a note to the Notes table.

        Args:
            user_id (int)
            time_of_entry (datetime.datetime)
            content (str)

        """
        user_id = int(user_id)
        content = str(content)

        return await self.add_row(self.TABLE_NAME, {
            'user_id': user_id,
            'time_of_entry': time_of_entry,
            'content': content
        })

    async def delete_note_by_note_id(self, note_id: int, pop=False):
        """Delete a note from the Notes table.

        note_id is not escaped.

        Args:
            note_id (int)
            pop (bool): If True, gets the notes before deleting them.

        Returns:
            None
            List[aiosqlite.Row]: A list of deleted entries if pop is True.

        """
        note_id = int(note_id)
        return await self.delete_rows(
            self.TABLE_NAME, where={'note_id': note_id}, pop=pop)

    async def delete_note_by_user_id(self, user_id: int, entry_num: int):
        """Delete a note from the Notes table by user_id and entry_num."""
        user_id = int(user_id)

        notes = await self.get_notes(user_id)
        note_id = notes[entry_num]['note_id']
        await self.delete_rows(self.TABLE_NAME, {'note_id': note_id})

    async def get_notes(self, user_id: int):
        """Get one or more notes for a user.

        Args:
            user_id (int): The id of the user to get notes from.

        """
        user_id = int(user_id)
        return await self.get_rows(self.TABLE_NAME, where={'user_id': user_id})
