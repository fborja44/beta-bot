from cgi import print_exception
from common import BRACKETS, GUILDS, ICON, IMGUR_CLIENT_ID, IMGUR_URL
from datetime import datetime, timedelta, date
from discord import Client, Embed, Guild, Interaction, Message, Member, RawReactionActionEvent, TextChannel
from dotenv import load_dotenv
from gridfs import Database
from logger import printlog, printlog_msg
from pprint import pprint
from traceback import print_exception
import challonge
import discord
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

def find_bracket(db_guild: dict, bracket_title: str):
    """
    Retrieves and returns a bracket document from the database (if it exists).
    """
    guild_brackets = db_guild['brackets']
    result = [bracket for bracket in guild_brackets if bracket['title'] == bracket_title]
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

async def create_bracket(interaction: Interaction, bracket_title: str, time: str=""):
    """
    Creates a new bracket and adds it to the guild in the database.
    """
    guild: Guild = interaction.guild
    channel: TextChannel = interaction.channel
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Check args
    # usage = 'Usage: `$bracket create <name> [time]`'

    # Parse time; Default is 1 hour from current time
    parsed_time = parse_time(time)

    # Max character length == 60
    if len(bracket_title.strip()) > 60:
        await channel.send(f"Bracket name can be no longer than 60 characters.")
        return None, None, None
    # Check if bracket already exists
    db_bracket = find_bracket(db_guild, bracket_title)
    if db_bracket:
        await channel.send(f"Bracket with name '{bracket_title}' already exists.")
        return None, None, None
    try:
        # Create challonge bracket
        bracket_challonge = challonge.tournaments.create(name=bracket_title, url=None, tournament_type='double elimination', 
            start_at=parsed_time, show_rounds=True, private=True, quick_advance=True, open_signup=False)

        new_bracket = {
            'id': None, # Initialized later
            'channel_id': channel.id,
            'title': bracket_title, 
            'jump_url': None, # Initialized later
            'result_url': None,
            'author': {
                'username': user.name, 
                'id': user.id },
            'challonge': {
                'id': bracket_challonge['id'], 
                'url': bracket_challonge['full_challonge_url'] },
            'entrants': [], 
            'matches': [],
            'created_at': datetime.now(),
            'starttime': parsed_time, 
            'endtime': None, 
            'completed': False,
            'open': True,
            'num_rounds': None
        }
        
        # Send embed message
        embed = create_bracket_embed(new_bracket)
        bracket_message: Message = await channel.send(embed=embed, view=registration_buttons_view())

        # Add bracket to database
        new_bracket['id'] = bracket_message.id
        new_bracket['jump_url'] = bracket_message.jump_url
        result = await _guild.push_to_guild(guild, BRACKETS, new_bracket)
        print(f"User '{user.name}' [id={user.id}] created new bracket '{bracket_title}'.")
        await interaction.response.send_message(f"Successfully created bracket '***{bracket_title}***'.", ephemeral=True)
        return (new_bracket, bracket_message, bracket_challonge)
    except Exception as e:
        await printlog("Something went wrong when creating the bracket.", e)
        await interaction.response.send_message(f"Something went wrong when creating bracket '***{bracket_title}***'.", ephemeral=True)
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
                await _guild.pull_from_guild(guild, BRACKETS, new_bracket)
        except: pass
        return None, None, None

