from discord import Client, Embed, Guild, Message, RawReactionActionEvent, Reaction, TextChannel, User
from gridfs import Database
from pprint import pprint
import mdb
import uuid

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
        "brackets": [],
        "challenges": [],
        # "commands": [],
        # "favorites": [],
        "leaderboard": [],
        "users": []
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