import os
from dotenv import load_dotenv
from logger import printlog
from pprint import pprint
from pymongo import MongoClient, ReturnDocument

# mdb.py
# MongoDB function helpers

load_dotenv()

MONGO_ADDR = os.getenv('MONGO')

client = MongoClient(MONGO_ADDR)
db = client['beta-bot']

async def find_document(db, target, collection, message=None, send_text=None):
    """
    Finds a single document in the specifed collection.
    """
    try:
        document = db[collection].find_one(target)
    except:
        printlog(f"DB_ERROR: Failed to find document in [{collection}]:\ntarget=[{target}]")
        return
    if message and send_text:
        message.channel.send(send_text)
    return document

async def add_document(db, document, collection, message=None, send_text=None):
    """
    Adds a single document to the specifed collection.
    """
    try:
        inserted_id = db[collection].insert_one(document).inserted_id
    except:
        printlog(f"DB_ERROR: Failed to add document to [{collection}]:\n{document}")
        return
    if inserted_id:
        printlog(f"Successfully added document to [{collection}]:\n{document}")
        if message and send_text:
            message.channel.send(send_text)
        return inserted_id
    else:
        printlog(f"Could not add document to [{collection}]:\n{document}")

async def delete_document(db, target, collection, message=None, send_text=None):
    """
    Deletes a single document from the specifed collection.
    """
    try:
        result = db[collection].delete_one(target)
    except:
        printlog(f"DB_ERROR: Failed to remove document from [{collection}]:\ntarget=[{target}]")
        return
    if result.deleted_count > 0:
        printlog(f"Successfully removed document from [{collection}]:\ntarget=[{target}]")
        if message and send_text:
            message.channel.send(send_text)
        return result
    else:
        printlog(f"Could not find/delete document in [{collection}]:\ntarget=[{target}]")

async def update_single_field(db, target, update_obj, collection, message=None, send_text=None):
    """
    Updates a single field in a document in the specifed collection.
    """
    try:
        document = db[collection].find_one_and_update(target, update_obj, return_document=ReturnDocument.AFTER)
    except:
        printlog(f"DB_ERROR: Failed to find/update document in [{collection}]:\ntarget=[{target}]")
        return
    if document:
        printlog(f"Successfully updated document in [{collection}]:\n{document}")
        if message and send_text:
            message.channel.send(send_text)
        return document
    else:
        printlog(f"Could not find/update document in [{collection}]:\ntarget=[{target}]")

