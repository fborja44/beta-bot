from pprint import pprint

from discord import Guild, Interaction

import db.mdb as mdb

# guild.py
# Discord guilds used by the bot

GUILDS = "guilds"


async def get_all_guilds():
    """Returns all guilds in the database.

    Returns:
        A list of all guild documents in the database.
    """
    return await mdb.find_all(GUILDS)


async def find_guild(guild_id: int):
    """Finds a guild in the database.

    Args:
        guild_id (int): The target guild id.

    Returns:
        The guild document if found. None otherwise.
    """
    return await mdb.find_document({"guild_id": guild_id}, GUILDS)


async def find_add_guild(guild: Guild):
    """Finds a guild in the database or adds it if it does not exist.

    Args:
        guild (Guild): The target discord guild.

    Returns:
        The guild document if found. If not found, returns the new guild document. On error, returns None.
    """
    guild_id = guild.id
    db_guild = await find_guild(guild_id)
    if db_guild:
        return db_guild
    else:
        return await add_guild(guild)


async def find_update_add_guild(guild: Guild):
    """Finds a guild in the database and updates it or adds it if it does not exist.

    Args:
        guild (Guild): The target discord guild.

    Returns:
        The updated guild document if found. If not found, returns the new guild document. On error, returns None.
    """
    guild_id = guild.id
    db_guild = await find_guild(guild_id)
    if db_guild:
        return await update_guild(guild)
    else:
        return await add_guild(guild)


async def add_guild(guild: Guild):
    """Creates a new guild document in the database.

    Args:
        guild (Guild): The target discord guild to add.

    Returns:
        The new guild document if successful. Otherwise, None.
    """
    new_guild = {
        "guild_id": guild.id,
        "name": guild.name,
        "config": {
            # "tournament_channels": [],          # ! [DEPRECATED ] List of ForumChannels/TextChannels (id) where users can create tournaments
            "create_events": False,  # TODO: Option to create server events with tournaments
            "disable_tournaments": False,  # TODO: Disables user created tournament commands
            "disable_challenges": False,  # TODO: Disables challenges
            "disable_leaderboard": False,  # TODO: Disables leaderboard commands
        },
        "tournaments": [],
        "challenges": [],
        "leaderboard": [],
    }

    # Add to database
    document_id = await mdb.add_document(new_guild, GUILDS)
    if document_id:
        print(f"Successfully added guild ['name'='{guild.name}'] to database.")
        return new_guild
    print(f"Failed to add guild ['name'='{guild.name}'] to database.")
    return None


async def update_guild(guild: Guild):
    """Updates a guild document in the database.

    Args:
        guild (Guild): The target discord guild to update.

    Returns:
        The updated guild document if successful. Otherwise, None.
    """
    db_guild = await mdb.update_single_document(
        {"guild_id": guild.id}, {"$set": {"name": guild.name}}, GUILDS
    )
    if db_guild:
        print(f"Successfully updated guild ['name'='{guild.name}'] in database.")
        return db_guild
    print(f"Failed to update guild ['name'='{guild.name}'] in database.")
    return None


async def set_guild(guild_id: int, new_guild: dict):
    """Sets a guild document in the database to the specified document

    Args:
        guild_id (int): The target guild id.
        new_guild (dict): The new guild document.

    Returns:
        The new guild document if successful. Otherwise, None.
    """
    db_guild = await mdb.update_single_document(
        {"guild_id": guild_id}, {"$set": new_guild}, GUILDS
    )
    if db_guild:
        print(f"Successfully set guild ['id'='{guild_id}'] in database.")
        return db_guild
    print(f"Failed to set guild ['id'='{guild_id}'] in database.")
    return None


async def delete_guild(guild: Guild):
    """Deletes a guild document in the database.

    Args:
        guild (Guild): The target discord guild to delete.

    Returns:
        The result object if successful. Otherwise, None.
    """
    delete_result = await mdb.delete_document({"guild_id": guild.id}, GUILDS)
    if delete_result:
        print(f"Successfully deleted guild ['name'='{guild.name}'] from database.")
        return delete_result
    print(f"Failed to delete guild ['name'='{guild.name}'] in database.")
    return None


async def push_to_guild(guild: Guild, target_array: str, document: dict):
    """Adds a new subdocument to a guild.

    Args:
        guild (Guild): The target guild to update.
        target_array (str): The target subdocument collection.
        document (dict): The document to add.

    Returns:
        The added document if successful. Otherwise, None.
    """
    guild_id = guild.id
    document_id = document["id"]
    db_guild = await find_add_guild(guild)
    if not db_guild:
        return None
    db_guild = await mdb.update_single_document(
        {"guild_id": guild_id}, {"$push": {target_array: document}}, GUILDS
    )
    if db_guild:
        print(
            f"Successfully pushed subdocument ['id'={document_id}] to field '{target_array}' in guild ['name'='{guild.name}']."
        )
        return document
    print(
        f"Failed to push subdocument ['id'='{document_id}'] to field '{target_array}' in guild ['name'='{guild.name}']."
    )
    return None


async def pull_from_guild(guild: Guild, target_array: str, document: dict):
    """Removes a subdocument from a guild.

    Args:
        guild (Guild): The target gulid to update.
        target_array (str): The target subdocument collection
        document (dict): The document to remove.

    Returns:
        The removed document if successful. Otherwise, None.
    """
    guild_id = guild.id
    document_id = document["id"]
    db_guild = await find_add_guild(guild)
    if not db_guild:
        return None
    updated_guild = await mdb.update_single_document(
        {"guild_id": guild_id}, {"$pull": {target_array: {"id": document_id}}}, GUILDS
    )
    if updated_guild:
        print(
            f"Successfully pulled subdocument ['id'={document_id}] from field '{target_array}' in guild ['name'='{guild.name}']."
        )
        return updated_guild
    print(
        f"Failed to pull subdocument ['id'={document_id}] to field '{target_array}' in guild ['name'='{guild.name}']."
    )
    return None


#######################
## COMMAND FUNCTIONS ##
#######################


async def update_tournament_channel(interaction: Interaction, channel_name: str):
    """ "
    TODO
    Updates the tournament channel in a guild
    """


async def toggle_tournament_events(interaction: Interaction):
    """
    TODO
    Toggles create_events option.
    """


async def toggle_tournaments(interaction: Interaction):
    """
    TODO
    Toggles the disable_tournaments option.
    """


async def toggle_challenges(interaction: Interaction):
    """
    TODO
    Toggles the disable_challenges option.
    """


async def toggle_leaderboard(interaction: Interaction):
    """
    TODO
    Toggles the disable_leaderboard option.
    """
