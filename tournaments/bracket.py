from cgi import print_exception
from datetime import datetime, timedelta, date, timezone
from discord import Embed, Guild, ForumChannel, Interaction, Message, Member, TextChannel, Thread
# from discord.ext import tasks
from dotenv import load_dotenv
from pprint import pprint
from traceback import print_exception
from tournaments import match as _match
from guilds import guild as _guild
from utils.color import GOLD, WOOP_PURPLE
from utils.common import BRACKETS, GUILDS, ICON, IMGUR_CLIENT_ID, IMGUR_URL, MAX_ENTRANTS
from utils.logger import printlog
from utils import mdb
import challonge
import discord
import os
import pytz
import re
import requests

os.environ['path'] += os.getenv('CAIRO_PATH')
from cairosvg import svg2png # SVG to PNG

# bracket.py
# User created brackets

load_dotenv()

os.environ['path'] += r';C:\Program Files\UniConvertor-2.0rc5\dlls'

MIN_ENTRANTS = 2
EASTERN_ZONE = pytz.timezone('US/Eastern')

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
    channel: ForumChannel | TextChannel = interaction.channel.parent if 'thread' in str(interaction.channel.type) else interaction.channel
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Check args
    # usage = 'Usage: `$bracket create <name> [time]`'

    # Check if in a valid tournament channel
    if channel.id not in db_guild['config']['tournament_channels']:
        if respond: await interaction.followup.send(f"Brackets must be created in a tournament channel.") # TODO: List guild's tournament channels.
        return False
    # TODO: Check if bot has thread permissions
    # Parse time; Default is 1 hour from current time
    try:
        parsed_time = parse_time(time) # TODO: needs testing for bad input
    except ValueError as e:
        print(e)
        if respond: await interaction.followup.send("Invalid input for time. ex. `10am` or `10:30pm`")
        return None, None, None
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
        return None, None, None
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
            'id': None,                                             # Initialized later
            'channel_id': channel.id,                               # TextChannel/Thread that the create command was called in
            'thread_id': None,                                      # Initialized later if created as a thread
            'title': bracket_title, 
            'tournament_type': bracket_challonge['tournament_type'],
            'jump_url': None,                                       # Initialized later
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
            'winner': None,
            'max_entrants': max_entrants,
            'matches': [],
            'created_at': datetime.now(tz=EASTERN_ZONE),
            'start_time': parsed_time, 
            'end_time': None, 
            'completed': False,
            'open': True,
            'num_rounds': None
        }
        
        embed = create_bracket_embed(new_bracket, interaction.user)
        # Send tournament message
        if str(channel.type) == 'forum':
            thread_title = f"🥊 {bracket_title} - {bracket_challonge['tournament_type'].title()} (0 of{max_entrants})"
            thread_content = "Open for Registration 🚨"
            bracket_thread, bracket_message = await channel.create_thread(name=thread_title, content=thread_content , embed=embed, view=registration_buttons_view())
            new_bracket['thread_id'] = bracket_thread.id
        # Send creation message in alert channels and original channel
        info_embed = create_info_embed(new_bracket)
        await interaction.channel.send(embed=info_embed)
        for channel_id in db_guild['config']['alert_channels']:
            alert_channel: TextChannel = guild.get_channel(channel_id)
            await alert_channel.send(embed=info_embed)

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
        # Delete thread if applicable
        try:
            if bracket_thread:
               await bracket_thread.delete()
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
    # Check if in valid channel
    if not await valid_bracket_channel(db_bracket, interaction, respond):
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
        print(f"Failed to delete message for bracket '{bracket_title}' ['id'='{db_bracket['id']}'].")
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
    # Delete thread if applicable
    if db_bracket['thread_id']:
        try:
            bracket_thread: Thread = guild.get_thread(db_bracket['thread_id'])
            await bracket_thread.delete()
        except:
            print(f"Failed to delete thread for bracket '{bracket_title}' ['thread_id'='{db_bracket['thread_id']}'].")
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
    # Check if in valid channel
    if not await valid_bracket_channel(db_bracket, interaction):
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
        db_bracket['start_time'] = parse_time(time)
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
        start_at=db_bracket['start_time'], 
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
    # Check if in valid channel
    if not await valid_bracket_channel(db_bracket, interaction):
        return False
    # Check if already started
    if not db_bracket['open']:
        await interaction.followup.send(f"'***{bracket_title}***' has already been started.", ephemeral=True)
        return False
    # Make sure there are sufficient number of entrants
    if len(db_bracket['entrants']) < MIN_ENTRANTS:
        await interaction.followup.send(f"Bracket must have at least {MIN_ENTRANTS} entrants before starting.", ephemeral=True)
        return False
    # Only allow one bracket to be started at a time in a guild
    active_bracket = find_active_bracket(db_guild)
    if active_bracket and active_bracket['id'] != db_bracket['id']:
        active_bracket_id = active_bracket['thread_id'] or active_bracket['channel_id'] or active_bracket['id']
        await interaction.followup.send(f"There may only be one active bracket per server.\nCurrent active bracket in: <#{active_bracket_id}>.", ephemeral=True)
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
    await channel.send(content=f"'***{bracket_title}***' has now started!") # Reply to original bracket message
    # Get each initial open matches
    matches = list(filter(lambda match: (match['state'] == 'open'), challonge_matches))
    for match in matches:
        try:
            await _match.create_match(channel, guild, db_bracket, match)
        except Exception as e:
            printlog(f"Failed to add match ['match_id'='{match['id']}'] to bracket ['title'='{bracket_title}']", e)
    # Update embed message
    await edit_bracket_message(db_bracket, channel)
    await interaction.followup.send(f"Successfully started bracket '***{bracket_title}***'.")
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
    # Check if in valid channel
    if not await valid_bracket_channel(db_bracket, interaction):
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
    completed_time = datetime.now(tz=EASTERN_ZONE)
    db_bracket, bracket_title = await retrieve_valid_bracket(interaction, db_guild, bracket_title, active=True)
    if not db_bracket:
        return False
    # Only allow author or guild admins to finalize bracket
    if user.id != db_bracket['author']['id'] and not user.guild_permissions.administrator:
        await interaction.followup.send(f"Only the author or server admins can finalize the bracket.", ephemeral=True)
        return False
    # Check if in valid channel
    if not await valid_bracket_channel(db_bracket, interaction):
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
    result_message = await channel.send(content=f"'***{bracket_title}***' has been finalized. Here are the results!", embed=embed) # Reply to original bracket message
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
    # Close thread if applicable
    if db_bracket['thread_id']:
        try:
            bracket_thread: Thread = guild.get_thread(db_bracket['thread_id'])
            await bracket_thread.edit(locked=True, pinned=False)
        except:
            print(f"Failed to edit thread for bracket '{bracket_title}' ['thread_id'='{db_bracket['thread_id']}'].")
    await interaction.followup.send("Succesfully finalized bracket '***{bracket_title}***.")
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
        # Update thread if applicable
        if db_bracket['thread_id'] is not None:
            bracket_thread: Thread = guild.get_thread(db_bracket['thread_id'])
            await bracket_thread.edit(name=f"🥊 {bracket_title} - {db_bracket['tournament_type'].title()} ({len(db_bracket['entrants'])} of {db_bracket['max_entrants']})")
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
        # Update thread if applicable
        if db_bracket['thread_id'] is not None:
            bracket_thread: Thread = guild.get_thread(db_bracket['thread_id'])
            await bracket_thread.edit(name=f"🥊 {bracket_title} - {db_bracket['tournament_type'].title()} ({len(db_bracket['entrants'])} of {db_bracket['max_entrants']})")
    else:
        print(f"Failed to remove entrant ['name'='{db_entrant['name']}']from bracket [id='{bracket_id}'].")
        if respond: await interaction.followup.send(f"Something went wrong when trying to leave '***{bracket_title}***'.", ephemeral=True)
        return False
    if respond: await interaction.followup.send(f"Successfully removed from '***{bracket_title}***'.", ephemeral=True)
    return True

