import asyncio

import discord


async def get_reaction(client, message, reactions=None,
                       users=None, *, timeout=None):
    """Return (reaction, user) whenever a reaction is added or removed.

    See https://stackoverflow.com/a/59433241 on awaiting multiple events.

    Args:
        client (discord.Client): The client/bot.
        message (discord.Message): The message to watch for reactions.
        reactions (Optional[List[Union[Emoji, PartialEmoji, str]]]):
            Returns only reaction changes within this list.
            If None, returns any reaction change.
        timeout (Optional[float]): The timeout period.
            Raises TimeoutError.
        users (Optional[List[discord.User]]): A list of users
            that are allowed to react to the message.
            If None, returns any user's reaction change.
        timeout (Optional[float]): The timeout period.
            Raises TimeoutError.

    Returns:
        Tuple[discord.Reaction, discord.User]

    Raises:
        TimeoutError

    """
    def check(r: discord.Reaction, u: discord.User):
        result = r.message.id == message.id

        if reactions:
            result = result and r.emoji in reactions
        if users:
            result = result and u.id in (u1.id for u1 in users)

        return result

    pending_tasks = [
        client.wait_for('reaction_add', check=check),
        client.wait_for('reaction_remove', check=check),
    ]
    try:
        completed_tasks, pending_tasks = await asyncio.wait(
            pending_tasks, return_when=asyncio.FIRST_COMPLETED,
            timeout=timeout
        )
        result = completed_tasks.pop().result()
    except KeyError:
        # Timed out!
        raise asyncio.TimeoutError(
            'Timed out while waiting for reaction change')
    else:
        return result
    finally:
        for task in pending_tasks:
            task.cancel()
        # If any exception happened in any other done tasks
        # we don't care about the exception, but don't want the noise of
        # non-retrieved exceptions
        for task in completed_tasks:
            task.exception()
