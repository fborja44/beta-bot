import discord
import pymongo
import mdb
from pprint import pprint

# favorite.py
# Hall of Fame messages

FAVORITES = 'favorites'
HALL_OF_FAME = 'hall-of-fame'

async def add_favorite(self, msg, db):
    await mdb.add_document(db, msg, FAVORITES)

async def delete_favorite(self, msg, db):
    message_id = msg['message_id']
    await mdb.delete_document(db, {'message_id': message_id}, FAVORITES)

async def update_favorite(self, payload, db):
    channel = self.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    # Get star count
    reaction_list = list(filter(lambda reaction: (reaction.emoji == '⭐'), message.reactions))
    if not reaction_list:
        star_count = 0
    else:
        reaction = reaction_list[0]
        star_count = reaction.count
        # Don't count self stars
        async for user in reaction.users(): # TODO: Clean this up
            if user.id == message.author.id:
                print("User {name='{0}', id='{1}'} self-starred post.".format(user.name, user.id))
                star_count -= 1

    #author = {"username": message.author.name, "id": message.author.id}
    msg = {"message_id": message.id,
           "channel": { "id": message.channel.id, "name": message.channel.name, "nsfw": message.channel.nsfw, "category": message.channel.category_id },
           "author": {"username": message.author.name, "id": message.author.id},
           "star_count": star_count}

    # No stars:
        # If in database, remove
        # Otherwise, do nothing
    # Has stars:
        # If in database, update
        # If not in database, add

    # No stars; Remove
    if star_count == 0:
        if await mdb.find_document(db, {'message_id': message.id}, FAVORITES):
            await delete_favorite(self,  msg, db)
    # Has stars; Update
    else:
        await mdb.update_single_field(db, {'message_id': message.id}, {'$set': {'star_count': star_count}}, FAVORITES)
        # If not in favorites, insert new doc
        if not await mdb.find_document(db, {'message_id': message.id}, FAVORITES):
            await add_favorite(self, msg, db)

async def add_hall_entry(self, msg, db):
    message_id = msg['message_id']
    # Add to hall
    entry = { "message_id": message_id, "star-count": msg['star_count'] }
    await mdb.add_document(db, entry, HALL_OF_FAME)

async def remove_hall_entry(self, msg, db):
    message_id = msg['message_id']
    await mdb.delete_document(db, {'message_id': message_id}, HALL_OF_FAME)

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