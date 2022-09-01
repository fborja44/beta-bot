from cgi import print_exception
from common import BRACKETS, GUILDS, ICON, IMGUR_CLIENT_ID, IMGUR_URL
from datetime import datetime, timedelta, date
from discord import Client, Embed, Guild, Message, Member, RawReactionActionEvent, TextChannel
from dotenv import load_dotenv
from gridfs import Database
from logger import printlog, printlog_msg
from pprint import pprint
from traceback import print_exception
import challonge
import guild as _guild
import match as _match
import mdb
import os
import re
import requests

os.environ['path'] += os.getenv('CAIRO_PATH')
from cairosvg import svg2png # SVG to PNG

# bracket.py
# User created brackets

load_dotenv()

os.environ['path'] += r';C:\Program Files\UniConvertor-2.0rc5\dlls'

time_re_long = re.compile(r'([1-9]|0[1-9]|1[0-2]):[0-5][0-9]\s*([AaPp][Mm])$') # ex. 10:00 AM
time_re_short = re.compile(r'([1-9]|0[1-9]|1[0-2])\s*([AaPp][Mm])$')           # ex. 10 PM

def find_bracket(db_guild: dict, bracket_name: str):
    """
    Retrieves and returns a bracket document from the database (if it exists).
    """
    guild_brackets = db_guild['brackets']
    result = [bracket for bracket in guild_brackets if bracket['name'] == bracket_name]
    if result:
        return result[0]
    return None

def find_bracket_by_id(db_guild: dict, bracket_id: int):
    """
    Retrieves and returns a bracket document from the database (if it exists).
    """
    result = [bracket for bracket in db_guild['brackets'] if bracket['id'] == bracket_id]
    if result:
        return result[0]
    return None

def find_active_bracket(db_guild: dict):
    """
    Returns the current active bracket in a guild.
    """
    try:
        return list(filter(lambda bracket: not bracket['open'] and not bracket['completed'], db_guild['brackets']))[0]
    except:
        return None

def find_most_recent_bracket(db_guild: dict, completed: bool):
    """
    Returns the most recently created bracket in a guild that has not yet been completed
    """
    guild_brackets = db_guild['brackets']
    try:
        if completed:
            guild_brackets = list(filter(lambda bracket: bracket['completed'] is not False, guild_brackets))
            guild_brackets.sort(key=lambda bracket: bracket['completed'], reverse=True)
            return list(filter(lambda bracket: bracket['completed'] is not False, guild_brackets))[0]
        else:
            guild_brackets.sort(key=lambda bracket: bracket['created_at'], reverse=True)
            return list(filter(lambda bracket: not bracket['completed'] , guild_brackets))[0]
    except Exception as e:
        print(e)
        return None

