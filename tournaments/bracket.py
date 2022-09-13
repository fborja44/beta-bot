from cgi import print_exception
from utils.common import BRACKETS, GUILDS, ICON, IMGUR_CLIENT_ID, IMGUR_URL, MAX_ENTRANTS
from datetime import datetime, timedelta, date
from discord import Embed, Guild, Interaction, Message, Member, TextChannel
from dotenv import load_dotenv
from utils.logger import printlog, printlog_msg
from pprint import pprint
from traceback import print_exception
import challonge
import discord
import guilds.guild as _guild
import tournaments.match as _match
import utils.mdb as mdb
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

async def create_bracket(interaction: Interaction, bracket_title: str, time: str="", single_elim: bool = False, max_entrants: int = 24, respond: bool = True):
    """
    Creates a new bracket and adds it to the guild.
    """
    guild: Guild = interaction.guild
    channel: TextChannel = interaction.channel
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Check args
    # usage = 'Usage: `$bracket create <name> [time]`'

    # Parse time; Default is 1 hour from current time
    parsed_time = parse_time(time) # TODO: needs testing for bad input

    # Max character length == 60
    if len(bracket_title.strip()) == 0:
        if respond: await interaction.followup.send(f"Bracket title cannot be empty.")
        return None, None, None
    if len(bracket_title.strip()) > 60:
        if respond: await interaction.followup.send(f"Bracket title can be no longer than 60 characters.")
        return None, None, None
    # Max entrants limits
    if max_entrants is not None and (max_entrants < 4 or max_entrants > MAX_ENTRANTS):
        if respond: await interaction.followup.send(f"`max_entrants` must be between 4 and {MAX_ENTRANTS}.")
        return False
    # Check if bracket already exists
    db_bracket = find_bracket(db_guild, bracket_title)
    if db_bracket:
        if respond: await interaction.followup.send(f"Bracket with title '{bracket_title}' already exists.")
        return None, None, None
    try:
        # Create challonge bracket
        bracket_challonge = challonge.tournaments.create(
            name=bracket_title, 
            url=None, 
            tournament_type="single elimination" if single_elim else "double elimination",
            start_at=parsed_time,
            signup_cap=max_entrants,
            show_rounds=True, 
            private=True, 
            quick_advance=True, 
            open_signup=False
        )

        new_bracket = {
            'id': None, # Initialized later
            'channel_id': channel.id,
            'title': bracket_title, 
            'tournament_type': bracket_challonge['tournament_type'],
            'jump_url': None, # Initialized later
            'result_url': None,
            'author': {
                'username': user.name, 
                'id': user.id,
                'avatar_url': user.display_avatar.url
                 },
            'challonge': {
                'id': bracket_challonge['id'], 
                'url': bracket_challonge['full_challonge_url']
                 },
            'entrants': [], 
            'max_entrants': max_entrants,
            'matches': [],
            'created_at': datetime.now(),
            'starttime': parsed_time, 
            'endtime': None, 
            'completed': False,
            'open': True,
            'num_rounds': None
        }
        
        # Send embed message
        embed = create_bracket_embed(new_bracket, interaction.user)
        bracket_message: Message = await channel.send(embed=embed, view=registration_buttons_view())

        # Add bracket to database
        new_bracket['id'] = bracket_message.id
        new_bracket['jump_url'] = bracket_message.jump_url
        result = await _guild.push_to_guild(guild, BRACKETS, new_bracket)
        print(f"User '{user.name}' [id={user.id}] created new bracket '{bracket_title}'.")
        if respond: await interaction.followup.send(f"Successfully created bracket '***{bracket_title}***'.")
        return (new_bracket, bracket_message, bracket_challonge)
    except Exception as e:
        printlog("Something went wrong when creating the bracket.", e)
        if respond: await interaction.followup.send(f"Something went wrong when creating bracket '***{bracket_title}***'.")
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

