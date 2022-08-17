import challonge
import match as _match
import mdb
import re
from datetime import datetime, timedelta, date
from discord import Embed
from logger import printlog
from pprint import pprint

# bracket.py
# User created brackets

# Challonge API: https://api.challonge.com/v1

BRACKETS = 'brackets'
BASE_URL = 'https://api.challonge.com/v2'

time_re_long = re.compile(r'([1-9]|0[1-9]|1[0-2]):[0-5][0-9] ([AaPp][Mm])$') # ex. 10:00 AM
time_re_short = re.compile(r'([1-9]|0[1-9]|1[0-2]) ([AaPp][Mm])$')           # ex. 10 PM

def create_bracket_embed(name, author, time, url, entrants=[], status="Open for Registration  🚨"):
    """
    Creates embed object to include in bracket message.
    """
    embed = Embed(title=f'🥊  {name}', description=f"Status:  {status}", color=0x6A0DAD)
    time_str = time.strftime("%A, %B %d, %Y %I:%M %p") # time w/o ms
    embed.add_field(name='Starting At', value=time_str, inline=False)
    if len(entrants) > 0:
        entrants_content = ""
        for entrant in entrants:
            # To mention a user:
            # <@{user_id}>
            entrants_content += f"> <@{entrant['discord_id']}>\n"
    else:
        entrants_content = '> *None*'
    embed.add_field(name=f'Entrants ({len(entrants)})', value=entrants_content, inline=False)
    embed.add_field(name=f'Bracket Link', value=url, inline=False)
    embed.set_footer(text=f'React with ✅ to enter! | Created by {author}')
    return embed

async def get_bracket(self, db, bracket_name):
    """
    Retrieves and returns a bracket document from the database (if it exists).
    """
    return await mdb.find_document(db, {"name": bracket_name}, BRACKETS)

async def add_bracket(self, message, db, argv, argc):
    """
    Adds a new bracket document to the database.
    """
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
            time = datetime.strptime(f'{date.today()} {match1.group()}', '%Y-%m-%d %I:%M %p')
        elif match2:
            match = match2.span()
            time = datetime.strptime(f'{date.today()} {match2.group()}', '%Y-%m-%d %I %p')
        # Check if current time is before time on current date; If so, go to next day
        if current_time > time:
            time += timedelta(days=1)

    # Get bracket name
    if match:
        argv = message.content[:match[0]].split()
    bracket_name = ' '.join(argv[2:]) 
    # Max character length == 60
    if len(bracket_name.strip()) > 60:
        return await message.channel.send(f"Bracket name can be no longer than 60 characters.")
    # Check if bracket already exists
    bracket = await get_bracket(self, db, bracket_name)
    if bracket:
        return await message.channel.send(f"Bracket with name '{bracket_name}' already exists.")

    # Create challonge bracket
    response = challonge.tournaments.create(name="Test", url=None, tournament_type='double elimination', start_at=time, show_rounds=True, private=True, quick_advance=True, open_signup=False)
    # Send embed message
    embed = create_bracket_embed(bracket_name, message.author.name, time, response['full_challonge_url'])
    bracket_message = await message.channel.send(embed=embed)
    # Add checkmark reaction to message
    await bracket_message.add_reaction('✅')
    # Add bracket to DB
    bracket = {
        'name': bracket_name, 
        'bracket_id': bracket_message.id, 
        'jump_url': message.jump_url,
        'author': {'username': message.author.name, 'id': message.author.id},
        'challonge': {'id': response['id'], 'url': response['full_challonge_url']},
        'entrants': [], 
        'matches': [],
        'starttime': time, 
        'endtime': None, 
        'completed': False,
        'open': True
    }
    if await mdb.add_document(db, bracket, BRACKETS):
        print(f"User '{message.author.name}' [id={message.author.id}] created new bracket '{bracket_name}'.")

    # TODO: Cleanup if anything fails (delete db entry, delete message, delete challonge bracket)

async def delete_bracket(self, message, db, argv, argc):
    """
    Deletes the specified bracket from the database (if it exists).
    """
    usage = 'Usage: `$bracket delete <name>`'
    if argc < 3:
        return await message.channel.send(usage)

    bracket_name = ' '.join(argv[2:]) # get bracket name
    # Check if bracket already exists
    bracket = await get_bracket(self, db, bracket_name)
    if not bracket:
        return await message.channel.send(f"Bracket with name '{bracket_name}' does not exist.")
    result = await mdb.delete_document(db, {'name': bracket_name}, BRACKETS)
    # TODO: Only allow author to delete bracket
    try:
        bracket_message = await message.channel.fetch_message(bracket['bracket_id'])
        await bracket_message.delete() # delete message from channel
    except:
        print(f"Failed to delete message for bracket '{bracket_name}' [id='{bracket['bracket_id']}']")
    if result:
        challonge.tournaments.destroy(bracket['challonge']['id']) # delete bracket from challonge
        print(f"User '{message.author.name}' [id={message.author.id}] deleted bracket '{bracket_name}'.")
        await message.channel.send(f"Successfully deleted bracket '{bracket_name}'.")
    else:
        await message.channel.send(f"Failed to delete bracket '{bracket_name}'.")
    
    # TODO: Delete every match message and document associated with the bracket

async def update_bracket(self, message, db, argv, argc):
    """
    Updates the specified bracket in the database (if it exists).
    """
    usage = 'Usage: `$bracket update <name>`'
    if argc < 3:
        return await message.channel.send(usage)