async def create_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Creates a new bracket and adds it to the guild in the database.
    """
    guild: Guild = message.guild
    db_guild = await _guild.find_add_guild(self, db, guild)
    # Check args
    usage = 'Usage: `$bracket create <name> [time]`'
    if argc < 3:
        await message.channel.send(usage)
        return None
    # Parse time; Default is 1 hour from current time
    time, text_match = parse_time(message.content)

    # Get bracket name
    if text_match:
        argv = message.content[:text_match[0]].split()
    bracket_name = ' '.join(argv[2:]) 
    # Max character length == 60
    if len(bracket_name.strip()) > 60:
        await message.channel.send(f"Bracket name can be no longer than 60 characters.")
        return None
    # Check if bracket already exists
    db_bracket = find_bracket(db_guild, bracket_name)
    if db_bracket:
        await message.channel.send(f"Bracket with name '{bracket_name}' already exists.")
        return None
    try:
        # Create challonge bracket
        bracket_challonge = challonge.tournaments.create(name=bracket_name, url=None, tournament_type='double elimination', start_at=time, show_rounds=True, private=True, quick_advance=True, open_signup=False)

        new_bracket = {
            'id': None, 
            'channel_id': message.channel.id,
            'name': bracket_name, 
            'jump_url': message.jump_url,
            'result_url': None,
            'author': {
                'username': message.author.name, 
                'id': message.author.id },
            'challonge': {
                'id': bracket_challonge['id'], 
                'url': bracket_challonge['full_challonge_url'] },
            'entrants': [], 
            'matches': [],
            'created_at': datetime.now(),
            'starttime': time, 
            'endtime': None, 
            'completed': False,
            'open': True,
            'num_rounds': None
        }
        
        # Send embed message
        embed = create_bracket_embed(new_bracket)
        bracket_message: Message = await message.channel.send(embed=embed)
        # Add checkmark reaction to message
        await bracket_message.add_reaction('✅')

        # Add bracket to database
        new_bracket['id'] = bracket_message.id
        result = await _guild.push_to_guild(self, db, guild, BRACKETS, new_bracket)
        print(f"User '{message.author.name}' [id={message.author.id}] created new bracket '{bracket_name}'.")
        return (new_bracket, bracket_message, bracket_challonge)
    except Exception as e:
        msg = "Something went wrong when creating bracket."
        await printlog_msg(msg, msg, message.channel, e)
        # Delete challonge tournament
        try:
            challonge.tournaments.destroy(bracket_challonge['id'])
        except: pass
        # Delete bracket message
        try:
            if bracket_message:
               await bracket_message.delete()
        except: pass
        # Delete bracket document
        try:
            if result:
                await _guild.pull_from_guild(self, db, guild, BRACKETS, new_bracket)
        except: pass
        return None

async def delete_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Deletes the specified bracket from the database (if it exists).
    """
    guild: Guild = message.guild
    db_guild = await _guild.find_guild(self, db, guild.id)
    # Fetch bracket
    usage = 'Usage: `$bracket delete [name]`'
    db_bracket, bracket_name = await parse_args(self, message, db, db_guild, usage, argv, argc)
    retval = True
    if not db_bracket:
        return False
    # Only allow author or guild admins to delete bracket
    if message.author.id != db_bracket['author']['id'] or not message.author.guild_permissions.administrator:
        await message.channel.send(f"Only the author or server admins can delete brackets.")
        return False
    # Check if in channel bracket was created in
    if db_bracket['channel_id'] != message.channel.id:
        await message.channel.send(f"Must be in the channel that the bracket was created in: <#{db_bracket['channel_id']}>")
        return False
    # Delete every match message and document associated with the bracket
    await delete_all_matches(self, message, db, db_bracket)
    # Delete bracket document
    try:
        result = await _guild.pull_from_guild(self, db, guild, BRACKETS, db_bracket)
    except:
        print(f"Failed to delete bracket ['name'={bracket_name}].")
    # Delete bracket message
    try:
        bracket_message: Message = await message.channel.fetch_message(db_bracket['id'])
        await bracket_message.delete() # delete message from channel
    except:
        print(f"Failed to delete message for bracket '{bracket_name}' [id='{db_bracket['id']}']")
    if result:
        try:
            challonge.tournaments.destroy(db_bracket['challonge']['id']) # delete bracket from challonge
        except Exception as e:
            printlog(f"Failed to delete bracket [id='{db_bracket['id']}] from challonge [id='{db_bracket['challonge']['id']}].", e)
            retval = False
        print(f"User '{message.author.name}' [id={message.author.id}] deleted bracket '{bracket_name}'.")
        await message.channel.send(f"Successfully deleted bracket '{bracket_name}'.")
    else:
        await message.channel.send(f"Failed to delete bracket '{bracket_name}'.")
        retval = False
    await message.delete()
    return retval