async def delete_bracket(interaction: Interaction, bracket_title: str, respond: bool=True):
    """
    Deletes the specified bracket (if it exists).
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    # Fetch bracket
    # usage = 'Usage: `$bracket delete [title]`'
    db_bracket, bracket_title = await retrieve_valid_bracket(interaction, db_guild, bracket_title)
    retval = True
    if not db_bracket:
        return False
    # Only allow author or guild admins to delete bracket
    if user != db_bracket['author']['id'] and not user.guild_permissions.administrator:
        if respond: await interaction.followup.send(f"Only the author or server admins can delete brackets.", ephemeral=True)
        return False
    # Check if in channel bracket was created in
    if db_bracket['channel_id'] != channel.id:
        if respond: await interaction.followup.send(f"Must be in the channel that '***{bracket_title}***' was created in: <#{db_bracket['channel_id']}>.", ephemeral=True)
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
        if respond: await interaction.followup.send(f"Failed to delete bracket '***{bracket_title}***'.", ephemeral=True)
        retval = False
    if respond: await interaction.followup.send(f"Successfully deleted bracket '***{bracket_title}***'.")
    return retval

async def update_bracket(interaction: Interaction, bracket_title: str , new_bracket_title: str | None=None, time: str | None=None, single_elim: bool | None=None, max_entrants: int | None=None):
    """
    Updates the specified bracket (if it exists).
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    # Fetch bracket
    # usage = 'Usage: `$bracket update [name]`'
    db_bracket, bracket_title = await retrieve_valid_bracket(interaction, db_guild, bracket_title)
    if not db_bracket: 
        return False
    # Only allow author or guild admins to update bracket
    if user.id != db_bracket['author']['id'] and not user.guild_permissions.administrator:
        await interaction.followup.send(f"Only the author or server admins can update the bracket.", ephemeral=True)
        return False
    # Check if in channel bracket was created in
    if db_bracket['channel_id'] != channel.id:
        await interaction.followup.send(f"Must be in the channel that '***{bracket_title}***' was created in: <#{db_bracket['channel_id']}>.", ephemeral=True)
        return False
    # Only allow updating if the bracket has not been started or completed
    if not db_bracket['open'] or db_bracket['completed']:
        await interaction.followup.send(f"You may only update brackets in the registration phase.", ephemeral=True)
        return False
    # Check if updating info
    if not (new_bracket_title is not None or time is not None or single_elim is not None or max_entrants is not None):
        await interaction.followup.send(f"Must include at least one field to update.", ephemeral=True)
        return False
    # Updating bracket_title
    if new_bracket_title is not None:
        if len(new_bracket_title.strip()) == 0:
            await interaction.followup.send(f"Bracket title cannot be empty.")
            return None, None, None
        if len(new_bracket_title.strip()) > 60:
            await interaction.followup.send(f"Bracket title can be no longer than 60 characters.")
            return None, None, None
        db_bracket['title'] = new_bracket_title
    # Updating time
    if time is not None:
        db_bracket['starttime'] = parse_time(time)
    # Updating type
    if single_elim is not None:
        db_bracket['tournament_type'] = "single elimination" if single_elim else "double elimination"
    # Updating max_entrants
    if max_entrants is not None:
        if (max_entrants < 4 or max_entrants > MAX_ENTRANTS):
            await interaction.followup.send(f"`max_entrants` must be between 4 and {MAX_ENTRANTS}.")
            return False
        db_bracket['max_entrants'] = max_entrants
    # Update the bracket on challonge
    challonge.tournaments.update(db_bracket['challonge']['id'], 
        name=db_bracket['title'], 
        tournament_type=db_bracket['tournament_type'],
        start_at=db_bracket['starttime'], 
        signup_cap=max_entrants,
    )
    # Update the bracket in database
    await set_bracket(guild.id, bracket_title, db_bracket)
    # Update bracket embed
    bracket_message: Message = await channel.fetch_message(db_bracket['id'])
    author: Member = await guild.fetch_member(db_bracket['author']['id']) or interaction.user
    new_bracket_embed = create_bracket_embed(db_bracket, author)
    await bracket_message.edit(embed=new_bracket_embed)
    await interaction.followup.send(f"Successfully updated bracket.")
    return True

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
    db_bracket, bracket_title = await retrieve_valid_bracket(interaction, db_guild, bracket_title)
    if not db_bracket: 
        return False
    # Only allow author or guild admins to start bracket
    if user.id != db_bracket['author']['id'] and not user.guild_permissions.administrator:
        await interaction.followup.send(f"Only the author or server admins can start the bracket.", ephemeral=True)
        return False
    # Check if in channel bracket was created in
    if db_bracket['channel_id'] != channel.id:
        await interaction.followup.send(f"Must be in the channel that '***{bracket_title}***' was created in: <#{db_bracket['channel_id']}>.", ephemeral=True)
        return False
    # Check if already started
    if not db_bracket['open']:
        await interaction.followup.send(f"'***{bracket_title}***' has already been started.", ephemeral=True)
        return False
    # Make sure there are sufficient number of entrants
    if len(db_bracket['entrants']) < 2:
        await interaction.followup.send(f"Bracket must have at least 2 entrants before starting.", ephemeral=True)
        return False
    # Only allow one bracket to be started at a time in a guild
    active_bracket = find_active_bracket(db_guild)
    if active_bracket and active_bracket['id'] == db_bracket['id']:
        await interaction.followup.send(f"There may only be one active bracket per server.", ephemeral=True)
        return False
    # Start bracket on challonge
    try:
        challonge.tournaments.start(db_bracket['challonge']['id'], include_participants=1, include_matches=1)
    except Exception as e:
        printlog(f"Failed to start bracket ['title'='{bracket_title}'] on challonge.")
        await interaction.followup.send(f"Something went wrong when starting '***{bracket_title}***' on challonge.")
        return False
    printlog(f"User ['name'='{user.name}'] started bracket '{bracket_title}' [id={db_bracket['id']}].")
    # Challonge API changed? Retrive matches.
    challonge_matches = challonge.matches.index(db_bracket['challonge']['id'])
    # Get total number of rounds
    max_round = 0
    for match in challonge_matches:
       round = match['round']
       if round > max_round:
           max_round = round
    # Set bracket to closed in database and set total number of rounds
    db_bracket.update({'open': False, 'num_rounds': max_round })
    await set_bracket(guild.id, bracket_title, db_bracket)
    print(f"User ['name'='{user.name}'] started bracket ['title'='{bracket_title}'].")
    # Send start message
    # bracket_message = await channel.fetch_message(db_bracket['id'])
    await interaction.followup.send(content=f"'***{bracket_title}***' has now started!") # Reply to original bracket message
    # Get each initial open matches
    matches = list(filter(lambda match: (match['state'] == 'open'), challonge_matches))
    for match in matches:
        try:
            await _match.create_match(channel, guild, db_bracket, match)
        except Exception as e:
            printlog(f"Failed to add match ['match_id'='{match['id']}'] to bracket ['title'='{bracket_title}']", e)
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
    db_bracket, bracket_title = await retrieve_valid_bracket(interaction, db_guild, bracket_title, active=True)
    if not db_bracket:
        return False
    bracket_message_id = db_bracket['id']
    challonge_id = db_bracket['challonge']['id']
    # Check if in channel bracket was created in
    if db_bracket['channel_id'] != channel.id:
        await interaction.followup.send(f"Must be in the channel that '***{bracket_title}***' was created in: <#{db_bracket['channel_id']}>.", ephemeral=True)
        return False
    # Only allow author or guild admins to reset bracket
    if user.id != db_bracket['author']['id'] and not user.guild_permissions.administrator:
        await interaction.followup.send(f"Only the author or server admins can reset the bracket.", ephemeral=True)
        return False
    # Check if already completed
    if db_bracket['completed']: 
        await interaction.followup.send(f"Cannot reset a finalized bracket.", ephemeral=True)
        return False
    # Delete every match message and document associated with the bracket
    await delete_all_matches(channel, db_bracket)
    # Reset bracket on challonge
    try:
        challonge.tournaments.reset(challonge_id)
    except Exception as e:
        printlog(f"Something went wrong when resetting bracket ['title'='{bracket_title}'] on challonge.", e)
    # Set open to true and reset number of rounds
    db_bracket.update({'open': True, 'num_rounds': None, 'matches': []})
    await set_bracket(guild.id, bracket_title, db_bracket)
    print(f"User ['name'='{user.name}'] reset bracket ['title'='{bracket_title}'].")
    # Reset bracket message
    bracket_message = await channel.fetch_message(bracket_message_id)
    author: Member = await guild.fetch_member(db_bracket['author']['id']) or interaction.user
    new_bracket_embed = create_bracket_embed(db_bracket, author)
    await bracket_message.edit(embed=new_bracket_embed, view=registration_buttons_view())
    await interaction.followup.send(f"Successfully reset bracket '***{bracket_title}***'.")
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
    db_bracket, bracket_title = await retrieve_valid_bracket(interaction, db_guild, bracket_title, active=True)
    if not db_bracket:
        return False
    # Only allow author or guild admins to finalize bracket
    if user.id != db_bracket['author']['id'] and not user.guild_permissions.administrator:
        await interaction.followup.send(f"Only the author or server admins can finalize the bracket.", ephemeral=True)
        return False
    # Check if in channel bracket was created in
    if db_bracket['channel_id'] != channel.id:
        await interaction.followup.send(f"Must be in the channel that '***{bracket_title}***' was created in: <#{db_bracket['channel_id']}>.", ephemeral=True)
        return False
    # Check if already finalized
    if db_bracket['completed']:
        await interaction.followup.send(f"'***{bracket_title}***' has already been finalized.", ephemeral=True)
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
    db_bracket['completed'] = completed_time # update completed time
    embed = create_results_embed(db_bracket, final_bracket['participants'])
    result_message = await interaction.followup.send(content=f"'***{bracket_title}***' has been finalized. Here are the results!", embed=embed) # Reply to original bracket message
    # Set bracket to completed in database
    try: 
        db_bracket.update({'result_url': result_message.jump_url}) # update result jump url
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
    guild: Guild = interaction.guild
    db_guild = await _guild.find_guild(guild.id)
    # Fetch bracket
    # usage = 'Usage: `$bracket results <title>`'
    db_bracket, bracket_title = await retrieve_valid_bracket(interaction, db_guild, bracket_title, completed=True)
    challonge_id = db_bracket['challonge']['id']
    if not db_bracket:
        return False
    # Check if bracket is completed
    if not db_bracket['completed']:
        await interaction.followup.send(f"'***{bracket_title}***' has not yet been finalized.", ephemeral=True)
        return False
    # Retrive challonge bracket information
    try: 
        final_bracket = challonge.tournaments.show(challonge_id, include_participants=1, include_matches=1)
    except:
        print(f"Could not find bracket on challonge ['challonge_id'='{challonge_id}'].")
        return False
    # Create results message
    embed = create_results_embed(db_bracket, final_bracket['participants'])
    await interaction.followup.send(embed=embed) # Reply to original bracket message
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

