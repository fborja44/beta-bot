from discord import Guild, Interaction
from pprint import pprint
import utils.mdb as mdb

# guild.py
# Discord guilds used by the bot

GUILDS = 'guilds'

async def find_guild(guild_id: int):
    """
    Finds a guild in the database.
    """
    return await mdb.find_document({"guild_id": guild_id}, GUILDS)

async def find_add_guild(guild: Guild):
    """
    Finds a guild in the database or adds it if it does not exist.
    """
    guild_id = guild.id
    db_guild = await find_guild(guild_id)
    if db_guild:
        return db_guild
    else:
        return await add_guild(guild)

async def find_update_add_guild(guild: Guild):
    """
    Finds a guild in the database or adds it if it does not exist.
    """
    guild_id = guild.id
    db_guild = await find_guild(guild_id)
    if db_guild:
        return await update_guild(guild)
    else:
        return await add_guild(guild)

async def add_guild(guild: Guild):
    """
    Creates a guild document in the database
    """
    new_guild = {
        "guild_id": guild.id,
        "name": guild.name,
        "config": {
            "tournament_channel": None,     # TODO: Forum Channel (id) to post tournaments to (optional)
            "manager_roles": [],            # TODO: Roles (ids) to give tournament organizer/manager permissions to
            "allowed_channels": [],         # TODO: Channels that bot commands can be sent to
            "allowed_categories": [],       # TODO: Categories of channels that bot commands can be sent to
            "create_events": False,         # TODO: Option to create server events with brackets
            "disable_brackets": False,      # TODO: Disables user created bracket commands
            "disable_challenges": False,    # TODO: Disables challenges
            "disable_leaderboard": False,   # TODO: Disables leaderboard commands
        },
        "brackets": [],
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
    """
    Updates a guild document in the database.
    """
    db_guild = await mdb.update_single_document({'guild_id': guild.id}, {'$set': {'name': guild.name}}, GUILDS)
    if db_guild:
        print(f"Successfully updated guild ['name'='{guild.name}'] in database.")
        return db_guild
    print(f"Failed to update guild ['name'='{guild.name}'] in database.")
    return None

async def set_guild(guild_id: int, new_guild: dict):
    """
    Sets a guild document in the database to the specified document
    """
    db_guild = await mdb.update_single_document({'guild_id': guild_id}, {'$set': new_guild}, GUILDS)
    if db_guild:
        print(f"Successfully set guild ['id'='{guild_id}'] in database.")
        return db_guild
    print(f"Failed to set guild ['id'='{guild_id}'] in database.")
    return None

async def delete_guild(guild: Guild):
    """
    Deletes a guild document in the database.
    """
    delete_result = await mdb.delete_document({'guild_id': guild.id}, GUILDS)
    if delete_result:
        print(f"Successfully deleted guild ['name'='{guild.name}'] from database.")
        return delete_result
    print(f"Failed to delete guild ['name'='{guild.name}'] in database.")
    return None

async def push_to_guild(guild: Guild, target_array: str, document: dict):
    """
    Adds new document to a guild as a subdocument.
    """
    guild_id = guild.id
    document_id = document['id']
    db_guild = await find_add_guild(guild)
    if not db_guild:
        return None
    db_guild = await mdb.update_single_document({'guild_id': guild_id}, {'$push': {target_array: document}}, GUILDS)
    if db_guild:
        print(f"Successfully pushed subdocument ['id'={document_id}] to field '{target_array}' in guild ['name'='{guild.name}'].")
        return document
    print(f"Failed to push subdocument ['id'='{document_id}'] to field '{target_array}' in guild ['name'='{guild.name}'].")
    return None

async def pull_from_guild(guild: Guild, target_array: str, document: dict):
    """
    Removes a subdocument from a guild.
    """
    guild_id = guild.id
    document_id = document['id']
    db_guild = await find_add_guild(guild)
    if not db_guild:
        return None
    updated_guild = await mdb.update_single_document({'guild_id': guild_id}, {'$pull': {target_array: {'id': document_id}}}, GUILDS)
    if updated_guild:
        print(f"Successfully pulled subdocument ['id'={document_id}] to field '{target_array}' in guild ['name'='{guild.name}'].")
        return document
    print(f"Failed to pull subdocument ['id'={document_id}] to field '{target_array}' in guild ['name'='{guild.name}'].")
    return None

#######################
## COMMAND FUNCTIONS ##
#######################

async def update_tournament_channel(interaction: Interaction, channel_name: str):
    """"
    TODO
    Updates the tournament channel in a guild
    """
    
async def toggle_tournament_events(interaction: Interaction):
    """
    TODO
    Toggles create_events option.
    """

async def toggle_brackets(interaction: Interaction):
    """
    TODO
    Toggles the disable_brackets option.
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