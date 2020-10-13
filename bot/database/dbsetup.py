"""Provides functions for setting up the bot's databases."""
import sqlite3

from . import database
from . import notedatabase
from . import userdatabase

DATABASE_USERS = './data/userdb.db'

dbconn_users = database.DatabaseConnection(DATABASE_USERS)


def setup_database_users(connection):
    userdatabase.setup(connection)
    notedatabase.setup(connection)
    print('Verified user database')


def setup():
    setup_database_users(sqlite3.connect(DATABASE_USERS))
