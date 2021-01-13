from .database import Database
from .dbsetup import (
    DATABASE_IRISH, DATABASE_USERS,
    GameDatabase, IrishDatabase, NoteDatabase, PrefixDatabase,
    ReminderDatabase, UserDatabase, get_prefix, setup
)
from . import gamedatabase
from . import irishdatabase
from . import notedatabase
from . import prefixdatabase
from . import reminderdatabase
from . import userdatabase
