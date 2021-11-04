"""A database for storing users' notes.

Table dependencies:
    Guilds
    Users
"""
#  Copyright (C) 2021 thegamecracks
#  This Source Code Form is subject to the terms of the Mozilla Public
#  License, v. 2.0. If a copy of the MPL was not distributed with this
#  file, You can obtain one at http://mozilla.org/MPL/2.0/.
import datetime
from typing import Iterable, Optional, Union

from . import database as db


class NoteDatabase(db.Database):
    """Provide an interface to a UserDatabase with a Notes table."""

    TABLE_NAME = 'Notes'
    TABLE_SETUP = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        note_id INTEGER PRIMARY KEY NOT NULL,
        user_id INTEGER NOT NULL,
        guild_id INTEGER DEFAULT NULL,
        time_of_entry TIMESTAMP,
        content TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES Users(id)
            ON DELETE CASCADE,
        FOREIGN KEY (guild_id) REFERENCES Guilds(id)
            ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS ix_notes_users ON {TABLE_NAME}(user_id, guild_id);
    """

    async def add_note(
        self, user_id: int, guild_id: Optional[int],
        time_of_entry: datetime.datetime, content: str
    ) -> int:
        """Add a note to the Notes table.

        Note that the user should be in the database beforehand.

        Args:
            user_id (int): The user that owns the note.
            guild_id (Optional[int]): The guild this note is for.
            time_of_entry (datetime.datetime): The datetime this note has been added.
            content (str): The content of this note.

        Returns:
            int: The id of the row that was added.

        """
        user_id = int(user_id)
        content = str(content)
        if guild_id is not None:
            guild_id = int(guild_id)

        return await self.add_row(self.TABLE_NAME, {
            'user_id': user_id,
            'guild_id': guild_id,
            'time_of_entry': time_of_entry,
            'content': content
        })

    async def delete_notes_by_note_id(
            self, note_ids: Union[int, Iterable[int]], pop=False):
        """Delete one or more notes from the Notes table by note id.

        This is an atomic operation.

        Args:
            note_ids (Union[int, Iterable[int]])
            pop (bool): If True, gets the notes before deleting them.

        Returns:
            None
            List[sqlite3.Row]: A list of deleted entries if pop is True.

        """
        if isinstance(note_ids, int):
            note_ids = [(note_ids,)]
        else:
            note_ids = [(int(n),) for n in note_ids]

        rows = None
        async with self.connect(writing=True) as conn:
            async with conn.cursor(transaction=True) as c:
                if pop:
                    await c.execute(
                        'SELECT * FROM {} WHERE note_id IN ({})'.format(
                            self.TABLE_NAME,
                            ', '.join([str(x[0]) for x in note_ids])
                        )
                    )
                    rows = await c.fetchall()
                await c.executemany(
                    f'DELETE FROM {self.TABLE_NAME} WHERE note_id=?',
                    note_ids
                )
        return rows

    async def delete_note_by_user_id(
            self, user_id: int, guild_id: Optional[int], entry_num: int):
        """Delete a note from the Notes table by foreign keys and entry_num."""
        user_id = int(user_id)
        entry_num = int(entry_num)
        if guild_id is not None:
            guild_id = int(guild_id)

        notes = await self.get_notes(user_id, guild_id)
        note_id = notes[entry_num]['note_id']
        await self.delete_rows(self.TABLE_NAME, {'note_id': note_id})

    async def get_notes(self, user_id: int, guild_id: Optional[int]):
        """Get one or more notes for a user.

        Args:
            user_id (int): The id of the user to get notes from.
            guild_id (Optional[int]): The guild this note is in.

        """
        user_id = int(user_id)
        if guild_id is not None:
            guild_id = int(guild_id)

        return await self.get_rows(
            self.TABLE_NAME,
            where={'user_id': user_id, 'guild_id': guild_id}
        )
