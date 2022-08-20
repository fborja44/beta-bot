from discord import Client, Message, RawReactionActionEvent
from gridfs import Database
from logger import printlog
from pprint import pprint
import mdb

# favorite.py
# Hall of Fame messages

FAVORITES = 'favorites'
HALL_OF_FAME = 'hall-of-fame'

async def add_favorite(self: Client, msg: Message, db: Database):
    """
    Adds a message to the favorites collection.
    """
    return await mdb.add_document(db, msg, FAVORITES)

async def delete_favorite(self: Client, msg: Message, db: Database):
    """
    Deletes a message from the favorites collection.
    """
    message_id = msg['message_id']
    return await mdb.delete_document(db, {'message_id': message_id}, FAVORITES)

async def update_favorite(self: Client, payload: RawReactionActionEvent, db: Database):
    """
    Updates a message in the favorites collection.
    """
    channel = self.get_channel(payload.channel_id)
    member = payload.member
    user_id  = payload.user_id
    event_type = payload.event_type
    message = await channel.fetch_message(payload.message_id)

    # TODO: Add list of members who have starred to db

    # Check if user is interacting with own message
    if user_id == message.author.id:
        if event_type == 'REACTION_ADD':
            printlog(f"User '{message.author.name}' [id={message.author.id}] self-starred message [id={payload.message_id}].")
        elif event_type == 'REACTION_REMOVE':
            printlog(f"User '{message.author.name}' [id={message.author.id}] removed self-star on message [id={payload.message_id}].")
        return

    # New message document
    msg = {
        "message_id": message.id,
        "channel": { "id": message.channel.id, "name": message.channel.name, 
                    "nsfw": message.channel.nsfw, "category": message.channel.category_id },
        "author": {"username": message.author.name, "id": message.author.id}
    }
    
    # Get star count
    reaction_list = list(filter(lambda reaction: (reaction.emoji == '⭐'), message.reactions))
    # Check reaction counts
    if reaction_list:
        reaction = reaction_list[0]
        msg['star_count'] = reaction.count
        if not await mdb.find_document(db, {'message_id': message.id}, FAVORITES):
            message = await add_favorite(self, msg, db)
        else:
            message = await mdb.update_single_document(db, {'message_id': message.id}, {'$set': {'star_count': msg['star_count']}}, FAVORITES)
    else:
        # No star reactions; Remove from favorites if exists
        if await mdb.find_document(db, {'message_id': message.id}, FAVORITES):
            await delete_favorite(self, msg, db)

    # Check type of event
    if event_type == 'REACTION_ADD' and message:
        print(f"User '{member}' [id={user_id}] starred message.")
    elif event_type == 'REACTION_REMOVE' and message:
        print(f"User [id={user_id}] unstarred message.") # member not available on remove
    else:
        printlog(f"Error occured when user '{member}' [id={user_id}] updated star reaction.")

async def add_hall_entry(self: Client, msg: Message, db: Database):
    """
    Adds a message to the hall of fame collection.
    """
    message_id = msg['message_id']
    # Add to hall
    entry = { "message_id": message_id, "star-count": msg['star_count'] }
    return await mdb.add_document(db, entry, HALL_OF_FAME)

async def remove_hall_entry(self: Client, msg: Message, db: Database):
    """
    Deletes a message from the hall of fame collection.
    """
    message_id = msg['message_id']
    return await mdb.delete_document(db, {'message_id': message_id}, HALL_OF_FAME)

async def update_hall_entry(self: Client, msg: Message, db: Database):
    """
    Updates a message in the hall of fame collection.
    """
    message_id = msg['message_id']
    # Check if in hall already
    try:
        entry = db['hall-of-fame'].find_one({"message_id": message_id})
    except:
        print(f"Failed to get message with id '{str(message_id)}' from favorites.")
        return
    if not entry:
        # Add to hall
        await add_hall_entry(self, msg, db)
    else:
        # Update hall entry
        pass