async def add_entrant(interaction: Interaction, db_bracket: dict=None, member: Member=None, respond: bool=True):
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
        if respond: await interaction.followup.send(f"'***{bracket_title}***' is not open for registration.", ephemeral=True)
        return False 
    bracket_title = db_bracket['title']
    entrant_ids = [] # list of entrant names
    for entrant in db_bracket['entrants']:
        entrant_ids.append(entrant['id'])
    challonge_id = db_bracket['challonge']['id']
    # Check if already in entrants list
    if user.id in entrant_ids:
        # printlog(f"User ['name'='{user.name}']' is already registered as an entrant in bracket ['title'='{bracket_title}'].")
        if respond: await interaction.followup.send(f"You have already joined '***{bracket_title}***'.", ephemeral=True)
        return False
    # Check if bracket is at capacity
    if db_bracket['max_entrants'] and db_bracket['max_entrants'] == len(db_bracket['entrants']):
        if respond: await interaction.followup.send(f"Unable to join '***{bracket_title}***'. Tournament has reached maximum entrants.")
        return False
    # Add user to challonge bracket
    try:
        response = challonge.participants.create(challonge_id, user.name)
    except Exception as e:
        printlog(f"Failed to add user ['name'='{user.name}'] to challonge bracket. User may already exist.", e)
        if respond: await interaction.followup.send(f"Something went wrong when trying to join '***{bracket_title}***'.", ephemeral=True)
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
        if respond: await interaction.followup.send(f"Something went wrong when trying to join '***{bracket_title}***'.", ephemeral=True)
        return False
    if updated_guild:
        print(f"Added entrant '{user.name}' ['id'='{user.id}'] to bracket ['title'='{bracket_title}'].")
        # Update message
        await edit_bracket_message(db_bracket, channel)
    else:
        print(f"Failed to add entrant '{user.name}' ['id'='{user.id}'] to bracket ['title'='{bracket_title}'].")
        if respond: await interaction.followup.send(f"Something went wrong when trying to join '***{bracket_title}***'.", ephemeral=True)
        return False
    if respond: await interaction.followup.send(f"Successfully joined '***{bracket_title}***'.", ephemeral=True)
    return True