async def delete_bracket(interaction: Interaction, bracket_title: str):
    """
    Deletes the specified bracket from the database (if it exists).
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    # Fetch bracket
    # usage = 'Usage: `$bracket delete [title]`'
    db_bracket, bracket_title = await retrieve_valid_bracket(channel, db_guild, bracket_title)
    retval = True
    if not db_bracket:
        return False
    # Only allow author or guild admins to delete bracket
    if user != db_bracket['author']['id'] and not user.guild_permissions.administrator:
        await interaction.response.send_message(f"Only the author or server admins can delete brackets.", ephemeral=True)
        return False
    # Check if in channel bracket was created in
    if db_bracket['channel_id'] != channel.id:
        await interaction.response.send_message(f"Must be in the channel that '***{bracket_title}***' was created in: <#{db_bracket['channel_id']}>.", ephemeral=True)
        return False
    # Delete every match message and document associated with the bracket
    await delete_all_matches(channel, db_bracket)
    # Delete bracket document
    try:
        result = await _guild.pull_from_guild(guild, BRACKETS, db_bracket)
    except:
        print(f"Failed to delete bracket ['name'={bracket_title}].")
    # Delete bracket message
    try:
        bracket_message: Message = await channel.fetch_message(db_bracket['id'])
        await bracket_message.delete() # delete message from channel
    except:
        print(f"Failed to delete message for bracket '{bracket_title}' [id='{db_bracket['id']}']")
    if result:
        try:
            challonge.tournaments.destroy(db_bracket['challonge']['id']) # delete bracket from challonge
        except Exception as e:
            printlog(f"Failed to delete bracket [id='{db_bracket['id']}] from challonge [id='{db_bracket['challonge']['id']}].", e)
            retval = False
        print(f"User '{user.name}' [id={user.id}] deleted bracket '{bracket_title}'.")
    else:
        await interaction.response.send_message(f"Failed to delete bracket '***{bracket_title}***'.", ephemeral=True)
        retval = False
    await interaction.response.send_message(f"Successfully deleted bracket '***{bracket_title}***'.")
    return retval

async def update_bracket(interaction: Interaction):
    """
    Updates the specified bracket in the database (if it exists).
    TODO
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    # Fetch bracket
    # usage = 'Usage: `$bracket update [name]`'
    db_bracket, bracket_title = await retrieve_valid_bracket(channel, db_guild, bracket_title)
    if not db_bracket: 
        return False
    # Only allow author or guild admins to update bracket
    if user.id != db_bracket['author']['id'] and not user.guild_permissions.administrator:
        await interaction.response.send_message(f"Only the author or server admins can update the bracket.", ephemeral=True)
        return False
    # Check if in channel bracket was created in
    if db_bracket['channel_id'] != channel.id:
        await interaction.response.send_message(f"Must be in the channel that '***{bracket_title}***' was created in: <#{db_bracket['channel_id']}>.", ephemeral=True)
        return False

