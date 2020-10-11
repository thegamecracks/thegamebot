from . import userdatabase as user_db


class NoteDatabase(user_db.UserDatabase):
    "Provide an interface to a UserDatabase with a Notes table."

    def add_note(self, user_id: int, time_of_entry, content: str, *, add_user=False):
        """Add a note to the Notes table.

        Args:
            user_id (int)
            time_of_entry (datetime.datetime)
            content (str)
            add_user (bool):
                If True, automatically adds the user_id to the Users table.
                Otherwise, the user_id foreign key can be violated.

        """
        if add_user:
            self.add_user(user_id)

        with self.conn as conn:
            conn.execute(
                'INSERT INTO Notes (user_id, time_of_entry, content) '
                'VALUES (?, ?, ?)',
                (user_id, time_of_entry, content)
            )

    def delete_note_by_note_id(self, note_id: int, pop=False):
        """Delete a note from the Notes table.

        note_id is not escaped.

        Args:
            note_id (int)
            pop (bool): If True, gets the notes before deleting them.

        Returns:
            None
            List[sqlite3.Row]: A list of deleted entries if pop is True.

        """
        return self.delete_rows('Notes', where=f'note_id={note_id}', pop=pop)

    def delete_note_by_user_id(self, user_id: int, entry_num: int):
        """Delete a note from the Notes table by user_id and entry_num.

        user_id is not escaped.

        """
        notes = self.get_notes(user_id)
        note_id = notes[entry_num]['note_id']
        self.delete_rows('Notes', where=f'note_id={note_id}')

    def get_notes(self, user_id: int, *, as_Row=True):
        """Get one or more notes for a user.

        user_id is not escaped.

        Args:
            user_id (int): The id of the user to get notes from.

        """
        return self.get_rows(
            'Notes', where=f'user_id={user_id}', as_Row=as_Row)