async def update_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Updates the specified bracket in the database (if it exists).
    TODO
    """
    guild: Guild = message.guild
    db_guild = await _guild.find_guild(self, db, guild.id)
    # Fetch bracket
    usage = 'Usage: `$bracket update [name]`'
    db_bracket, bracket_name = await parse_args(self, message, db, db_guild, usage, argv, argc, send=False)
    if not db_bracket: 
        return False
    # Only allow author or guild admins to update bracket
    if message.author.id != db_bracket['author']['id'] or not message.author.guild_permissions.administrator:
        await message.channel.send(f"Only the author or server admins can update the bracket.")
        return False
    # Check if in channel bracket was created in
    if db_bracket['channel_id'] != message.channel.id:
        await message.channel.send(f"Must be in the channel that the bracket was created in: <#{db_bracket['channel_id']}>")
        return False

async def start_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Starts a bracket created by the user.
    """
    guild: Guild = message.guild
    db_guild = await _guild.find_add_guild(self, db, guild)
    # Fetch bracket
    usage = 'Usage: `$bracket start [name]`'
    db_bracket, bracket_name = await parse_args(self, message, db, db_guild, usage, argv, argc)
    if not db_bracket: 
        return False
    # Only allow author or guild admins to start bracket
    if message.author.id != db_bracket['author']['id'] or not message.author.guild_permissions.administrator:
        await message.channel.send(f"Only the author or server admins can start the bracket.")
        return False
    # Check if in channel bracket was created in
    if db_bracket['channel_id'] != message.channel.id:
        await message.channel.send(f"Must be in the channel that the bracket was created in: <#{db_bracket['channel_id']}>")
        return False
    # Check if already started
    if not db_bracket['open']:
        await message.channel.send(f"'{bracket_name}' has already been started.")
        return False
    # Make sure there are sufficient number of entrants
    if len(db_bracket['entrants']) < 2:
        await message.channel.send(f"Bracket must have at least 2 entrants before starting.")
        return False
    # Only allow one bracket to be started at a time in a guild
    active_bracket = find_active_bracket(db_guild)
    if active_bracket and active_bracket['id'] == db_bracket['id']:
        await message.channel.send(f"There may only be one active bracket per server.")
        return False
    # Start bracket on challonge
    start_response = challonge.tournaments.start(db_bracket['challonge']['id'], include_participants=1, include_matches=1)
    printlog(f"User ['name'='{message.author.name}'] started bracket '{bracket_name}' [id={db_bracket['id']}].")
    # Get total number of rounds
    max_round = 0
    for match in start_response['matches']:
       round = match['match']['round']
       if round > max_round:
           max_round = round
    # Set bracket to closed in database and set total number of rounds
    db_bracket.update({'open': False, 'num_rounds': max_round })
    updated_bracket = await set_bracket(db, guild.id, bracket_name, db_bracket)
    print(f"User ['name'='{message.author.name}'] started bracket ['name'='{bracket_name}'].")
    # Send start message
    bracket_message = await message.channel.fetch_message(db_bracket['id'])
    await message.channel.send(content=f"***{bracket_name}*** has now started!", reference=bracket_message) # Reply to original bracket message
    # Get each initial open matches
    matches = list(filter(lambda match: (match['match']['state'] == 'open'), start_response['matches']))
    for match in matches:
        try:
            await _match.create_match(self, message, db, guild, db_bracket, match['match'])
        except Exception as e:
            printlog(f"Failed to add match ['match_id'='{match['match']['id']}'] to bracket ['name'='{bracket_name}']", e)
    # Update embed message
    await edit_bracket_message(self, db_bracket, message.channel)
    await message.delete()
    return True

async def finalize_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Closes a bracket if completed.
    """
    guild: Guild = message.guild
    db_guild = await _guild.find_guild(self, db, guild.id)
    # Fetch bracket
    usage = 'Usage: `$bracket finalize [name]`'
    completed_time = datetime.now()
    db_bracket, bracket_name = await parse_args(self, message, db, db_guild, usage, argv, argc, active=True)
    if not db_bracket:
        return False
    # Only allow author or guild admins to finalize bracket
    if message.author.id != db_bracket['author']['id'] or not message.author.guild_permissions.administrator:
        await message.channel.send(f"Only the author or server admins can finalize the bracket.")
        return False
    # Check if in channel bracket was created in
    if db_bracket['channel_id'] != message.channel.id:
        await message.channel.send(f"Must be in the channel that the bracket was created in: <#{db_bracket['channel_id']}>")
        return False
    # Check if already finalized
    if db_bracket['completed']:
        await message.channel.send(f"***{bracket_name}*** has already been finalized.")
        return False
    challonge_id = db_bracket['challonge']['id']
    # Finalize bracket on challonge
    try:
        final_bracket = challonge.tournaments.finalize(challonge_id, include_participants=1, include_matches=1)
    except Exception as e:
        printlog(f"Failed to finalize bracket on challonge ['name'='{bracket_name}'].", e)
        try: # Try and retrive bracket information instead of finalizing
            final_bracket = challonge.tournaments.show(challonge_id, include_participants=1, include_matches=1)
        except:
            print(f"Could not find bracket on challonge ['challonge_id'='{challonge_id}'].")
            return False
    # Create results message
    bracket_message = await message.channel.fetch_message(db_bracket['id'])
    db_bracket['completed'] = completed_time
    embed = create_results_embed(db_bracket, final_bracket['participants'])
    result_message = await message.channel.send(content=f"***{bracket_name}*** has been finalized. Here are the results!", reference=bracket_message, embed=embed) # Reply to original bracket message
    # Set bracket to completed in database
    try: 
        db_bracket.update({'completed': completed_time, 'result_url': result_message.jump_url})
        updated_bracket = await set_bracket(db, guild.id, bracket_name, db_bracket)
    except:
        print(f"Failed to update final bracket ['id'='{db_bracket['id']}'].")
        return False
    # Update embed message
    await edit_bracket_message(self, db_bracket, message.channel)
    print(f"User ['name'='{message.author.name}'] Finalized bracket '{bracket_name}' ['id'='{db_bracket['id']}'].")
    await message.delete()
    return True

async def send_results(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Sends the results message of a bracket that has been completed.
    """
    guild: Guild = message.guild
    db_guild = await _guild.find_guild(self, db, guild.id)
    # Fetch bracket
    usage = 'Usage: `$bracket results <name>`'
    db_bracket, bracket_name = await parse_args(self, message, db, db_guild, usage, argv, argc, send=False, completed=True)
    bracket_message_id = db_bracket['id']
    challonge_id = db_bracket['challonge']['id']
    # Check if bracket is completed
    if not db_bracket['completed']:
        await message.channel.send(f"***{bracket_name}*** has not yet been finalized.")
        return False

    # Retrive challonge bracket information
    try: 
        final_bracket = challonge.tournaments.show(challonge_id, include_participants=1, include_matches=1)
    except:
        print(f"Could not find bracket on challonge ['challonge_id'='{challonge_id}'].")
        return False
    # Create results message
    bracket_message = await message.channel.fetch_message(bracket_message_id)
    embed = create_results_embed(db_bracket, final_bracket['participants'])
    result_message = await message.channel.send(reference=bracket_message, embed=embed) # Reply to original bracket message
    await message.delete()
    return True

