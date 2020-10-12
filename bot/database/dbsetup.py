"""Provides functions for setting up the bot's databases."""
from . import database
from . import notedatabase
from . import userdatabase

DATABASE_USERS = './data/userdb.db'

dbconn_users = database.DatabaseConnection(DATABASE_USERS)


def setup_database_users(dbconn):
    userdatabase.setup(dbconn)
    notedatabase.setup(dbconn)
    print('Verified user database')


def setup():
    setup_database_users(dbconn_users)


if __name__ == '__main__':
    # File being executed directly; set up databases relative to this file
    dbconn_users = database.DatabaseConnection('../../data/userdb.db')
    setup()
