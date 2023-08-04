import os
from pprint import pprint

from discord import Message
from dotenv import load_dotenv
from pymongo import DESCENDING, MongoClient, ReturnDocument

from utils.log import printlog

# mdb.py
# MongoDB function helpers

load_dotenv()

MONGO_ADDR = os.getenv("MONGO")

db_client = MongoClient(MONGO_ADDR)
db = db_client["beta-bot"]


async def find_all(collection: str, message: Message = None, response_text: str = None):
    """Finds all documents from a single collection.

    Args:
        collection (str): The target database collection.
        message (Message, optional): A discord message to respond to. Defaults to None.
        response_text (str, optional): The response message text. Defaults to None.

    Returns:
        A list of the resulting documents if successful. Otherwise, returns None.
    """
    try:
        document_list = db[collection].find({})
    except Exception as e:
        printlog(f"DB_ERROR: Failed to fetch collection documents [{collection}]:", e)
        return None
    if message and response_text:
        await message.channel.send(response_text)
    return document_list


async def find_document(
    target: dict, collection: str, message: Message = None, response_text: str = None
):
    """Finds a single document in the specifed collection.

    Args:
        target (dict): The target document query.
        collection (str): The target database collection.
        message (Message, optional): A discord message to respond to. Defaults to None.
        response_text (str, optional): The response message text. Defaults to None.

    Returns:
        The result document if successful. Otherwise, returns None.
    """
    try:
        document = db[collection].find_one(target)
    except Exception as e:
        printlog(
            f"DB_ERROR: Failed to find document in [{collection}]:\ntarget=[{target}]",
            e,
        )
        return None
    if message and response_text:
        await message.channel.send(response_text)
    return document


async def find_subdocument(
    target_array: str,
    target_field: str,
    target_value: dict,
    collection: str,
    message: Message = None,
    response_text: str = None,
):
    """Finds a single subdocument in the specifed collection.

    Args:
        target_array (str): The target subdocument collection name.
        target_field (str): The target subdocument field name.
        target_value (dict): The target subdocument value.
        collection (str): The target collection.
        message (Message, optional): A discord message to respond to. Defaults to None.
        response_text (str, optional): The response message text. Defaults to None.

    Returns:
        The result document if successful. Otherwise, returns None.
    """
    try:
        document = db[collection].aggregate(
            {"$match": {f"{target_array}.{target_field}": target_value}},
            {"$unwind": target_array},
            {"$match": {f"{target_array}.{target_field}": target_value}},
        )
    except Exception as e:
        printlog(
            f"DB_ERROR: Failed to find document in [{collection}]:\ntarget=[{target_array}.{target_field}: {target_value}]",
            e,
        )
        return None
    if message and response_text:
        await message.channel.send(response_text)
    return document


async def find_most_recent_document(
    target: dict, collection: str, message: Message = None, response_text: str = None
):
    """Finds the most recently added document in the database.

    Args:
        target (dict): The target document query
        collection (str): The target database collection.
        message (Message, optional): A discord message to respond to. Defaults to None.
        response_text (str, optional): The response message text. Defaults to None.

    Returns:
        The result document if successful. Otherwise, returns None.
    """
    try:
        document = db[collection].find_one(target, sort=[("_id", DESCENDING)])
    except Exception as e:
        printlog(
            f"DB_ERROR: Failed to retrieve most recent document in [{collection}]:\ntarget=[{target}]",
            e,
        )
        return None
    if message and response_text:
        await message.channel.send(response_text)
    return document


async def add_document(
    document: dict, collection: str, message: Message = None, response_text: str = None
):
    """Adds a single document to the specifed collection.

    Args:
        document (dict): The document to add to the database.
        collection (str): The target database collection.
        message (Message, optional): A discord message to respond to. Defaults to None.
        response_text (str, optional): The response message text. Defaults to None.

    Returns:
        The id of the inserted document if successful. Otherwise, returns None.
    """
    try:
        inserted_id = db[collection].insert_one(document).inserted_id
    except Exception as e:
        printlog(f"DB_ERROR: Failed to add document to [{collection}]:", e)
        return None
    if inserted_id:
        printlog(f"Successfully added document to [{collection}]:")
        if message and response_text:
            await message.channel.send(response_text)
        return inserted_id
    else:
        printlog(f"Could not add document to [{collection}]:")
    return None


async def delete_document(
    target: dict, collection: str, message: Message = None, response_text: str = None
):
    """Deletes a single document from the specifed collection.

    Args:
        target (dict): The target document to remove from the database.
        collection (str): The target database collection.
        message (Message, optional): A discord message to respond to. Defaults to None.
        response_text (str, optional): The response message text. Defaults to None.

    Returns:
        The result object if successful. Otherwise, returns None.
    """
    try:
        result = db[collection].delete_one(target)
    except Exception as e:
        printlog(
            f"DB_ERROR: Failed to remove document from [{collection}]:\ntarget=[{target}]",
            e,
        )
        return None
    if result.deleted_count > 0:
        printlog(
            f"Successfully removed document from [{collection}]:\ntarget=[{target}]"
        )
        if message and response_text:
            await message.channel.send(response_text)
        return result
    else:
        printlog(
            f"Could not find/delete document in [{collection}]:\ntarget=[{target}]"
        )
    return None


async def update_single_document(
    target: dict, update_obj: dict, collection: str, message: Message=None, response_text: str=None
):
    """Updates a single field in a document in the specifed collection.

    Args:
        target (dict): The target database document to update
        update_obj (dict): The updated document.
        collection (str): The target database collection.
        message (message, optional): A discord message to respond to. Defaults to None.
        response_text (str, optional): The response message text. Defaults to None.

    Returns:
        The updated document if successful. Otherwise, returns None.
    """
    try:
        document = db[collection].find_one_and_update(
            target, update_obj, return_document=ReturnDocument.AFTER
        )
    except Exception as e:
        printlog(
            f"DB_ERROR: Failed to find/update document in [{collection}]:\ntarget=[{target}]",
            e,
        )
        return None
    if document:
        printlog(f"Successfully updated document in [{collection}]:")
        if message and response_text:
            await message.channel.send(response_text)
        return document
    else:
        printlog(
            f"Could not find/update document in [{collection}]:\ntarget=[{target}]"
        )
    return None