async def reset_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Resets a bracket if opened.
    """
    guild: Guild = message.guild
    db_guild = await _guild.find_guild(self, db, guild.id)
    # Fetch bracket
    usage = 'Usage: `$bracket reset [name]`'
    db_bracket, bracket_name = await parse_args(self, message, db, db_guild, usage, argv, argc, send=False, active=True)
    bracket_message_id = db_bracket['id']
    challonge_id = db_bracket['challonge']['id']
    if not db_bracket:
        return False
    # Check if in channel bracket was created in
    if db_bracket['channel_id'] != message.channel.id:
        await message.channel.send(f"Must be in the channel that the bracket was created in: <#{db_bracket['channel_id']}>")
        return False
    # Only allow author or guild admins to finalize bracket
    if message.author.id != db_bracket['author']['id'] or not message.author.guild_permissions.administrator:
        await message.channel.send(f"Only the author or server admins can finalize the bracket.")
        return False
    # Check if already completed
    if db_bracket['completed']: 
        message.channel.send("Cannot reset a finalized bracket.")
        return False
    # Delete every match message and document associated with the bracket
    await delete_all_matches(self, message, db, db_bracket)
    # Reset bracket on challonge
    try:
        reset_bracket = challonge.tournaments.reset(challonge_id)
    except Exception as e:
        printlog(f"Something went wrong when resetting bracket ['name'='{bracket_name}'] on challonge.", e)
    # Set open to true and reset number of rounds
    db_bracket.update({'open': True, 'num_rounds': None })
    updated_bracket = await set_bracket(db, guild.id, bracket_name, db_bracket)
    print(f"User ['name'='{message.author.name}'] reset bracket ['name'='{bracket_name}'].")
    # Reset bracket message
    bracket_message = await message.channel.fetch_message(bracket_message_id)
    new_bracket_embed = create_bracket_embed(db_bracket)
    await bracket_message.edit(embed=new_bracket_embed)
    await message.channel.send(f"Successfully reset bracket '{bracket_name}'.")
    await message.delete()
    return True

######################
## HELPER FUNCTIONS ##
######################

async def parse_args(self: Client, message: Message, db: Database, db_guild: dict, usage: str, argv: list, argc: int, f_argc: int=2, 
                     send: bool=True, completed: bool=False, active: bool=False):
    """"
    Parses arguments for bracket functions. Checks if there is a valid bracket.
    """
    if argc < f_argc:
        await message.channel.send(usage)
        return (None, None)
    # Get bracket from database
    if argc >= f_argc + 1:
        bracket_name = ' '.join(argv[2:]) # Get bracket name
        # Check if bracket exists
        db_bracket = find_bracket(db_guild, bracket_name)
        if not db_bracket:
            if send: 
                await message.channel.send(f"Bracket with name '{bracket_name}' does not exist.")
            return (None, None)
    elif argc < f_argc + 1:
        if active: # Get active bracket, if exists
            db_bracket = find_active_bracket(db_guild)
            if not db_bracket:
                if send: 
                    await message.channel.send(f"There are currently no active brackets.")
                return (None, None)
        else: # Get most recently created bracket
            db_bracket = find_most_recent_bracket(db_guild, completed)
            if not db_bracket:
                if send: 
                    await message.channel.send(f"There are currently no open brackets.")
                return (None, None)
        bracket_name = db_bracket['name']
    return (db_bracket, bracket_name)

def find_index_in_bracket(db_bracket: dict, target_field: str, target_key: str, target_value):
    """
    Returns the index of a dictionary in a bracket list.
    """
    for i, dic in enumerate(db_bracket[target_field]):
        if dic[target_key] == target_value:
            return i
    return -1

async def set_bracket(db: Database, guild_id: int, bracket_name: str, new_bracket: dict):
    """
    Sets a bracket in a guild to the specified document.
    """
    return await mdb.update_single_document(db, 
        {'guild_id': guild_id, 'brackets.name': bracket_name, 'brackets.id': new_bracket['id']}, 
        {'$set': {f'brackets.$': new_bracket}
        },
        GUILDS)

async def add_to_bracket(db: Database, guild_id: int, bracket_name: str, target_field: str, document: dict):
    """
    Pushes a document to a bracket subarray.
    """
    return await mdb.update_single_document(db, 
        {'guild_id': guild_id, 'brackets.name': bracket_name}, 
        {'$push': {f'brackets.$.{target_field}': document}},
        GUILDS)

async def remove_from_bracket(db: Database, guild_id: int, bracket_name: str, target_field: str, target_id: int):
    """
    Pulls a document from a bracket subarray.
    """
    return await mdb.update_single_document(db, 
        {'guild_id': guild_id, 'brackets.name': bracket_name}, 
        {'$pull': {f'brackets.$.{target_field}': {'id': target_id}}},
        GUILDS)

async def delete_all_matches(self: Client, message: Message, db: Database, db_bracket: dict):
    """
    Deletes all matches in the specified bracket.
    """
    bracket_name = db_bracket['name']
    retval = True
    for match in db_bracket['matches']:
        match_id = match['id']
        try:
            await _match.delete_match(self, message, db, db_bracket, match_id)
        except:
            print(f"Failed to delete match ['id'={match_id}] while deleting bracket ['name'={bracket_name}].")
            retval = False
    return retval

def parse_time(string: str):
    """
    Helper function to parse a time string in the format XX:XX AM/PM or XX AM/PM.
    Returns the date string and the index of the matched time string.
    If there is no matching time string, returns the current time + 1 hour.
    """
    text_match1 = time_re_long.search(string.strip()) # Check for long time
    text_match2 = time_re_short.search(string.strip()) # Check for short time
    if not text_match1 and not text_match2:
        time = datetime.now() + timedelta(hours=1)
        text_match = None
    else:
        current_time = datetime.now()
        if text_match1:
            text_match = text_match1.span()
            time = datetime.strptime(f'{date.today()} {text_match1.group()}', '%Y-%m-%d %I:%M %p')
        elif text_match2:
            text_match = text_match2.span()
            time = datetime.strptime(f'{date.today()} {text_match2.group()}', '%Y-%m-%d %I %p')
        # Check if current time is before time on current date; If so, go to next day
        if current_time > time:
            time += timedelta(days=1)
    return (time, text_match)

#######################
## ENTRANT FUNCTIONS ##
#######################

def find_entrant(db_bracket: dict, entrant_id):
    """
    Returns an entrant in a bracket by id.
    """
    result = [entrant for entrant in db_bracket['entrants'] if entrant['id'] == entrant_id]
    if result:
        return result[0]
    return None

async def update_bracket_entrants(self: Client, payload: RawReactionActionEvent, db: Database):
    """
    Adds or removes an entrant from a bracket based on whether the reaction was added or removed.
    """
    guild: Guild = self.get_guild(payload.guild_id)
    channel = guild.get_channel(payload.channel_id)
    db_guild = await _guild.find_add_guild(self, db, guild)
    # Check if message reacted to is in brackets and is open
    db_bracket = find_bracket_by_id(db_guild, payload.message_id)
    if not db_bracket or not db_bracket['open']:
        return False 
    if payload.event_type=='REACTION_ADD':
        await add_entrant(self, db, db_bracket, payload.member, channel)
    elif payload.event_type=='REACTION_REMOVE':
        await remove_entrant(self, db, db_bracket, payload.user_id, channel)
    return True

async def add_entrant(self: Client, db: Database, db_bracket: dict, member: Member, channel: TextChannel):
    """
    Adds an entrant to a bracket.
    """
    bracket_name = db_bracket['name']
    entrant_names = [] # list of entrant names
    for entrant in db_bracket['entrants']:
        entrant_names.append(entrant['id'])
    challonge_id = db_bracket['challonge']['id']
    # Add user to challonge bracket
    try:
        response = challonge.participants.create(challonge_id, member.name)
    except Exception as e:
        printlog(f"Failed to add user ['name'='{member.name}'] to challonge bracket. User may already exist.", e)
        return False
    # Check if already in entrants list
    if member.name in entrant_names:
        printlog(f"User ['name'='{member.name}']' is already registered as an entrant in bracket ['name'='{bracket_name}'].")
        return False
    # Add user to entrants list
    new_entrant = {
        'id': member.id, 
        'challonge_id': response['id'],
        'name': member.name, 
        'placement': None,
        'active': True
        }
    try:
        updated_guild = await add_to_bracket(db, channel.guild.id, bracket_name, 'entrants', new_entrant)
        db_bracket['entrants'].append(new_entrant)
    except:
        print(f"Failed to add user '{member.name}' to bracket ['name'='{bracket_name}'] entrants.")
        return False
    if updated_guild:
        print(f"Added entrant '{member.name}' ['id'='{member.id}'] to bracket ['name'='{bracket_name}'].")
        # Update message
        await edit_bracket_message(self, db_bracket, channel)
    else:
        print(f"Failed to add entrant '{member.name}' ['id'='{member.id}'] to bracket ['name'='{bracket_name}'].")
        return False
    return True

async def remove_entrant(self: Client, db: Database, db_bracket: dict, user_id: int, channel: TextChannel):
    """
    Destroys an entrant from a tournament or DQs them if the tournament has already started.
    """
    # Remove user from challonge bracket
    bracket_name = db_bracket['name']
    entrant_names = [] # list of entrant names
    for entrant in db_bracket['entrants']:
        entrant_names.append(entrant['id'])
    challonge_id = db_bracket['challonge']['id']
    bracket_id = db_bracket['id']
    # Check if already in entrants list
    if user_id not in entrant_names:
        printlog(f"User ['id'='{user_id}']' is not registered as an entrant in bracket ['name'='{bracket_name}'].")
        return False
    db_entrant = list(filter(lambda entrant: entrant['id'] == user_id, db_bracket['entrants']))[0]
    try:
        response = challonge.participants.destroy(challonge_id, db_entrant['challonge_id'])
    except Exception as e:
        printlog(f"Failed to remove user ['name'='{db_entrant['name']}'] from challonge bracket. User may not exist.", e)
        return False
    # Remove user from entrants list
    try:
        updated_guild = await remove_from_bracket(db, channel.guild.id, bracket_name, 'entrants', db_entrant['id'])
        db_bracket['entrants'] = list(filter(lambda entrant: entrant['name'] != entrant['name'], db_bracket['entrants']))
    except:
        print(f"Failed to remove user '{db_entrant['name']}' from bracket ['name'='{bracket_name}'] entrants.")
        return False
    if updated_guild:
        print(f"Removed entrant ['name'='{db_entrant['name']}']from bracket [id='{bracket_id}'].")
        # Update message
        await edit_bracket_message(self, db_bracket, channel)
    else:
        print(f"Failed to remove entrant ['name'='{db_entrant['name']}']from bracket [id='{bracket_id}'].")

async def disqualify_entrant_main(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Destroys an entrant from a tournament or DQs them if the tournament has already started from a command.
    Main function.
    """
    guild: Guild = message.guild
    db_guild = await _guild.find_add_guild(self, db, guild)
    usage = 'Usage: `$bracket dq <entrant name>`. Must be in a reply to a bracket or match.'
    # Parse args
    if argc < 3 or not message.reference:
        await message.channel.send(usage)
        return False
    entrant_name = ' '.join(argv[2:])
    # Get active bracket
    db_bracket = find_active_bracket(db_guild)
    if not db_bracket:
        await message.channel.send("There are currently no active brackets.")
        return False

    # Check if replying to a bracket message
    if db_bracket['id'] == message.reference.message_id:
        return await disqualify_entrant_bracket(self, message, db, db_guild, db_bracket, entrant_name)

    # Check if replying to match message
    try:
        db_match = _match.find_match(db_bracket, message.reference.message_id)
    except Exception as e:
        printlog("Something went wrong when trying to retrive a match while DQing.", e)
        return False
    if db_match:
        return await _match.disqualify_entrant_match(self, message, db, db_guild, db_bracket, db_match, entrant_name)
    await message.channel.send("DQ must be in reply to a bracket or match message.")
    return False