async def remove_entrant(interaction: Interaction, db_bracket: dict=None, member: Member=None, respond: bool=True):
    """
    Destroys an entrant from a tournament.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    message: Message = interaction.message
    user: Member = member or interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Fetch bracket
    db_bracket = db_bracket or find_bracket_by_id(db_guild, message.id)
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
        if respond: await interaction.followup.send(f"You are not registered for '***{bracket_title}***'.", ephemeral=True)
        return False
    db_entrant = list(filter(lambda entrant: entrant['id'] == user.id, db_bracket['entrants']))[0]
    try:
        challonge.participants.destroy(challonge_id, db_entrant['challonge_id'])
    except Exception as e:
        printlog(f"Failed to remove user ['name'='{db_entrant['name']}'] from challonge bracket. User may not exist.", e)
        if respond: await interaction.followup.send(f"Something went wrong when trying to leave '***{bracket_title}***'.", ephemeral=True)
        return False
    # Remove user from entrants list
    try:
        updated_guild = await remove_from_bracket(channel.guild.id, bracket_title, 'entrants', db_entrant['id'])
        db_bracket['entrants'] = list(filter(lambda entrant: entrant['id'] != user.id, db_bracket['entrants']))
    except:
        print(f"Failed to remove user '{db_entrant['name']}' from bracket ['title'='{bracket_title}'] entrants.")
        if respond: await interaction.followup.send(f"Something went wrong when trying to leave '***{bracket_title}***'.", ephemeral=True)
        return False
    if updated_guild:
        print(f"Removed entrant ['name'='{db_entrant['name']}']from bracket [id='{bracket_id}'].")
        # Update message
        await edit_bracket_message(db_bracket, channel)
    else:
        print(f"Failed to remove entrant ['name'='{db_entrant['name']}']from bracket [id='{bracket_id}'].")
        if respond: await interaction.followup.send(f"Something went wrong when trying to leave '***{bracket_title}***'.", ephemeral=True)
        return False
    if respond: await interaction.followup.send(f"Successfully removed from '***{bracket_title}***'.", ephemeral=True)
    return True

async def disqualify_entrant_main(interaction: Interaction, entrant_name: str, bracket_title: str):
    """
    Destroys an entrant from a tournament or DQs them if the tournament has already started from a command.
    Main function.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # usage = 'Usage: `$bracket dq <entrant name>`. There must be an active bracket, or must be in a reply to a bracket message.'
    # Retrieve bracket
    db_bracket, bracket_title = await retrieve_valid_bracket(interaction, db_guild, bracket_title, active=True)
    if not db_bracket:
        return False
    # Only allow author, guild admins, or self to dq a user
    if user.id != db_bracket['author']['id'] and not user.guild_permissions.administrator and user.name != entrant_name:
        await interaction.followup.send(f"Only the author or server admins can disqualify/remove entrants from brackets.", ephemeral=True)
        return False
    bracket_title = db_bracket['title']
    # Check if entrant exists
    db_entrant = None
    for elem in db_bracket['entrants']:
        if elem['name'].lower() == entrant_name.lower():
            db_entrant = elem
    if not db_entrant:
        printlog(f"User ['name'='{entrant_name}']' is not an entrant in bracket ['title'='{bracket_title}'].")
        await interaction.followup.send(f"There is no entrant named '{entrant_name}' in '***{bracket_title}***'.")
        return False
    elif not db_entrant['active']:
        await interaction.followup.send(f"Entrant '{entrant_name}' has already been disqualified from '***{bracket_title}***'.", ephemeral=True)
        return False

    # If bracket is still in registration phase, just remove from bracket
    if db_bracket['open']:
        entrant: Member = await interaction.guild.fetch_member(db_entrant['id'])
        await remove_entrant(interaction, db_bracket, entrant, respond=False)
        await interaction.followup.send(f"Successfully removed entrant from '***{bracket_title}***'.", ephemeral=True)
        print(f"User ['name'='{user.name}'] manually removed entrant.")
        return True

    # Call dq helper function
    await disqualify_entrant(channel, db_guild, db_bracket, db_entrant)
    await interaction.followup.send(f"'{db_entrant['name']}' was disqualified from '***{bracket_title}***'.")
    print(f"User ['name'='{user.name}'] manually disqualified entrant.")
    return True

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

