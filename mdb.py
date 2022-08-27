from dotenv import load_dotenv
from gridfs import Database
from logger import printlog
from pprint import pprint
from pymongo import ReturnDocument, DESCENDING
import os

# mdb.py
# MongoDB function helpers

load_dotenv()

MONGO_ADDR = os.getenv('MONGO')

async def find_document(db: Database, target: dict, collection: str, message=None, send_text=None):
    """
    Finds a single document in the specifed collection.
    """
    try:
        document = db[collection].find_one(target)
    except Exception as e:
        printlog(f"DB_ERROR: Failed to find document in [{collection}]:\ntarget=[{target}]", e)
        return None
    if message and send_text:
        await message.channel.send(send_text)
    return document

async def find_subdocument(db: Database, target_array: str, target_field: str, target_value: dict, collection: str, message=None, send_text=None):
    """
    Finds a single document in the specifed collection.
    """
    try:
        document = db[collection].aggregate(
            {'$match': {f'{target_array}.{target_field}': target_value}},
            {'$unwind': target_array},
            {'$match': {f'{target_array}.{target_field}': target_value}},
        )
    except Exception as e:
        printlog(f"DB_ERROR: Failed to find document in [{collection}]:\ntarget=[{target_array}.{target_field}: {target_value}]", e)
        return None
    if message and send_text:
        await message.channel.send(send_text)
    return document

async def find_most_recent_document(db: Database, target: dict, collection: str, message=None, send_text=None):
    """
    Finds the most recently added document in the database.
    """
    try:
        document = db[collection].find_one(target, sort=[('_id', DESCENDING )])
    except Exception as e:
        printlog(f"DB_ERROR: Failed to retrieve most recent document in [{collection}]:\ntarget=[{target}]", e)
        return None
    if message and send_text:
        await message.channel.send(send_text)
    return document

async def add_document(db: Database, document: dict, collection: str, message=None, send_text=None):
    """
    Adds a single document to the specifed collection.
    """
    try:
        inserted_id = db[collection].insert_one(document).inserted_id
    except Exception as e:
        printlog(f"DB_ERROR: Failed to add document to [{collection}]:", e)
        return None
    if inserted_id:
        printlog(f"Successfully added document to [{collection}]:")
        if message and send_text:
            await message.channel.send(send_text)
        return inserted_id
    else:
        printlog(f"Could not add document to [{collection}]:")
    return None

async def delete_document(db: Database, target: dict, collection: str, message=None, send_text=None):
    """
    Deletes a single document from the specifed collection.
    """
    try:
        result = db[collection].delete_one(target)
    except Exception as e:
        printlog(f"DB_ERROR: Failed to remove document from [{collection}]:\ntarget=[{target}]", e)
        return None
    if result.deleted_count > 0:
        printlog(f"Successfully removed document from [{collection}]:\ntarget=[{target}]")
        if message and send_text:
            await message.channel.send(send_text)
        return result
    else:
        printlog(f"Could not find/delete document in [{collection}]:\ntarget=[{target}]")
    return None

async def update_single_document(db: Database, target: dict, update_obj: dict, collection: str, message=None, send_text=None):
    """
    Updates a single field in a document in the specifed collection.
    """
    try:
        document = db[collection].find_one_and_update(target, update_obj, return_document=ReturnDocument.AFTER)
    except Exception as e:
        printlog(f"DB_ERROR: Failed to find/update document in [{collection}]:\ntarget=[{target}]", e)
        return None
    if document:
        printlog(f"Successfully updated document in [{collection}]:")
        if message and send_text:
            await message.channel.send(send_text)
        return document
    else:
        printlog(f"Could not find/update document in [{collection}]:\ntarget=[{target}]")
    return None