async def disqualify_entrant_main(interaction: Interaction, entrant_name: str, bracket_title: str=""):
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
    # Check if in valid channel
    if not await valid_bracket_channel(db_bracket, interaction):
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

async def valid_bracket_channel(db_bracket: dict, interaction: Interaction, respond: bool=True):
    """
    Checks if performing command in valid channel.
    i.e. Channel that bracket was created in or the bracket thread if applicable.
    """
    bracket_title = db_bracket['title']
    channel_id: TextChannel | ForumChannel | Thread = interaction.channel_id
    if db_bracket['thread_id'] is not None:
        if db_bracket['thread_id'] != channel_id:
            if respond: await interaction.followup.send(f"Command only available in the tournament thread for '***{bracket_title}***': <#{db_bracket['thread_id']}>.", ephemeral=True)
            return False
    elif db_bracket['id'] != channel_id:
        if respond: await interaction.followup.send(f"Command only available in the tournament channel that '***{bracket_title}***' was created in: <#{db_bracket['thread_id']}>.", ephemeral=True)        
        return False
    return True

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
        # Check if in thread
        if 'thread' in str(interaction.channel.type):
            db_bracket = find_bracket_by_id(db_guild, interaction.channel_id)
            if not db_bracket:
                if send: 
                    await interaction.followup.send(f"This thread is not for a bracket.", ephemeral=True)
                return (None, None)
        elif active: # Get active bracket, if exists
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
    If the string is empty, returns the current time + 1 hour.
    """
    if len(string.strip()) == 0:
        return datetime.now(tz=EASTERN_ZONE) + timedelta(hours=1)
    text_match1 = time_re_long.search(string.strip()) # Check for long time
    text_match2 = time_re_short.search(string.strip()) # Check for short time
    if not text_match1 and not text_match2:
        raise ValueError(f"Received invalid input '{string}' for time string.")
    else:
        current_time = datetime.now(tz=EASTERN_ZONE)
        if text_match1:
            try:
                time = datetime.strptime(f'{date.today()} {text_match1.group()}', '%Y-%m-%d %I:%M %p') # w/ space
            except ValueError:
                time = datetime.strptime(f'{date.today()} {text_match1.group()}', '%Y-%m-%d %I:%M%p') # no space
        elif text_match2:
            try:
                time = datetime.strptime(f'{date.today()} {text_match2.group()}', '%Y-%m-%d %I %p') # w/ space
            except ValueError:
                time = datetime.strptime(f'{date.today()} {text_match2.group()}', '%Y-%m-%d %I%p') # no space
        # Check if current time is before time on current date; If so, go to next day
        time = EASTERN_ZONE.localize(time) # set time to offset-aware datetime
        if current_time > time:
            time += timedelta(days=1)
    return time

# TODO: Check-in period to start bracket
# def create_bracket_start_task(time: datetime):
#     @tasks.loop(time=time)
#     async def start_registration_phase():

#######################
## MESSAGE FUNCTIONS ##
#######################

def create_bracket_embed(db_bracket: dict, author: Member):
    """
    Creates embed object to include in bracket message.
    """
    bracket_title = db_bracket['title']
    challonge_url = db_bracket['challonge']['url']
    time = db_bracket['start_time']
    
    # Check the status
    if db_bracket['completed']:
        status = "Completed 🏁"
    elif db_bracket['open']:
        status = "Open for Registration! 🚨"
    else:
        status = "Started 🟩"
    # Main embed
    embed = Embed(title=f'🥊  {bracket_title}', description=f"Status: {status}" if not db_bracket['thread_id'] else "", color=WOOP_PURPLE)
    # Author field
    embed.set_author(name="beta-bot | GitHub 🤖", url="https://github.com/fborja44/beta-bot", icon_url=ICON)
    # Tournament description fields
    embed.add_field(name='Tournament Type', value=db_bracket['tournament_type'].title())
    time_str = time.strftime("%A, %B %d, %Y %#I:%M %p %Z") # time w/o ms
    embed.add_field(name='Starting At', value=time_str)
    # Entrants list
    if db_bracket['max_entrants']:
        embed.add_field(name='Entrants (0)', value="> *None*", inline=False)
    else:
        max_entrants = db_bracket['max_entrants']
        embed.add_field(name=f'Entrants (0/{max_entrants})', value="> *None*", inline=False)
    embed = update_embed_entrants(db_bracket, embed)
    # Bracket link
    embed.add_field(name=f'Bracket Link', value=challonge_url, inline=False)
    # Set footer
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
        status = " Completed 🏁"
    elif db_bracket['open']:
        status = "Open for Registration 🚨"
    else:
        await bracket_message.edit(view=None)
        status = "Started 🟩"
    if not db_bracket['thread_id']:
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
        embed.add_field(name=f'Completed At', value=f"{time_str}\nUse `/bracket results`", inline=False)
    if db_bracket['thread_id']:
        content = status
    else:
        content = ""
    await bracket_message.edit(content=content, embed=embed)

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
    # jump_url = db_bracket['jump_url']
    # Main embed
    embed = Embed(title=f"🏆  Final Results for '{bracket_title}'", color=GOLD)
    # Author field
    embed.set_author(name="beta-bot | GitHub 🤖", url="https://github.com/fborja44/beta-bot", icon_url=ICON)
    results_content = ""
    entrants.sort(key=(lambda entrant: entrant['participant']['final_rank']))
    # List placements
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
    # Other info fields
    embed.add_field(name=f'Bracket Link', value=challonge_url, inline=False)
    time_str = db_bracket['completed'].strftime("%A, %B %d, %Y %#I:%M %p %Z") # time w/o ms
    embed.set_footer(text=f'Completed: {time_str}')
    return embed

def create_info_embed(db_bracket: dict):
    author_name = db_bracket['author']['username']
    thread_id = db_bracket['thread_id']
    tournament_channel_id = db_bracket['channel_id']
    bracket_link = f'<#{thread_id}>' if thread_id else f'<#{tournament_channel_id}>'
    time = db_bracket['start_time']
    embed = Embed(title=f'💥 {author_name} has created a new bracket!', color=WOOP_PURPLE)
    embed.set_author(name="beta-bot | GitHub 🤖", url="https://github.com/fborja44/beta-bot", icon_url=ICON)
    # Tournament description fields
    embed.add_field(name=db_bracket['title'], value=f"Register at: {bracket_link}", inline=False)
    embed.add_field(name='Tournament Type', value=db_bracket['tournament_type'].title())
    time_str = time.strftime("%A, %B %d, %Y %#I:%M %p %Z") # time w/o ms
    embed.add_field(name='Starting At', value=time_str)
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