async def disqualify_entrant_bracket(self: Client, message: Message, db: Database, db_guild: dict, db_bracket: dict, entrant_name: str):
    """
    Destroys an entrant from a tournament or DQs them if the tournament has already started from a command.
    Bracket version.
    """
    bracket_name = db_bracket['name']
    # Check if entrant exists
    db_entrant = None
    for elem in db_bracket['entrants']:
        if elem['name'].lower() == entrant_name.lower():
            db_entrant = elem
    if not db_entrant:
        printlog(f"User ['name'='{entrant_name}']' is not an entrant in bracket ['name'='{bracket_name}'].")
        await message.channel.send(f"There is no entrant named '{entrant_name}' in ***{bracket_name}***.")
        return False
    elif not db_entrant['active']:
        await message.channel.send(f"Entrant '{entrant_name}' has already been disqualified from ***{bracket_name}***.")
        return False

    # Call dq helper function
    return await disqualify_entrant(self, message, db, db_guild, db_bracket, db_entrant)

async def disqualify_entrant(self: Client, message: Message, db: Database, db_guild: dict, db_bracket: dict, db_entrant: dict):
    """
    Function to dq an entrant in the database and challonge.
    """
    bracket_name = db_bracket['name']
    challonge_id = db_bracket['challonge']['id']
    entrant_name = db_entrant['name']
    db_entrant['active'] = False
    entrant_index = find_index_in_bracket(db_bracket, 'entrants', 'id', db_entrant['id'])
    db_bracket['entrants'][entrant_index] = db_entrant
    # Update entrant in database
    try:
        await set_bracket(db, db_guild['guild_id'], bracket_name, db_bracket)
    except:
        print("Failed to DQ entrant in database.")
        return False
    # Disqualify entrant on challonge
    try:
        challonge.participants.destroy(challonge_id, db_entrant['challonge_id'])
    except Exception as e:
        printlog(f"Failed to DQ entrant ['name'='{entrant_name}'] from bracket ['name'='{bracket_name}']", e)
        return False

    # Update all open matches
    winner_emote = None
    for bracket_match in db_bracket['matches']:
        # Get match document
        db_match = _match.find_match(db_bracket, bracket_match['id'])
        # Check if match is open
        if db_match['completed']:
            continue
        # Check the players; Other player wins
        if entrant_name == db_entrant['name']: #TODO: Broken
            winner_emote = '2️⃣'
            break
        elif entrant_name == db_entrant['name']:
            winner_emote = '1️⃣'
            break
    if winner_emote:
        # Report match
        match_message = await message.channel.fetch_message(db_match['id'])
        await _match.report_match(self, match_message, db, db_guild, db_bracket, db_match, winner_emote, is_dq=True)
    await message.delete()
    return True

