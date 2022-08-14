import os
from pymongo import MongoClient, ReturnDocument
from pprint import pprint
from dotenv import load_dotenv
from logger import printlog

# mdb.py
# MongoDB function helpers

load_dotenv()

MONGO_ADDR = os.getenv('MONGO')

client = MongoClient(MONGO_ADDR)
db = client['beta-bot']

async def find_document(db, target, collection, message=None, send_text=None):
    try:
        document = db[collection].find_one(target)
    except:
        printlog("DB_ERROR: Failed to find document in [{0}]:\ntarget=[{1}]".format(collection, target))
        return
    if message and send_text:
        message.channel.send(send_text)
    return document

async def add_document(db, document, collection, message=None, send_text=None):
    try:
        inserted_id = db[collection].insert_one(document).inserted_id
    except:
        printlog("DB_ERROR: Failed to add document to [{0}]:\n{1}".format(collection, document))
        return
    if inserted_id:
        printlog("Successfully added document to [{0}]:\n{1}".format(collection, document))
        if message and send_text:
            message.channel.send(send_text)
        return inserted_id
    else:
        printlog("Could not add document to [{0}]:\n{1}".format(collection, document))

async def delete_document(db, target, collection, message=None, send_text=None):
    try:
        result = db[collection].delete_one(target)
    except:
        printlog("DB_ERROR: Failed to remove document from [{0}]:\ntarget=[{1}]".format(collection, target))
        return
    if result.deleted_count > 0:
        printlog("Successfully removed document from [{0}]:\ntarget=[{1}]".format(collection, target))
        if message and send_text:
            message.channel.send(send_text)
        return result
    else:
        printlog("Could not find/delete document in [{0}]:\ntarget=[{1}]".format(collection, target))

async def update_single_field(db, target, update_obj, collection, message=None, send_text=None):
    try:
        document = db[collection].find_one_and_update(target, update_obj, return_document=ReturnDocument.AFTER)
    except:
        printlog("DB_ERROR: Failed to find/update document in [{0}]:\ntarget=[{1}]".format(collection, target))
        return
    if document:
        printlog("Successfully updated document in [{0}]:\n{1}".format(collection, document))
        if message and send_text:
            message.channel.send(send_text)
        return document
    else:
        printlog("Could not find/update document in [{0}]:\ntarget=[{1}]".format(collection, target))

