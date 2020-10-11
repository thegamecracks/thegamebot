from . import database as db


class UserDatabase(db.Database):
    "Provide an interface to a database with a Users table."

    def __contains__(self, user_id: int):
        "Test if a user_id exists in the database."
        return self.get_user(user_id) is not None

    def add_user(self, user_id: int):
        """Add a user to the database if the user does not exist.

        user_id is not escaped.

        """
        if user_id not in self:
            self.add_row('Users', {'id': user_id})

    def get_user(self, user_id: int, *, as_Row=True):
        """Get a user record from the database.

        If the user is not found, returns None.

        user_id is not escaped.

        """
        return self.get_one('Users', where=f'id={user_id}', as_Row=as_Row)

    def remove_user(self, user_id: int):
        """Remove a user from the database.

        user_id is not escaped.

        """
        self.delete_rows('Users', where=f'id={user_id}')