async def start_bracket(interaction: Interaction, bracket_title: str):
    """
    Starts a bracket created by the user.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Fetch bracket
    # usage = 'Usage: `$bracket start [title]`'
    db_bracket, bracket_title = await retrieve_valid_bracket(channel, db_guild, bracket_title)
    if not db_bracket: 
        return False
    # Only allow author or guild admins to start bracket
    if user.id != db_bracket['author']['id'] and not user.guild_permissions.administrator:
        await interaction.response.send_message(f"Only the author or server admins can start the bracket.", ephemeral=True)
        return False
    # Check if in channel bracket was created in
    if db_bracket['channel_id'] != channel.id:
        await interaction.response.send_message(f"Must be in the channel that '***{bracket_title}***' was created in: <#{db_bracket['channel_id']}>.", ephemeral=True)
        return False
    # Check if already started
    if not db_bracket['open']:
        await interaction.response.send_message(f"'{bracket_title}' has already been started.", ephemeral=True)
        return False
    # Make sure there are sufficient number of entrants
    if len(db_bracket['entrants']) < 2:
        await interaction.response.send_message(f"Bracket must have at least 2 entrants before starting.", ephemeral=True)
        return False
    # Only allow one bracket to be started at a time in a guild
    active_bracket = find_active_bracket(db_guild)
    if active_bracket and active_bracket['id'] == db_bracket['id']:
        await interaction.response.send_message(f"There may only be one active bracket per server.", ephemeral=True)
        return False
    # Start bracket on challonge
    start_response = challonge.tournaments.start(db_bracket['challonge']['id'], include_participants=1, include_matches=1)
    printlog(f"User ['name'='{user.name}'] started bracket '{bracket_title}' [id={db_bracket['id']}].")
    # Get total number of rounds
    max_round = 0
    for match in start_response['matches']:
       round = match['match']['round']
       if round > max_round:
           max_round = round
    # Set bracket to closed in database and set total number of rounds
    db_bracket.update({'open': False, 'num_rounds': max_round })
    await set_bracket(guild.id, bracket_title, db_bracket)
    print(f"User ['name'='{user.name}'] started bracket ['title'='{bracket_title}'].")
    # Send start message
    bracket_message = await channel.fetch_message(db_bracket['id'])
    await interaction.response.send_message(content=f"***{bracket_title}*** has now started!", reference=bracket_message) # Reply to original bracket message
    # Get each initial open matches
    matches = list(filter(lambda match: (match['match']['state'] == 'open'), start_response['matches']))
    for match in matches:
        try:
            await _match.create_match(interaction, guild, db_bracket, match['match'])
        except Exception as e:
            printlog(f"Failed to add match ['match_id'='{match['match']['id']}'] to bracket ['title'='{bracket_title}']", e)
    # Update embed message
    await edit_bracket_message(db_bracket, channel)
    return True

async def reset_bracket(interaction: Interaction, bracket_title: str):
    """
    Resets a bracket if it has been started.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    # Fetch bracket
    # usage = 'Usage: `$bracket reset [title]`'
    db_bracket, bracket_title = await retrieve_valid_bracket(channel, db_guild, bracket_title, active=True)
    bracket_message_id = db_bracket['id']
    challonge_id = db_bracket['challonge']['id']
    if not db_bracket:
        return False
    # Check if in channel bracket was created in
    if db_bracket['channel_id'] != channel.id:
        await interaction.response.send_message(f"Must be in the channel that '***{bracket_title}***' was created in: <#{db_bracket['channel_id']}>.", ephemeral=True)
        return False
    # Only allow author or guild admins to finalize bracket
    if user.id != db_bracket['author']['id'] and not user.guild_permissions.administrator:
        await interaction.response.send_message(f"Only the author or server admins can reset the bracket.", ephemeral=True)
        return False
    # Check if already completed
    if db_bracket['completed']: 
        await interaction.response.send_message(f"Cannot reset a finalized bracket.", ephemeral=True)
        return False
    # Delete every match message and document associated with the bracket
    await delete_all_matches(channel, db_bracket)
    # Reset bracket on challonge
    try:
        challonge.tournaments.reset(challonge_id)
    except Exception as e:
        printlog(f"Something went wrong when resetting bracket ['title'='{bracket_title}'] on challonge.", e)
    # Set open to true and reset number of rounds
    db_bracket.update({'open': True, 'num_rounds': None })
    await set_bracket(guild.id, bracket_title, db_bracket)
    print(f"User ['name'='{user.name}'] reset bracket ['title'='{bracket_title}'].")
    # Reset bracket message
    bracket_message = await channel.fetch_message(bracket_message_id)
    new_bracket_embed = create_bracket_embed(db_bracket)
    await bracket_message.edit(embed=new_bracket_embed)
    await interaction.response.send_message(f"Successfully reset bracket '***{bracket_title}***'.")
    return True