#######################
## MESSAGE FUNCTIONS ##
#######################

async def edit_bracket_message(self: Client, db_bracket: dict, channel: TextChannel):
    """
    Edits bracket embed message in a channel.
    """
    bracket_name = db_bracket['name']
    bracket_message: Message = await channel.fetch_message(db_bracket['id'])
    embed = bracket_message.embeds[0]
    embed = update_embed_entrants(db_bracket, embed)
    if not db_bracket['open']:
        image_embed = None
        try:
            image_embed = create_bracket_image(db_bracket, embed)
        except Exception as e:
            printlog(f"Failed to create image for bracket ['name'='{bracket_name}'].")
            print(e)
        if not image_embed:
            printlog(f"Error when creating image for bracket ['name'='{bracket_name}'].")
        else:
            embed = image_embed
    if db_bracket['completed']:
        time_str = db_bracket['completed'].strftime("%A, %B %d, %Y %#I:%M %p") # time w/o ms
        embed.set_footer(text=f'Completed: {time_str}')
        embed.set_author(name="Click Here to See Results", url=db_bracket['result_url'], icon_url=ICON)
    await bracket_message.edit(embed=embed)

def update_embed_entrants(db_bracket: dict, embed: Embed):
    """
    Updates the entrants list in a bracket embed.
    """
    entrants = db_bracket['entrants']
    if len(entrants) > 0:
        entrants_content = ""
        for entrant in entrants:
            # To mention a user:
            # <@{user_id}>
            entrants_content += f"> <@{entrant['id']}>\n"
    else:
        entrants_content = '> *None*'
    embed.set_field_at(1, name=f'Entrants ({len(entrants)})', value=entrants_content, inline=False)
    return embed

