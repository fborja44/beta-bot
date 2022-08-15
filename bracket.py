import mdb
import re
import requests
from discord import Embed
from pprint import pprint
from logger import printlog
from datetime import datetime, timedelta, date

# bracket.py
# User created brackets

# Challonge API: https://api.challonge.com/v1

BRACKETS = 'brackets'
BASE_URL = 'https://api.challonge.com/v2'

time_re_long = re.compile(r'([1-9]|0[1-9]|1[0-2]):[0-5][0-9] ([AaPp][Mm])$') # ex. 10:00 AM
time_re_short = re.compile(r'([1-9]|0[1-9]|1[0-2]) ([AaPp][Mm])$')           # ex. 10 PM

def create_bracket_embed(name, author, time, entrants=[]):
    embed = Embed(title='🥊  {0}'.format(name), description="Created by {0}".format(author), color=0x6A0DAD)
    time_str = time.strftime("%A, %B %d, %Y %I:%M %p") # time w/o ms
    embed.add_field(name='Starting At', value=time_str, inline=False)
    if len(entrants) > 0:
        entrants_content = ""
        for entrant_id in entrants:
            # To mention a user:
            # <@{user_id}>
            entrants_content += "> <@{0}>\n".format(entrant_id)
    else:
        entrants_content = '> *None*'
    embed.add_field(name='Entrants ({0})'.format(len(entrants)), value=entrants_content, inline=False)
    embed.set_footer(text='React with ✅ to enter!')
    return embed

async def get_bracket(self, db, bracket_name):
    return await mdb.find_document(db, {"name": bracket_name}, BRACKETS)

async def add_bracket(self, message, db, argv, argc):
    usage = 'Usage: `$bracket create <name> [time]`'
    if argc < 3:
        return await message.channel.send(usage)

    # Parse time; Default is 1 hour from current time
    match1 = time_re_long.search(message.content.strip()) # Check for long time
    match2 = time_re_short.search(message.content.strip()) # Check for short time
    if not match1 and not match2:
        time = datetime.now() + timedelta(hours=1)
        match = None
    else:
        current_time = datetime.now()
        if match1:
            match = match1.span()
            time = datetime.strptime('{0} {1}'.format(date.today(), match1.group()), '%Y-%m-%d %I:%M %p')
        elif match2:
            match = match2.span()
            time = datetime.strptime('{0} {1}'.format(date.today(), match2.group()), '%Y-%m-%d %I %p')
        # Check if current time is before time on current date; If so, go to next day
        if current_time > time:
            time += timedelta(days=1)

    # Get bracket name
    if match:
        argv = message.content[:match[0]].split()
    bracket_name = ' '.join(argv[2:]) 
    # Check if bracket already exists
    bracket = await get_bracket(self, db, bracket_name)
    if bracket:
        return await message.channel.send("Bracket with name '{0}' already exists.".format(bracket_name))

    # Send embed message
    embed = create_bracket_embed(bracket_name, message.author.name, time)
    bracket_message = await message.channel.send(embed=embed)
    # Add checkmark reaction to message
    await bracket_message.add_reaction('✅')
    # Add bracket to DB
    bracket = {'name': bracket_name, 'bracket_id': bracket_message.id, 
               'author': {'username': message.author.name, 'id': message.author.id},
               'entrants': [], 'starttime': time, 'endtime': None, 
               'open': True}
    if await mdb.add_document(db, bracket, BRACKETS):
        print("User '{0}' [id={1}] created new bracket '{2}'.".format(message.author.name, message.author.id, bracket_name))

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
        # Update message
        await edit_bracket_message(self, bracket, message_id, channel_id)
    else:
        print("Failed to add entrant [id='{0}'] to bracket [id='{1}'].".format(member_id, message_id))

async def remove_entrant(self, db, message_id, member_id, channel_id):
    # Remove user from entrants list
    bracket = await mdb.update_single_field(db, {'bracket_id': message_id}, {'$pull': {'entrants': member_id}}, BRACKETS)
    if bracket:
        print("Removed entrant [id='{0}'] from bracket [id='{1}'].".format(member_id, message_id))
        # Update message
        await edit_bracket_message(self, bracket, message_id, channel_id)
    else:
        print("Failed to remove entrant [id='{0}'] from bracket [id='{1}'].".format(member_id, message_id))

async def edit_bracket_message(self, bracket, message_id, channel_id):
    channel = self.get_channel(channel_id)
    message = await channel.fetch_message(message_id)
    
    embed = create_bracket_embed(bracket['name'], bracket['author']['username'], bracket['starttime'], bracket['entrants'])
    await message.edit(embed=embed)

