import mdb
from discord import Embed
from pprint import pprint
from logger import printlog
from datetime import datetime

# bracket.py
# User created brackets

# Challonge API: https://api.challonge.com/v1

BRACKETS = 'brackets'

async def get_bracket(self, db, bracket_name):
    return await mdb.find_document(db, {"name": bracket_name}, BRACKETS)

async def add_bracket(self, message, db, argv, argc):
    usage = 'Usage: `$bracket create <name> [time]`'
    if argc < 3:
        return await message.channel.send(usage)

    bracket_name = ' '.join(argv[2:]) # get bracket name
    # Check if bracket already exists
    bracket = await get_bracket(self, db, bracket_name)
    if bracket:
        return await message.channel.send("Bracket with name '{0}' already exists.".format(bracket_name))

    # Send embed message
    embed = Embed(title='🥊  {0}'.format(bracket_name), description="Created by {0}".format(message.author.name), color=0x6A0DAD)
    embed.add_field(name='Starting At', value="Sunday, August 14, 2022 11:59 PM", inline=False)
    embed.add_field(name='Entrants (0)', value="> *None*", inline=False)
    embed.set_footer(text='React with ✅ to enter!')
    message = await message.channel.send(embed=embed)
    
    # Add ✅ reaction to message
    await message.add_reaction('✅')

    # Add bracket to DB
    bracket = {'name': bracket_name, 'bracket_id': message.id, 
               'author': {'username': message.author.name, 'id': message.author.id},
               'entrants': [], 'starttime': datetime.utcnow(), 'endtime': None, 
               'open': True}
    await mdb.add_document(db, bracket, BRACKETS)
    print("User '{0}' [id={1}] created new bracket '{2}'.".format(message.author.name, message.author.id, bracket_name))

    # Wait for reactions on bracket

async def delete_bracket(self, message, db, argv, argc):
    usage = 'Usage: `$bracket delete <name>`'
    if argc < 3:
        return await message.channel.send(usage)

    bracket_name = ' '.join(argv[2:]) # get bracket name
    # Check if bracket already exists
    bracket = await get_bracket(self, db, bracket_name)
    if not bracket:
        return await message.channel.send("Bracket with name '{0}' does not exist.".format(bracket_name))
    result = await mdb.delete_document(db, {'name': bracket_name}, BRACKETS)
    try:
        bracket_message = await message.channel.fetch_message(bracket['bracket_id'])
        await bracket_message.delete()
    except:
        print("Failed to delete message for bracket '{0}' [id='{1}']".format(bracket_name, bracket['bracket_id']))
    if result:
        print("User '{0}' [id={1}] created new bracket '{2}'.".format(message.author.name, message.author.id, bracket_name))
        await message.channel.send("Successfully deleted bracket '{0}'.".format(bracket_name))
    else:
        await message.channel.send("Failed to delete bracket '{0}'; Bracket does not exist.".format(bracket_name))

async def update_bracket(self, message, db, argv, argc):
    usage = 'Usage: `$bracket update <name>`'
    if argc < 3:
        return await message.channel.send(usage)

async def update_bracket_entrants(self, payload, db):
    # Check if message reacted to is in brackets and is open
    bracket = await mdb.find_document(db, {'bracket_id': payload.message_id}, BRACKETS)
    if not bracket or not bracket['open']:
        return # Do not respond

    if payload.event_type=='REACTION_ADD':
        await add_entrant(self, db, payload.message_id, payload.user_id, payload.channel_id)
    elif payload.event_type=='REACTION_REMOVE':
        await remove_entrant(self, db, payload.message_id, payload.user_id, payload.channel_id)
    
async def add_entrant(self, db, message_id, member_id, channel_id):
    # Add user to entrants list
    bracket = await mdb.update_single_field(db, {'bracket_id': message_id}, {'$push': {'entrants': member_id}}, BRACKETS)
    if bracket:
        print("Added entrant [id='{0}'] to bracket [id='{1}'].".format(member_id, message_id))
        # Update Message
        channel = self.get_channel(channel_id)
        message = await channel.fetch_message(message_id)
        entrants_content = ""
        for entrant_id in bracket['entrants']:
            # To mention a user:
            # <@{user_id}>
            entrants_content += "> <@{0}>\n".format(entrant_id)

        embed = Embed(title='🥊  {0}'.format(bracket['name']), description="Created by {0}".format(message.author.name), color=0x6A0DAD)
        embed.add_field(name='Starting At', value="Sunday, August 14, 2022 11:59 PM", inline=False)
        embed.add_field(name='Entrants ({0})'.format(len(bracket['entrants'])), value=entrants_content, inline=False)
        embed.set_footer(text='React with ✅ to enter!')
        await message.edit(embed=embed)
    else:
        print("Failed to add entrant [id='{0}'] to bracket [id='{1}'].".format(member_id, message_id))

async def remove_entrant(self, db, message_id, member_id):
    pass