def create_bracket_image(db_bracket: dict, embed: Embed):
    """
    Creates an image of the bracket.
    Converts the generated svg challonge image to png and uploads it to imgur.
    Discord does not support svg images in preview.
    """
    bracket_name = db_bracket['name']
    challonge_url = db_bracket['challonge']['url']
    if len(db_bracket['entrants']) >= 2:
        svg_url = f"{challonge_url}.svg"
        print("svg_url: ", svg_url)
        png_data = svg2png(url=svg_url) # Convert svg to png
        payload = {
            'image': png_data
        }
        headers = {
            'Authorization': f'Client-ID {IMGUR_CLIENT_ID}'
        }
        response = requests.request("POST", f"{IMGUR_URL}/image", headers=headers, data=payload, files=[])
        if response.status_code == requests.codes.ok:
            data = response.json()['data']
            image_link = data['link']
            embed.set_image(url=image_link)
            return embed
        else:
            printlog(f"Failed to create image for bracket ['name'='{bracket_name}'].")
            return False
    else:
        printlog(f"Failed to create image for bracket ['name'='{bracket_name}'].")
        return False

def create_bracket_embed(db_bracket: dict):
    """
    Creates embed object to include in bracket message.
    """
    author_name = db_bracket['author']['username']
    bracket_name = db_bracket['name']
    challonge_url = db_bracket['challonge']['url']
    time = db_bracket['starttime']
    
    # Check the status
    if db_bracket['completed']:
        status = "Completed 🏁"
    elif db_bracket['open']:
        status = "🚨 Open for Registration 🚨"
    else:
        status = "Started 🟩"

    embed = Embed(title=f'🥊  {bracket_name}', description=f"Status:  {status}", color=0x6A0DAD)
    embed.set_author(name="beta-bot | GitHub 🤖", url="https://github.com/fborja44/beta-bot", icon_url=ICON)
    time_str = time.strftime("%A, %B %d, %Y %#I:%M %p") # time w/o ms
    embed.add_field(name='Starting At', value=time_str, inline=False)
    # Entrants list
    embed.add_field(name='Entrants (0)', value="> *None*", inline=False)
    embed = update_embed_entrants(db_bracket, embed)
    embed.add_field(name=f'Bracket Link', value=challonge_url, inline=False)
    embed.set_footer(text=f'React with ✅ to enter! | Created by {author_name}')
    return embed

