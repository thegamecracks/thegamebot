from . import database as db


class UserDatabase(db.Database):
    "Provide an interface to a database with a Users table."

    def add_user(self, user_id):
        "Add a user to the database if the user does not exist."
    def get_user(self, user_id):
        "Get a user record from the database."
    def remove_user(self, user_id):
        "Remove a user from the database."