async def finalize_bracket(interaction: Interaction, bracket_title: str):
    """
    Closes a bracket if completed.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    # Fetch bracket
    # usage = 'Usage: `$bracket finalize [title]`'
    completed_time = datetime.now()
    db_bracket, bracket_title = await retrieve_valid_bracket(channel, db_guild, bracket_title, active=True)
    if not db_bracket:
        return False
    # Only allow author or guild admins to finalize bracket
    if user.id != db_bracket['author']['id'] and not user.guild_permissions.administrator:
        await interaction.response.send_message(f"Only the author or server admins can finalize the bracket.", ephemeral=True)
        return False
    # Check if in channel bracket was created in
    if db_bracket['channel_id'] != channel.id:
        await interaction.response.send_message(f"Must be in the channel that '***{bracket_title}***' was created in: <#{db_bracket['channel_id']}>.", ephemeral=True)
        return False
    # Check if already finalized
    if db_bracket['completed']:
        await interaction.response.send_message(f"'***{bracket_title}***' has already been finalized.", ephemeral=True)
        return False
    challonge_id = db_bracket['challonge']['id']
    # Finalize bracket on challonge
    try:
        final_bracket = challonge.tournaments.finalize(challonge_id, include_participants=1, include_matches=1)
    except Exception as e:
        printlog(f"Failed to finalize bracket on challonge ['title'='{bracket_title}'].", e)
        try: # Try and retrive bracket information instead of finalizing
            final_bracket = challonge.tournaments.show(challonge_id, include_participants=1, include_matches=1)
        except:
            print(f"Could not find bracket on challonge ['challonge_id'='{challonge_id}'].")
            return False
    # Create results message
    bracket_message = await channel.fetch_message(db_bracket['id'])
    db_bracket['completed'] = completed_time
    embed = create_results_embed(db_bracket, final_bracket['participants'])
    result_message = await interaction.response.send_message(content=f"***{bracket_title}*** has been finalized. Here are the results!", reference=bracket_message, embed=embed) # Reply to original bracket message
    # Set bracket to completed in database
    try: 
        db_bracket.update({'completed': completed_time, 'result_url': result_message.jump_url})
        await set_bracket(guild.id, bracket_title, db_bracket)
    except:
        print(f"Failed to update final bracket ['id'='{db_bracket['id']}'].")
        return False
    # Update embed message
    await edit_bracket_message(db_bracket, channel)
    print(f"User ['name'='{user.name}'] Finalized bracket '{bracket_title}' ['id'='{db_bracket['id']}'].")
    return True

async def send_results(interaction: Interaction, bracket_title: str):
    """
    Sends the results message of a bracket that has been completed.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    db_guild = await _guild.find_guild(guild.id)
    # Fetch bracket
    usage = 'Usage: `$bracket results <title>`'
    db_bracket, bracket_title = await retrieve_valid_bracket(channel, db_guild, bracket_title, completed=True)
    bracket_message_id = db_bracket['id']
    challonge_id = db_bracket['challonge']['id']
    if not db_bracket:
        return False
    # Check if bracket is completed
    if not db_bracket['completed']:
        await interaction.response.send_message(f"***{bracket_title}*** has not yet been finalized.", ephemeral=True)
        return False

    # Retrive challonge bracket information
    try: 
        final_bracket = challonge.tournaments.show(challonge_id, include_participants=1, include_matches=1)
    except:
        print(f"Could not find bracket on challonge ['challonge_id'='{challonge_id}'].")
        return False
    # Create results message
    bracket_message = await channel.fetch_message(bracket_message_id)
    embed = create_results_embed(db_bracket, final_bracket['participants'])
    await interaction.response.send_message(reference=bracket_message, embed=embed) # Reply to original bracket message
    return True

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