class registration_buttons_view(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Join Bracket", style=discord.ButtonStyle.green, custom_id="join_bracket")
    async def join(self: discord.ui.View, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await add_entrant(interaction)

    @discord.ui.button(label="Leave Bracket", style=discord.ButtonStyle.red, custom_id="leave_bracket")
    async def leave(self: discord.ui.View, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await remove_entrant(interaction)

    @discord.ui.button(label="Start Bracket", style=discord.ButtonStyle.blurple, custom_id="start_bracket")
    async def start(self: discord.ui.View, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        db_guild = await _guild.find_guild(interaction.guild.id)
        db_bracket = find_bracket_by_id(db_guild, interaction.message.id)
        bracket_title = db_bracket['title']
        await start_bracket(interaction, bracket_title)

######################
## HELPER FUNCTIONS ##
######################

async def retrieve_valid_bracket(interaction: Interaction, db_guild: dict, bracket_title: str, 
                     send: bool=True, completed: bool=False, active: bool=False):
    """"
    Checks if there is a valid bracket.
    By default, finds bracket by bracket title.
    Otherwise, finds the current active bracket or most recent bracket (completed or not completed).
    """
    # Get bracket from database
    if len(bracket_title.strip()) > 0:
        # Check if bracket exists
        db_bracket = find_bracket(db_guild, bracket_title)
        if not db_bracket:
            if send: 
                await interaction.followup.send(f"Bracket with name '{bracket_title}' does not exist.", ephemeral=True)
            return (None, None)
    else:
        if active: # Get active bracket, if exists
            db_bracket = find_active_bracket(db_guild)
            if not db_bracket:
                if send: 
                    await interaction.followup.send(f"There are currently no active brackets.", ephemeral=True)
                return (None, None)
        else: # Get most recently created bracket
            db_bracket = find_most_recent_bracket(db_guild, completed)
            if not db_bracket:
                if send: 
                    await interaction.followup.send(f"There are currently no open brackets.", ephemeral=True)
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
        {'guild_id': guild_id, 'brackets.title': bracket_title, 'brackets.id': new_bracket['id']}, 
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

def create_bracket_embed(db_bracket: dict, author: Member):
    """
    Creates embed object to include in bracket message.
    """
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
    embed.add_field(name='Tournament Type', value=db_bracket['tournament_type'].title(), inline=False)
    time_str = time.strftime("%A, %B %d, %Y %#I:%M %p %Z") # time w/o ms
    embed.add_field(name='Starting At', value=time_str, inline=False)
    # Entrants list
    if db_bracket['max_entrants']:
        embed.add_field(name='Entrants (0)', value="> *None*", inline=False)
    else:
        max_entrants = db_bracket['max_entrants']
        embed.add_field(name=f'Entrants (0/{max_entrants})', value="> *None*", inline=False)
    embed = update_embed_entrants(db_bracket, embed)
    embed.add_field(name=f'Bracket Link', value=challonge_url, inline=False)
    embed.set_footer(text=f'Created by {author.display_name} | {author.name}#{author.discriminator}.', icon_url=db_bracket['author']['avatar_url'])
    return embed

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
        await bracket_message.edit(view=None)
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
        embed.add_field(name=f'Completed At', value=f"{time_str}", inline=False)
        embed.set_author(name="Click Here For Results", url=db_bracket['result_url'], icon_url=ICON)
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
    max_entrants = db_bracket['max_entrants']
    name = f'Entrants ({len(entrants)}/{max_entrants})' if max_entrants else f'Entrants ({len(entrants)})'
    embed.set_field_at(2, name=name, value=entrants_content, inline=False)
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
        # print("svg_url: ", svg_url)
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

async def create_test_bracket(interaction: Interaction, num_entrants: int = 4):
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
        return await interaction.followup.send(f"Only admins can create a test bracket.")

    # Delete previous test bracket if it exists
    try:
        db_bracket = find_bracket(db_guild, bracket_title)
        if db_bracket:
            await delete_bracket(interaction, bracket_title, respond=False)
        # Call create_bracket
        db_bracket, bracket_message, bracket_challonge = await create_bracket(interaction, bracket_title, respond=False)

        members = [guild.get_member_named('beta#3096'), guild.get_member_named("pika!#3722"), guild.get_member_named("Wooper#0478"), guild.get_member_named("WOOPBOT#4140")]
        for i in range(num_entrants):
            try:
                await add_entrant(interaction, db_bracket, members[i], respond=False)
            except:
                pass
        await interaction.followup.send(f"Finished generating Test Bracket and entrants.")
        return True
    except Exception as e:
        printlog("Failed to create test bracket.", channel)
        print_exception(e)
        await interaction.followup.send(f"Something went wrong when generating the test bracket.", ephemeral=True)
        if bracket_message:
            await delete_bracket(interaction, bracket_title, respond=False)
        return False