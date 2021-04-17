"""A database for the Irish Squad server.

This stores its own users.
"""
from . import database as db
from .userdatabase import UserDatabase


class ChargeDatabase(db.Database):
    """Provide an interface to the Charges table."""

    TABLE_NAME = 'Charges'
    TABLE_SETUP = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        user_id INTEGER PRIMARY KEY NOT NULL,
        amount INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES Users(id)
            ON DELETE CASCADE
    );
    """

    def __init__(self, db, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db = db

    async def change_charges(self, user_id: int, amount: int, *, add_user=True):
        """Add or subtract charges from a user.

        Args:
            user_id (int)
            amount (int)
            add_user (bool):
                If True, automatically adds the user_id to the Users table.
                Otherwise, the user_id foreign key can be violated.

        """
        user_id = int(user_id)

        charges = await self.get_charges(user_id, add_user=add_user)

        new = charges + amount

        return await self.update_rows(
            self.TABLE_NAME, {'amount': new}, where={'user_id': user_id})

    async def delete_charges(self, user_id: int):
        """Delete a user's charges entry."""
        user_id = int(user_id)

        return await self.delete_rows(self.TABLE_NAME, {'user_id': user_id})

    async def get_charges(self, user_id: int, add_user=True):
        """Get the number of charges a user has.

        Args:
            user_id (int): The id of the user to get their number of charges.
            add_user (bool):
                If True, automatically adds the user_id to the Users table.
                Otherwise, the user_id foreign key can be violated.

        """
        async def get_row():
            return await self.get_one(
                self.TABLE_NAME, 'amount', where={'user_id': user_id})

        user_id = int(user_id)

        if add_user:
            await self.db.users.add_user(user_id)

        row = await get_row()
        if row is None:
            if await self.db.users.get_user(user_id) is None:
                raise ValueError(
                    f'User {user_id!r} does not exist in the database')
            else:
                await self.add_row('Charges', {'user_id': user_id})
                row = await get_row()
        return row['amount']


class IrishDatabase(db.Database):
    """Provide an interface to the Irish Squad's database."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.charges = ChargeDatabase(self, *args, **kwargs)
        self.users = UserDatabase(*args, **kwargs)

    @property
    def TABLE_SETUP(self):
        return '\n'.join([
            self.users.TABLE_SETUP,
            self.charges.TABLE_SETUP
        ])