async def add_entrant(interaction: Interaction, db_bracket: dict=None, member: Member=None):
    """
    Adds an entrant to a bracket.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    message: Message = interaction.message
    user: Member = member or interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Fetch bracket
    db_bracket = db_bracket or find_bracket_by_id(db_guild, message.id)
    if not db_bracket or not db_bracket['open']:
        await interaction.response.send_message(f"'***{bracket_title}***' is not open for registration.", ephemeral=True)
        return False 
    bracket_title = db_bracket['title']
    entrant_ids = [] # list of entrant names
    for entrant in db_bracket['entrants']:
        entrant_ids.append(entrant['id'])
    challonge_id = db_bracket['challonge']['id']
    # Check if already in entrants list
    if user.id in entrant_ids:
        # printlog(f"User ['name'='{user.name}']' is already registered as an entrant in bracket ['title'='{bracket_title}'].")
        await interaction.response.send_message(f"You have already joined '***{bracket_title}***'.", ephemeral=True)
        return False
    # Add user to challonge bracket
    try:
        response = challonge.participants.create(challonge_id, user.name)
    except Exception as e:
        printlog(f"Failed to add user ['name'='{user.name}'] to challonge bracket. User may already exist.", e)
        await interaction.response.send_message(f"Something went wrong when trying to join '***{bracket_title}***'.", ephemeral=True)
        return False
    # Add user to entrants list
    new_entrant = {
        'id': user.id, 
        'challonge_id': response['id'],
        'name': user.name, 
        'placement': None,
        'active': True
        }
    try:
        updated_guild = await add_to_bracket(guild.id, bracket_title, 'entrants', new_entrant)
        db_bracket['entrants'].append(new_entrant)
    except:
        print(f"Failed to add user '{user.name}' to bracket ['title'='{bracket_title}'] entrants.")
        await interaction.response.send_message(f"Something went wrong when trying to join '***{bracket_title}***'.", ephemeral=True)
        return False
    if updated_guild:
        print(f"Added entrant '{user.name}' ['id'='{user.id}'] to bracket ['title'='{bracket_title}'].")
        # Update message
        await edit_bracket_message(db_bracket, channel)
    else:
        print(f"Failed to add entrant '{user.name}' ['id'='{user.id}'] to bracket ['title'='{bracket_title}'].")
        await interaction.response.send_message(f"Something went wrong when trying to join '***{bracket_title}***'.", ephemeral=True)
        return False
    await interaction.response.send_message(f"Successfully joined '***{bracket_title}***'.", ephemeral=True)
    return True

async def remove_entrant(interaction: Interaction):
    """
    Destroys an entrant from a tournament or DQs them if the tournament has already started.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    message: Message = interaction.message
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Fetch bracket
    db_bracket = find_bracket_by_id(db_guild, message.id)
    if not db_bracket or not db_bracket['open']:
        return False 
    # Remove user from challonge bracket
    bracket_title = db_bracket['title']
    entrant_names = [] # list of entrant names
    for entrant in db_bracket['entrants']:
        entrant_names.append(entrant['id'])
    challonge_id = db_bracket['challonge']['id']
    bracket_id = db_bracket['id']
    # Check if already in entrants list
    if user.id not in entrant_names:
        printlog(f"User ['id'='{user.id}']' is not registered as an entrant in bracket ['title'='{bracket_title}'].")
        await interaction.response.send_message(f"You are not registered for '***{bracket_title}***'.", ephemeral=True)
        return False
    db_entrant = list(filter(lambda entrant: entrant['id'] == user.id, db_bracket['entrants']))[0]
    try:
        challonge.participants.destroy(challonge_id, db_entrant['challonge_id'])
    except Exception as e:
        printlog(f"Failed to remove user ['name'='{db_entrant['name']}'] from challonge bracket. User may not exist.", e)
        await interaction.response.send_message(f"Something went wrong when trying to leave '***{bracket_title}***'.", ephemeral=True)
        return False
    # Remove user from entrants list
    try:
        updated_guild = await remove_from_bracket(channel.guild.id, bracket_title, 'entrants', db_entrant['id'])
        db_bracket['entrants'] = list(filter(lambda entrant: entrant['id'] != user.id, db_bracket['entrants']))
    except:
        print(f"Failed to remove user '{db_entrant['name']}' from bracket ['title'='{bracket_title}'] entrants.")
        await interaction.response.send_message(f"Something went wrong when trying to leave '***{bracket_title}***'.", ephemeral=True)
        return False
    if updated_guild:
        print(f"Removed entrant ['name'='{db_entrant['name']}']from bracket [id='{bracket_id}'].")
        # Update message
        await edit_bracket_message(db_bracket, channel)
    else:
        print(f"Failed to remove entrant ['name'='{db_entrant['name']}']from bracket [id='{bracket_id}'].")
        await interaction.response.send_message(f"Something went wrong when trying to leave '***{bracket_title}***'.", ephemeral=True)
        return False
    await interaction.response.send_message(f"Successfully removed from '***{bracket_title}***'.", ephemeral=True)
    return True

