from . import userdatabase as user_db


class NoteDatabase(user_db.UserDatabase):
    "Provide an interface to a UserDatabase with a Notes table."

    def add_note(self, user_id, content):
        "Add a note to the Notes table."
    def remove_note(self, user_id, entry_num):
        "Remove a note from the Notes table."
    def get_notes(self, user_id, entry_num=None):
        "Get one or more notes for a user."
