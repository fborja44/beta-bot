import discord
import pymongo
import mdb
from pprint import pprint

# favorite.py
# Hall of Fame messages

FAVORITES = 'favorites'
HALL_OF_FAME = 'hall-of-fame'

async def add_favorite(self, msg, db):
    return await mdb.add_document(db, msg, FAVORITES)

async def delete_favorite(self, msg, db):
    message_id = msg['message_id']
    return await mdb.delete_document(db, {'message_id': message_id}, FAVORITES)

async def update_favorite(self, payload, db):
    channel = self.get_channel(payload.channel_id)
    member = payload.member
    user_id  = payload.user_id
    event_type = payload.event_type
    message = await channel.fetch_message(payload.message_id)

    # Check if user is interacting with own message
    if user_id == message.author.id:
        if event_type == 'REACTION_ADD':
            mdb.printlog("User '{0}' [id={1}] self-starred message [id={2}].".format(message.author.name, message.author.id, payload.message_id))
        elif event_type == 'REACTION_REMOVE':
            mdb.printlog("User '{0}' [id={1}] removed self-star on message [id={2}].".format(message.author.name, message.author.id, payload.message_id))
        return

    msg = {"message_id": message.id,
           "channel": { "id": message.channel.id, "name": message.channel.name, "nsfw": message.channel.nsfw, "category": message.channel.category_id },
           "author": {"username": message.author.name, "id": message.author.id}}
           
    # Get star count
    reaction_list = list(filter(lambda reaction: (reaction.emoji == '⭐'), message.reactions))
    # Check reaction counts
    if reaction_list:
        reaction = reaction_list[0]
        msg['star_count'] = reaction.count
        if not await mdb.find_document(db, {'message_id': message.id}, FAVORITES):
            message = await add_favorite(self, msg, db)
        else:
            message = await mdb.update_single_field(db, {'message_id': message.id}, {'$set': {'star_count': msg['star_count']}}, FAVORITES)
    else:
        # No star reactions; Remove from favorites if exists
        if await mdb.find_document(db, {'message_id': message.id}, FAVORITES):
            await delete_favorite(self, msg, db)

    # Check type of event
    if event_type == 'REACTION_ADD' and message:
        print("User '{0}' [id={1}] starred message [id={2}].".format(message.author.name, message.author.id, payload.message_id))
    elif event_type == 'REACTION_REMOVE' and message:
        print("User '{0}' [id={1}] unstarred message [id={2}].".format(message.author.name, message.author.id, payload.message_id))
    elif not message:
        mdb.printlog("Error occured when user '{0}' [id={1}] updated star reaction.".format(member, user_id))

async def add_hall_entry(self, msg, db):
    message_id = msg['message_id']
    # Add to hall
    entry = { "message_id": message_id, "star-count": msg['star_count'] }
    return await mdb.add_document(db, entry, HALL_OF_FAME)

async def remove_hall_entry(self, msg, db):
    message_id = msg['message_id']
    return await mdb.delete_document(db, {'message_id': message_id}, HALL_OF_FAME)

async def update_hall_entry(self, msg, db):
    message_id = msg['message_id']
    # Check if in hall already
    try:
        entry = db['hall-of-fame'].find_one({"message_id": message_id})
    except:
        print("Failed to get message with id '{0}' from favorites.".format(str(message_id)))
        return
    if not entry:
        # Add to hall
        await add_hall_entry(self, msg, db)
    else:
        # Update hall entry
        pass