async def disqualify_entrant_main(interaction: Interaction, bracket_title: str, entrant_name: str):
    """
    Destroys an entrant from a tournament or DQs them if the tournament has already started from a command.
    Main function.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    usage = 'Usage: `$bracket dq <entrant name>`. There must be an active bracket, or must be in a reply to a bracket message.'
    # Retrieve bracket
    db_bracket = None
    if len(bracket_title.strip()) > 0:
        # Get bracket by title
        db_bracket = find_bracket(db_guild, bracket_title)
        if not db_bracket or db_bracket['completed']:
            channel.send("Must reply to a bracket that has not been completed.")
            return False
    else:
        # Get active bracket
        db_bracket = find_active_bracket(db_guild)
        if not db_bracket:
            await channel.send(f"There are currently no active brackets.")
            return False
    # Only allow author, guild admins, or self to dq a user
    if user.id != db_bracket['author']['id'] and not user.guild_permissions.administrator and user.name != entrant_name:
        await channel.send(f"Only the author or server admins can delete brackets.")
        return False
    bracket_title = db_bracket['title']
    # Check if entrant exists
    db_entrant = None
    for elem in db_bracket['entrants']:
        if elem['name'].lower() == entrant_name.lower():
            db_entrant = elem
    if not db_entrant:
        printlog(f"User ['name'='{entrant_name}']' is not an entrant in bracket ['title'='{bracket_title}'].")
        await channel.send(f"There is no entrant named '{entrant_name}' in ***{bracket_title}***.")
        return False
    elif not db_entrant['active']:
        await channel.send(f"Entrant '{entrant_name}' has already been disqualified from ***{bracket_title}***.")
        return False

    # If bracket is still in registration phase, just remove from bracket
    if db_bracket['open']:
        # Remove reaction by user
        member: Member = await guild.fetch_member(db_entrant['id'])
        bracket_message: Message = await channel.fetch_message(db_bracket['id'])
        try:
            await bracket_message.remove_reaction('✅', member)
        except:
            pass
        return await remove_entrant(db_bracket, db_entrant['id'], channel)

    # Call dq helper function
    return await disqualify_entrant(channel, db_guild, db_bracket, db_entrant)

async def disqualify_entrant(channel: TextChannel, db_guild: dict, db_bracket: dict, db_entrant: dict):
    """
    Function to dq an entrant in the database and challonge. Updates messages.
    """
    bracket_title = db_bracket['title']
    challonge_id = db_bracket['challonge']['id']
    entrant_name = db_entrant['name']
    db_entrant['active'] = False
    entrant_index = find_index_in_bracket(db_bracket, 'entrants', 'id', db_entrant['id'])
    db_bracket['entrants'][entrant_index] = db_entrant

    # Update entrant in database
    try:
        await set_bracket(db_guild['guild_id'], bracket_title, db_bracket)
    except:
        print("Failed to DQ entrant in database.")
        return False
    # Disqualify entrant on challonge
    try:
        challonge.participants.destroy(challonge_id, db_entrant['challonge_id'])
    except Exception as e:
        printlog(f"Failed to DQ entrant ['name'='{entrant_name}'] from bracket ['title'='{bracket_title}']", e)
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
        if db_match['player1']['id'] == db_entrant['id']:
            winner_emote = '2️⃣'
            break
        elif db_match['player2']['id'] == db_entrant['id']:
            winner_emote = '1️⃣'
            break
    if winner_emote:
        # Report match
        match_message = await channel.fetch_message(db_match['id'])
        await _match.report_match(match_message, db_guild, db_bracket, db_match, winner_emote, is_dq=True)
    return True

##################
## BUTTON VIEWS ##
##################

pages = {}

class registration_buttons_view(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Join Bracket", style=discord.ButtonStyle.green, custom_id="join_bracket")
    async def join(self: discord.ui.View, interaction: discord.Interaction, button: discord.ui.Button):
        print(interaction.message.id)
        await add_entrant(interaction)

    @discord.ui.button(label="Leave Bracket", style=discord.ButtonStyle.red, custom_id="leave_bracket")
    async def leave(self: discord.ui.View, interaction: discord.Interaction, button: discord.ui.Button):
        print(interaction.message.id)
        await remove_entrant(interaction)

######################
## HELPER FUNCTIONS ##
######################

async def retrieve_valid_bracket(channel: TextChannel, db_guild: dict, bracket_title: str, 
                     send: bool=True, completed: bool=False, active: bool=False):
    """"
    Checks if there is a valid bracket
    """
    # Get bracket from database
    if len(bracket_title.strip()) > 0:
        # Check if bracket exists
        db_bracket = find_bracket(db_guild, bracket_title)
        if not db_bracket:
            if send: 
                await channel.send(f"Bracket with name '{bracket_title}' does not exist.")
            return (None, None)
    else:
        if active: # Get active bracket, if exists
            db_bracket = find_active_bracket(db_guild)
            if not db_bracket:
                if send: 
                    await channel.send(f"There are currently no active brackets.")
                return (None, None)
        else: # Get most recently created bracket
            db_bracket = find_most_recent_bracket(db_guild, completed)
            if not db_bracket:
                if send: 
                    await channel.send(f"There are currently no open brackets.")
                return (None, None)
        bracket_title = db_bracket['title']
    return (db_bracket, bracket_title)

def find_index_in_bracket(db_bracket: dict, target_field: str, target_key: str, target_value):
    """
    Returns the index of a dictionary in a bracket list.
    """
    for i, dic in enumerate(db_bracket[target_field]):
        if dic[target_key] == target_value:
            return i
    return -1

async def set_bracket(guild_id: int, bracket_title: str, new_bracket: dict):
    """
    Sets a bracket in a guild to the specified document.
    """
    return await mdb.update_single_document(
        {'guild_id': guild_id, 'brackets.name': bracket_title, 'brackets.id': new_bracket['id']}, 
        {'$set': {f'brackets.$': new_bracket}
        },
        GUILDS)

async def add_to_bracket(guild_id: int, bracket_title: str, target_field: str, document: dict):
    """
    Pushes a document to a bracket subarray.
    """
    return await mdb.update_single_document(
        {'guild_id': guild_id, 'brackets.title': bracket_title}, 
        {'$push': {f'brackets.$.{target_field}': document}},
        GUILDS)

async def remove_from_bracket(guild_id: int, bracket_title: str, target_field: str, target_id: int):
    """
    Pulls a document from a bracket subarray.
    """
    return await mdb.update_single_document(
        {'guild_id': guild_id, 'brackets.title': bracket_title}, 
        {'$pull': {f'brackets.$.{target_field}': {'id': target_id}}},
        GUILDS)

async def delete_all_matches(channel: TextChannel, db_bracket: dict):
    """
    Deletes all matches in the specified bracket.
    """
    bracket_title = db_bracket['title']
    retval = True
    for match in db_bracket['matches']:
        match_id = match['id']
        try:
            await _match.delete_match(channel, db_bracket, match_id)
        except:
            print(f"Failed to delete match ['id'={match_id}] while deleting bracket ['title'={bracket_title}].")
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
    else:
        current_time = datetime.now()
        if text_match1:
            time = datetime.strptime(f'{date.today()} {text_match1.group()}', '%Y-%m-%d %I:%M %p')
        elif text_match2:
            time = datetime.strptime(f'{date.today()} {text_match2.group()}', '%Y-%m-%d %I %p')
        # Check if current time is before time on current date; If so, go to next day
        if current_time > time:
            time += timedelta(days=1)
    return time

#######################
## MESSAGE FUNCTIONS ##
#######################

async def edit_bracket_message(db_bracket: dict, channel: TextChannel):
    """
    Edits bracket embed message in a channel.
    """
    bracket_title = db_bracket['title']
    bracket_message: Message = await channel.fetch_message(db_bracket['id'])
    embed = bracket_message.embeds[0]
    embed = update_embed_entrants(db_bracket, embed)
    if db_bracket['completed']:
        status = "Completed 🏁"
    elif db_bracket['open']:
        status = "🚨 Open for Registration 🚨"
    else:
        status = "Started 🟩"
    embed.description = f"Status: {status}"
    if not db_bracket['open']:
        image_embed = None
        try:
            image_embed = create_bracket_image(db_bracket, embed)
        except Exception as e:
            printlog(f"Failed to create image for bracket ['title'='{bracket_title}'].")
            print(e)
        if not image_embed:
            printlog(f"Error when creating image for bracket ['title'='{bracket_title}'].")
        else:
            embed = image_embed
    if db_bracket['completed']:
        time_str = db_bracket['completed'].strftime("%A, %B %d, %Y %#I:%M %p %Z") # time w/o ms
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
    bracket_title = db_bracket['title']
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
            printlog(f"Failed to create image for bracket ['title'='{bracket_title}'].")
            return False
    else:
        printlog(f"Failed to create image for bracket ['title'='{bracket_title}'].")
        return False

def create_bracket_embed(db_bracket: dict):
    """
    Creates embed object to include in bracket message.
    """
    author_name = db_bracket['author']['username']
    bracket_title = db_bracket['title']
    challonge_url = db_bracket['challonge']['url']
    time = db_bracket['starttime']
    
    # Check the status
    if db_bracket['completed']:
        status = "Completed 🏁"
    elif db_bracket['open']:
        status = "🚨 Open for Registration 🚨"
    else:
        status = "Started 🟩"
    embed = Embed(title=f'🥊  {bracket_title}', description=f"Status: {status}", color=0x6A0DAD)
    embed.set_author(name="beta-bot | GitHub 🤖", url="https://github.com/fborja44/beta-bot", icon_url=ICON)
    time_str = time.strftime("%A, %B %d, %Y %#I:%M %p %Z") # time w/o ms
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
    bracket_title = db_bracket['title']
    challonge_url = db_bracket['challonge']['url']
    jump_url = db_bracket['jump_url']
    embed = Embed(title='🏆  Final Results', color=0xFAD25A)
    embed.set_author(name=bracket_title, url=jump_url, icon_url=ICON)
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
    time_str = db_bracket['completed'].strftime("%A, %B %d, %Y %#I:%M %p %Z") # time w/o ms
    embed.set_footer(text=f'Completed: {time_str}')
    return embed

#######################
## TESTING FUNCTIONS ##
#######################

async def create_test_bracket(interaction: Interaction):
    """
    Testing function. Creates a test bracket and adds two entrants.
    """
    printlog("Creating test bracket...")
    bracket_title = "Test Bracket"
    bracket_db , bracket_message , bracket_challonge = None, None, None
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Only allow guild admins to create a test bracket
    if not user.guild_permissions.administrator:
        return await user.channel.send(f"Only admins can create a test bracket.")

    # Delete previous test bracket if it exists
    try:
        db_bracket = find_bracket(db_guild, bracket_title)
        if db_bracket:
            await delete_bracket(interaction, bracket_title)
        # Call create_bracket
        db_bracket, bracket_message, bracket_challonge = await create_bracket(interaction, bracket_title)
        # Add first entrant
        try:
            member1 = guild.get_member_named('beta#3096')
            await add_entrant(interaction, db_bracket, member1)
        except:
            pass
        # Add second entrant
        try:
            member2 = guild.get_member_named("pika!#3722")
            await add_entrant(interaction, db_bracket, member2)
        except:
            pass
        # Add third entrant
        try:
            member3 = guild.get_member_named("Wooper#0478")
            await add_entrant(interaction, db_bracket, member3)
        except:
            pass
        # Add fourth entrant
        try:
            member4 = guild.get_member_named("WOOPBOT#4140")
            await add_entrant(interaction, db_bracket, member4)
        except:
            pass
        return True
    except Exception as e:
        await printlog("Failed to create test bracket.", channel)
        print_exception(e)
        await interaction.response.send_message(f"Something went wrong when creating the test bracket.", ephemeral=True)
        if bracket_message:
            await delete_bracket(interaction, bracket_title)
        return False