async def update_bracket_entrants(self, payload, db):
    """
    Adds or removes an entrant from a bracket based on whether the reaction was added or removed.
    """
    # Check if message reacted to is in brackets and is open
    bracket = await mdb.find_document(db, {'bracket_id': payload.message_id}, BRACKETS)
    if not bracket or not bracket['open']:
        return # Do not respond
    if payload.event_type=='REACTION_ADD':
        await add_entrant(self, db, bracket, payload.message_id, payload.user_id, payload.channel_id, payload.member)
    elif payload.event_type=='REACTION_REMOVE':
        await remove_entrant(self, db, bracket, payload.message_id, payload.user_id, payload.channel_id)
    
async def add_entrant(self, db, bracket, message_id, member_id, channel_id, member):
    """
    Adds an entrant to a bracket.
    """
    # Add user to challonge bracket
    response = challonge.participants.create(bracket['challonge']['id'], member.name)
    # Add user to entrants list
    entrant = {'name': member.name, 'discord_id': member_id, 'challonge_id': response['id']}
    updated_bracket = await mdb.update_single_field(db, {'bracket_id': message_id}, {'$push': {'entrants': entrant}}, BRACKETS)
    if updated_bracket:
        print(f"Added entrant '{member.name}' [id='{member_id}'] to bracket [id='{message_id}'].")
        # Update message
        await edit_bracket_message(self, updated_bracket, message_id, channel_id)
    else:
        print(f"Failed to add entrant '{member.name}' [id='{member_id}'] to bracket [id='{message_id}'].")

async def remove_entrant(self, db, bracket, message_id, member_id, channel_id):
    """
    Destroys an entrant from a tournament or DQs them if the tournament has already started.
    """
    # Remove user from challonge bracket
    entrant = list(filter(lambda entrant: (entrant['discord_id'] == member_id), bracket['entrants']))[0]
    response = challonge.participants.destroy(bracket['challonge']['id'], entrant['challonge_id'])
    # Remove user from entrants list
    updated_bracket = await mdb.update_single_field(db, {'bracket_id': message_id}, {'$pull': {'entrants': {'discord_id': member_id }}}, BRACKETS)
    if updated_bracket:
        print(f"Removed entrant [id='{member_id}'] from bracket [id='{message_id}'].")
        # Update message
        await edit_bracket_message(self, updated_bracket, message_id, channel_id)
    else:
        print(f"Failed to remove entrant [id='{member_id}'] from bracket [id='{message_id}'].")

async def edit_bracket_message(self, bracket, message_id, channel_id, status='🚨  Open for Registration'):
    """
    Edits bracket embed message in a channel.
    """
    channel = self.get_channel(channel_id)
    message = await channel.fetch_message(message_id)
    
    embed = create_bracket_embed(bracket['name'], bracket['author']['username'], bracket['starttime'], bracket['challonge']['url'], bracket['entrants'], status)
    await message.edit(embed=embed)

async def start_bracket(self, message, db, argv, argc):
    """
    Starts a bracket created by the user.
    """
    usage = 'Usage: `$bracket start <name>`'
    if argc < 3:
        return await message.channel.send(usage)
    
    # Get bracket from database
    bracket_name = ' '.join(argv[2:]) # get bracket name
    # Check if bracket exists
    bracket = await get_bracket(self, db, bracket_name)
    if not bracket:
        return await message.channel.send(f"Bracket with name '{bracket_name}' does not exist.")
    # Make sure there are sufficient number of entrants
    if len(bracket['entrants']) < 2:
        return await message.channel.send(f"Bracket must have at least 2 entrants before starting.")
    # Start bracket on challonge
    create_response = challonge.tournaments.start(bracket['challonge']['id'], include_participants=True, include_matches=True)
    # Set bracket to closed in database
    updated_bracket = await mdb.update_single_field(db, {'bracket_id': bracket['bracket_id']}, {'$set': {'open': False}}, BRACKETS)
    # Update embed message
    await edit_bracket_message(self, updated_bracket, bracket['bracket_id'], message.channel.id, status='Started 🟩')
    print(f"Succesfully started bracket '{bracket_name}' [id={bracket['bracket_id']}].")

    channel = self.get_channel(message.channel.id)
    message = await channel.fetch_message(bracket['bracket_id'])
    await message.channel.send(content=f"**{bracket_name}** has now started!", reference=message) # Reply to original bracket message

    # Send messages for each of the initial open matches
    matches = challonge.matches.index(bracket['challonge']['id'], state='open')
    for match in matches:
       await _match.add_match(self, message, db, bracket, match)

async def finalize_bracket(self, message, db, argv, argc):
    """
    Closes a bracket if completed.
    """
    usage = 'Usage: `$bracket finalize <name>`'
    if argc < 3:
        return await message.channel.send(usage)
    # Get bracket from database
    bracket_name = ' '.join(argv[2:]) # get bracket name
    # Check if bracket exists
    bracket = await get_bracket(self, db, bracket_name)
    if not bracket:
        return await message.channel.send(f"Bracket with name '{bracket_name}' does not exist.")
    # Finalize bracket on challonge
    response = challonge.tournaments.finalize(bracket['challonge']['id'], include_participants=True, include_matches=True)
     # Set bracket to completed in database
    updated_bracket = await mdb.update_single_field(db, {'bracket_id': bracket['bracket_id']}, {'$set': {'completed': True}}, BRACKETS)
    # Update embed message
    await edit_bracket_message(self, updated_bracket, bracket['bracket_id'], message.channel.id, status='Completed ⬛')
    print(f"Finalized bracket '{bracket_name}' [id={bracket['bracket_id']}].")

    channel = self.get_channel(message.channel.id)
    message = await channel.fetch_message(bracket['bracket_id'])
    await message.channel.send(content=f"**{bracket_name}** has been finalized.", reference=message) # Reply to original bracket message
    print(response)

async def reset_bracket(self, message, db, argv, argc):
    """
    Resets a bracket if opened.
    """