def create_results_embed(db_bracket: dict, entrants: list):
    """
    Creates embed object with final results to include after finalizing bracket.
    """
    bracket_name = db_bracket['name']
    challonge_url = db_bracket['challonge']['url']
    jump_url = db_bracket['jump_url']
    embed = Embed(title='🏆  Final Results', color=0xFAD25A)
    embed.set_author(name=bracket_name, url=jump_url, icon_url=ICON)
    results_content = ""
    entrants.sort(key=(lambda entrant: entrant['participant']['final_rank']))
    for i in range (min(len(entrants), 8)):
        entrant = entrants[i]['participant']
        match entrant['final_rank']:
            case 1:
                results_content += f"> 🥇  {entrant['name']}\n"
            case 2:
                results_content += f"> 🥈  {entrant['name']}\n"
            case 3:
                results_content += f"> 🥉  {entrant['name']}\n"
            case _:
                results_content += f"> **{entrant['final_rank']}.** {entrant['name']}\n"
    embed.add_field(name=f'Placements', value=results_content, inline=False)
    embed.add_field(name=f'Bracket Link', value=challonge_url, inline=False)
    time_str = db_bracket['completed'].strftime("%A, %B %d, %Y %#I:%M %p") # time w/o ms
    embed.set_footer(text=f'Completed: {time_str}')
    return embed

#######################
## TESTING FUNCTIONS ##
#######################

async def create_test_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Testing function. Creates a test bracket and adds two entrants.
    """
    printlog("Creating test bracket...")
    bracket_name = "Test Bracket"
    bracket_db , bracket_message , bracket_challonge = None, None, None
    guild: Guild = message.guild
    db_guild = await _guild.find_add_guild(self, db, guild)
    # Only allow guild admins to create a test bracket
    if not message.author.guild_permissions.administrator:
        return await message.channel.send(f"Only admins can create a test bracket.")

    # Delete previous test bracket if it exists
    try:
        db_bracket = find_bracket(db_guild, bracket_name)
        if db_bracket:
            argv = ["$bracket", "delete", bracket_name]
            await delete_bracket(self, message, db, argv, len(argv))
        # Call create_bracket
        argv = ["$bracket", "create", bracket_name]
        bracket_db, bracket_message, bracket_challonge = await create_bracket(self, message, db, argv, len(argv))
        
        # Add first entrant
        member1 = guild.get_member_named('beta#3096')
        await add_entrant(self, db, bracket_db, member1, message.channel)
        # Add second entrant
        # member2 = guild.get_member_named("pika!#3722")
        # await add_entrant(self, db, bracket_db, member2, message.channel)
        # Add third entrant
        member3 = guild.get_member_named("Wooper#0478")
        await add_entrant(self, db, bracket_db, member3, message.channel)
        # Add fourth entrant
        member4 = guild.get_member_named("WOOPBOT#4140")
        await add_entrant(self, db, bracket_db, member4, message.channel)
        return True
    except Exception as e:
        await printlog_msg("Failed to create test bracket.", "Something went wrong when creating the bracket.", message.channel)
        print_exception(e)
        if bracket_message:
            argv = ["$bracket", "delete", bracket_name]
            try:
                await delete_bracket(self, message, db, argv, len(argv))
            except: pass
        return False