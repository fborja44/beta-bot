from cgi import print_exception
from datetime import datetime, timedelta, date, timezone
from discord import Client, Embed, Guild, ForumChannel, Interaction, Message, Member, TextChannel, Thread
# from discord.ext import tasks
from dotenv import load_dotenv
from pprint import pprint
from traceback import print_exception
from tournaments import match as _match, participant as _participant
from guilds import channel as _channel, guild as _guild
from utils.color import GOLD, WOOP_PURPLE
from utils.common import TOURNAMENTS, GUILDS, ICON, IMGUR_CLIENT_ID, IMGUR_URL, MAX_ENTRANTS
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

# tournament.py
# User created tournaments

load_dotenv()

os.environ['path'] += r';C:\Program Files\UniConvertor-2.0rc5\dlls'

MIN_ENTRANTS = 2
EASTERN_ZONE = pytz.timezone('US/Eastern')

time_re_long = re.compile(r'([1-9]|0[1-9]|1[0-2]):[0-5][0-9]\s*([AaPp][Mm])$') # ex. 10:00 AM
time_re_short = re.compile(r'([1-9]|0[1-9]|1[0-2])\s*([AaPp][Mm])$')           # ex. 10 PM

def find_tournament(db_guild: dict, tournament_title: str):
    """
    Retrieves and returns a tournament document from the database (if it exists).
    """
    guild_tournaments = db_guild['tournaments']
    result = [tournament for tournament in guild_tournaments if tournament['title'] == tournament_title]
    if result:
        return result[0]
    return None

def find_tournament_by_id(db_guild: dict, tournament_id: int):
    """
    Retrieves and returns a tournament document from the database (if it exists).
    """
    result = [tournament for tournament in db_guild['tournaments'] if tournament['id'] == tournament_id]
    if result:
        return result[0]
    return None

def find_tournament_by_thread_id(db_guild: dict, thread_id: int):
    """
    Retrieves and returns a tournament document from the database (if it exists).
    """
    result = [tournament for tournament in db_guild['tournaments'] if tournament['thread_id'] == thread_id]
    if result:
        return result[0]
    return None

def find_active_tournament(db_guild: dict):
    """
    Returns the current active tournament in a guild.
    """
    try:
        return list(filter(lambda tournament: not tournament['open'] and not tournament['completed'], db_guild['tournaments']))[0]
    except:
        return None

def find_most_recent_tournament(db_guild: dict, completed: bool):
    """
    Returns the most recently created tournament in a guild that has not yet been completed
    """
    guild_tournaments = db_guild['tournaments']
    try:
        if completed:
            guild_tournaments = list(filter(lambda tournament: tournament['completed'] is not False, guild_tournaments))
            guild_tournaments.sort(key=lambda tournament: tournament['completed'], reverse=True)
            return list(filter(lambda tournament: tournament['completed'] is not False, guild_tournaments))[0]
        else:
            guild_tournaments.sort(key=lambda tournament: tournament['created_at'], reverse=True)
            return list(filter(lambda tournament: not tournament['completed'] , guild_tournaments))[0]
    except Exception as e:
        print(e)
        return None

def find_incomplete_tournaments(db_guild: dict):
    """
    Returns all tournaments that have not been completed.
    """
    guild_tournaments = db_guild['tournaments']
    try:
        guild_tournaments = list(filter(lambda tournament: not tournament['completed'], guild_tournaments))
        guild_tournaments.sort(key=lambda tournament: tournament['completed'], reverse=True)
        return guild_tournaments
    except Exception as e:
        print(e)
        return None

async def create_tournament(interaction: Interaction, tournament_title: str, time: str="", single_elim: bool = False, max_participants: int = 24, respond: bool = True):
    """
    Creates a new tournament and adds it to the guild.
    """
    guild: Guild = interaction.guild
    channel: ForumChannel | TextChannel = interaction.channel.parent if 'thread' in str(interaction.channel.type) else interaction.channel
    thread: Thread = interaction.channel if 'thread' in str(interaction.channel.type) else None
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Check args
    # usage = 'Usage: `$tournament create <name> [time]`'
    # Check if in a valid tournament channel/thread
    tournament_channel = None
    if 'thread' in str(interaction.channel.type):
        tournament_channel = _channel.find_tournament_channel_by_thread_id(db_guild, thread.id)
    else:
        tournament_channel = _channel.find_tournament_channel(db_guild, channel.id)
    if not tournament_channel:
        if respond: await interaction.followup.send(f"<#{thread.id or channel.id}> is not a valid tournament channel.") # TODO: List guild's tournament channels.
        return False
    # Check if bot has thread permissions
    bot_user = guild.get_member(interaction.client.user.id)
    bot_permissions = channel.permissions_for(bot_user)
    if not bot_permissions.create_private_threads or not bot_permissions.create_public_threads:
        if respond: await interaction.followup.send("Bot is missing permissions to post private/public threads.")
        return False
    # Parse time; Default is 1 hour from current time
    try:
        parsed_time = parse_time(time)
    except ValueError as e:
        print(e)
        if respond: await interaction.followup.send("Invalid input for time. ex. `10am` or `10:30pm`")
        return None, None, None
    # Max character length == 60
    if len(tournament_title.strip()) == 0:
        if respond: await interaction.followup.send(f"Tournament title cannot be empty.")
        return None, None, None
    if len(tournament_title.strip()) > 60:
        if respond: await interaction.followup.send(f"Tournament title can be no longer than 60 characters.")
        return None, None, None
    # Max participants limits
    if max_participants is not None and (max_participants < 4 or max_participants > MAX_ENTRANTS):
        if respond: await interaction.followup.send(f"`max_participants` must be between 4 and {MAX_ENTRANTS}.")
        return None, None, None
    # Check if tournament already exists
    db_tournament = find_tournament(db_guild, tournament_title)
    if db_tournament:
        if respond: await interaction.followup.send(f"Tournament with title '{tournament_title}' already exists.")
        return None, None, None
    try:
        # Create challonge tournament
        tournament_challonge = challonge.tournaments.create(
            name=tournament_title, 
            url=None, 
            tournament_type="single elimination" if single_elim else "double elimination",
            start_at=parsed_time,
            signup_cap=max_participants,
            show_rounds=True, 
            private=True, 
            quick_advance=True, 
            open_signup=False
        )
        new_tournament = {
            'id': None,                                             # Initialized later
            'channel_id': channel.id,                               # TextChannel/Thread that the create command was called in
            'thread_id': None,                                      # Initialized later if created as a thread
            'title': tournament_title, 
            'tournament_type': tournament_challonge['tournament_type'],
            'jump_url': None,                                       # Initialized later
            'result_url': None,
            'author': {
                'username': user.name, 
                'id': user.id,
                'avatar_url': user.display_avatar.url
                 },
            'challonge': {
                'id': tournament_challonge['id'], 
                'url': tournament_challonge['full_challonge_url']
                 },
            'participants': [], 
            'winner': None,
            'max_participants': max_participants,
            'matches': [],
            'created_at': datetime.now(tz=EASTERN_ZONE),
            'start_time': parsed_time, 
            'end_time': None, 
            'completed': False,
            'open': True,
            'num_rounds': None
        }
        
        embed = create_tournament_embed(new_tournament, interaction.user)
        # Send tournament thread message
        thread_title = f"🥊 {tournament_title} - {tournament_challonge['tournament_type'].title()} (0 of {max_participants})"
        thread_content = "Open for Registration 🚨"
        tournament_thread, tournament_message = await channel.create_thread(name=thread_title, content=thread_content , embed=embed, view=registration_buttons_view())
        new_tournament['thread_id'] = tournament_thread.id
        # Send creation message in alert channels (including forum channel)
        info_embed = create_info_embed(new_tournament)
        if 'thread' in str(interaction.channel.type):
            await interaction.channel.send(embed=info_embed)
        for channel_id in tournament_channel['alert_channels']:
            alert_channel: TextChannel = guild.get_channel(channel_id)
            await alert_channel.send(embed=info_embed)

        # Add tournament to database
        new_tournament['id'] = tournament_message.id
        new_tournament['jump_url'] = tournament_message.jump_url
        result = await _guild.push_to_guild(guild, TOURNAMENTS, new_tournament)
        print(f"User '{user.name}' [id={user.id}] created new tournament '{tournament_title}'.")

        if respond: await interaction.followup.send(f"Successfully created tournament '***{tournament_title}***'.")
        return (new_tournament, tournament_message, tournament_challonge)
    except Exception as e:
        printlog("Something went wrong when creating the tournament.", e)
        if respond: await interaction.followup.send(f"Something went wrong when creating tournament '***{tournament_title}***'.")
        # Delete challonge tournament
        try:
            challonge.tournaments.destroy(tournament_challonge['id'])
        except: pass
        # Delete tournament message
        try:
            if tournament_message:
               await tournament_message.delete()
        except: pass
        # Delete thread if applicable
        try:
            if tournament_thread:
               await tournament_thread.delete()
        except: pass
        # Delete tournament document
        try:
            if result:
                await _guild.pull_from_guild(guild, TOURNAMENTS, new_tournament)
        except: pass
        return None, None, None

async def delete_tournament(interaction: Interaction, tournament_title: str, respond: bool=True):
    """
    Deletes the specified tournament (if it exists).
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    # Fetch tournament
    # usage = 'Usage: `$tournament delete [title]`'
    db_tournament, tournament_title = await retrieve_valid_tournament(interaction, db_guild, tournament_title)
    retval = True
    if not db_tournament:
        return False
    # Only allow author or guild admins to delete tournament
    if user != db_tournament['author']['id'] and not user.guild_permissions.administrator:
        if respond: await interaction.followup.send(f"Only the author or server admins can delete tournaments.", ephemeral=True)
        return False
    # Check if in valid channel
    if not await valid_tournament_channel(db_tournament, interaction, respond):
        return False
    # Delete every match message and document associated with the tournament
    # NOT NEEDED ANYMORE BECAUSE MATCHES ARE PART OF THE BRACKET SUBDOCUMENT
    # await delete_all_matches(channel, db_tournament)
    # Delete tournament document
    try:
        result = await _guild.pull_from_guild(guild, TOURNAMENTS, db_tournament)
    except:
        print(f"Failed to delete tournament ['name'={tournament_title}].")
    # Delete tournament message
    try:
        tournament_message: Message = await channel.fetch_message(db_tournament['id'])
        await tournament_message.delete() # delete message from channel
    except:
        print(f"Failed to delete message for tournament '{tournament_title}' ['id'='{db_tournament['id']}'].")
    if result:
        try:
            challonge.tournaments.destroy(db_tournament['challonge']['id']) # delete tournament from challonge
        except Exception as e:
            printlog(f"Failed to delete tournament [id='{db_tournament['id']}] from challonge [id='{db_tournament['challonge']['id']}].", e)
            retval = False
        print(f"User '{user.name}' [id={user.id}] deleted tournament '{tournament_title}'.")
    else:
        if respond: await interaction.followup.send(f"Failed to delete tournament '***{tournament_title}***'.", ephemeral=True)
        retval = False
    if respond: await interaction.followup.send(f"Successfully deleted tournament '***{tournament_title}***'.")
    # Delete thread if applicable
    if db_tournament['thread_id']:
        try:
            tournament_thread: Thread = guild.get_thread(db_tournament['thread_id'])
            await tournament_thread.delete()
        except:
            print(f"Failed to delete thread for tournament '{tournament_title}' ['thread_id'='{db_tournament['thread_id']}'].")
    return retval

async def update_tournament(interaction: Interaction, tournament_title: str , new_tournament_title: str | None=None, time: str | None=None, single_elim: bool | None=None, max_participants: int | None=None):
    """
    Updates the specified tournament (if it exists).
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    # Fetch tournament
    # usage = 'Usage: `$tournament update [name]`'
    db_tournament, tournament_title = await retrieve_valid_tournament(interaction, db_guild, tournament_title)
    if not db_tournament: 
        return False
    # Only allow author or guild admins to update tournament
    if user.id != db_tournament['author']['id'] and not user.guild_permissions.administrator:
        await interaction.followup.send(f"Only the author or server admins can update the tournament.", ephemeral=True)
        return False
    # Check if in valid channel
    if not await valid_tournament_channel(db_tournament, interaction):
        return False
    # Only allow updating if the tournament has not been started or completed
    if not db_tournament['open'] or db_tournament['completed']:
        await interaction.followup.send(f"You may only update tournaments in the registration phase.", ephemeral=True)
        return False
    # Check if updating info
    if not (new_tournament_title is not None or time is not None or single_elim is not None or max_participants is not None):
        await interaction.followup.send(f"Must include at least one field to update.", ephemeral=True)
        return False
    # Updating tournament_title
    if new_tournament_title is not None:
        if len(new_tournament_title.strip()) == 0:
            await interaction.followup.send(f"Tournament title cannot be empty.")
            return None, None, None
        if len(new_tournament_title.strip()) > 60:
            await interaction.followup.send(f"Tournament title can be no longer than 60 characters.")
            return None, None, None
        db_tournament['title'] = new_tournament_title
    # Updating time
    if time is not None:
        db_tournament['start_time'] = parse_time(time)
    # Updating type
    if single_elim is not None:
        db_tournament['tournament_type'] = "single elimination" if single_elim else "double elimination"
    # Updating max_participants
    if max_participants is not None:
        if (max_participants < 4 or max_participants > MAX_ENTRANTS):
            await interaction.followup.send(f"`max_participants` must be between 4 and {MAX_ENTRANTS}.")
            return False
        db_tournament['max_participants'] = max_participants
    # Update the tournament on challonge
    challonge.tournaments.update(db_tournament['challonge']['id'], 
        name=db_tournament['title'], 
        tournament_type=db_tournament['tournament_type'],
        start_at=db_tournament['start_time'], 
        signup_cap=max_participants,
    )
    # Update the tournament in database
    await set_tournament(guild.id, tournament_title, db_tournament)
    # Update tournament embed
    tournament_message: Message = await channel.fetch_message(db_tournament['id'])
    author: Member = await guild.fetch_member(db_tournament['author']['id']) or interaction.user
    new_tournament_embed = create_tournament_embed(db_tournament, author)
    await tournament_message.edit(embed=new_tournament_embed)
    await interaction.followup.send(f"Successfully updated tournament.")
    return True

async def start_tournament(interaction: Interaction, tournament_title: str):
    """
    Starts a tournament created by the user.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Fetch tournament
    # usage = 'Usage: `$tournament start [title]`'
    db_tournament, tournament_title = await retrieve_valid_tournament(interaction, db_guild, tournament_title)
    if not db_tournament: 
        return False
    # Only allow author or guild admins to start tournament
    if user.id != db_tournament['author']['id'] and not user.guild_permissions.administrator:
        await interaction.followup.send(f"Only the author or server admins can start the tournament.", ephemeral=True)
        return False
    # Check if in valid channel
    if not await valid_tournament_channel(db_tournament, interaction):
        return False
    # Check if already started
    if not db_tournament['open']:
        await interaction.followup.send(f"'***{tournament_title}***' has already been started.", ephemeral=True)
        return False
    # Make sure there are sufficient number of participants
    if len(db_tournament['participants']) < MIN_ENTRANTS:
        await interaction.followup.send(f"Tournament must have at least {MIN_ENTRANTS} participants before starting.", ephemeral=True)
        return False
    # Only allow one tournament to be started at a time in a guild
    active_tournament = find_active_tournament(db_guild)
    if active_tournament and active_tournament['id'] != db_tournament['id']:
        active_tournament_id = active_tournament['thread_id'] or active_tournament['channel_id'] or active_tournament['id']
        await interaction.followup.send(f"There may only be one active tournament per server.\nCurrent active tournament in: <#{active_tournament_id}>.", ephemeral=True)
        return False
    # Start tournament on challonge
    try:
        challonge.tournaments.start(db_tournament['challonge']['id'], include_participants=1, include_matches=1)
    except Exception as e:
        printlog(f"Failed to start tournament ['title'='{tournament_title}'] on challonge.")
        await interaction.followup.send(f"Something went wrong when starting '***{tournament_title}***' on challonge.")
        return False
    printlog(f"User ['name'='{user.name}'] started tournament '{tournament_title}' [id={db_tournament['id']}].")
    # Challonge API changed? Retrive matches.
    challonge_matches = challonge.matches.index(db_tournament['challonge']['id'])
    # Get total number of rounds
    max_round = 0
    for match in challonge_matches:
       round = match['round']
       if round > max_round:
           max_round = round
    # Set tournament to closed in database and set total number of rounds
    db_tournament.update({'open': False, 'num_rounds': max_round })
    await set_tournament(guild.id, tournament_title, db_tournament)
    print(f"User ['name'='{user.name}'] started tournament ['title'='{tournament_title}'].")
    # Send start message
    # tournament_message = await channel.fetch_message(db_tournament['id'])
    await channel.send(content=f"'***{tournament_title}***' has now started!") # Reply to original tournament message
    # Get each initial open matches
    matches = list(filter(lambda match: (match['state'] == 'open'), challonge_matches))
    for match in matches:
        try:
            await _match.create_match(channel, guild, db_tournament, match)
        except Exception as e:
            printlog(f"Failed to add match ['match_id'='{match['id']}'] to tournament ['title'='{tournament_title}']", e)
    # Update embed message
    await edit_tournament_message(db_tournament, channel)
    await interaction.followup.send(f"Successfully started tournament '***{tournament_title}***'.")
    return True

async def reset_tournament(interaction: Interaction, tournament_title: str):
    """
    Resets a tournament if it has been started.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    # Fetch tournament
    # usage = 'Usage: `$tournament reset [title]`'
    db_tournament, tournament_title = await retrieve_valid_tournament(interaction, db_guild, tournament_title)
    if not db_tournament:
        return False
    tournament_message_id = db_tournament['id']
    challonge_id = db_tournament['challonge']['id']
    # Check if in valid channel
    if not await valid_tournament_channel(db_tournament, interaction):
        return False
    # Only allow author or guild admins to reset tournament
    if user.id != db_tournament['author']['id'] and not user.guild_permissions.administrator:
        await interaction.followup.send(f"Only the author or server admins can reset the tournament.", ephemeral=True)
        return False
    # Check if already completed
    if db_tournament['completed']: 
        await interaction.followup.send(f"Cannot reset a finalized tournament.", ephemeral=True)
        return False
    # Delete every match message and document associated with the tournament
    await delete_all_matches(channel, db_tournament)
    # Reset tournament on challonge
    try:
        challonge.tournaments.reset(challonge_id)
    except Exception as e:
        printlog(f"Something went wrong when resetting tournament ['title'='{tournament_title}'] on challonge.", e)
    # Set open to true and reset number of rounds
    db_tournament.update({'open': True, 'num_rounds': None, 'matches': []})
    await set_tournament(guild.id, tournament_title, db_tournament)
    print(f"User ['name'='{user.name}'] reset tournament ['title'='{tournament_title}'].")
    # Reset tournament message
    tournament_message = await channel.fetch_message(tournament_message_id)
    author: Member = await guild.fetch_member(db_tournament['author']['id']) or interaction.user
    new_tournament_embed = create_tournament_embed(db_tournament, author)
    await tournament_message.edit(embed=new_tournament_embed, view=registration_buttons_view())
    await interaction.followup.send(f"Successfully reset tournament '***{tournament_title}***'.")
    return True

async def finalize_tournament(interaction: Interaction, tournament_title: str):
    """
    Closes a tournament if completed.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    # Fetch tournament
    # usage = 'Usage: `$tournament finalize [title]`'
    completed_time = datetime.now(tz=EASTERN_ZONE)
    db_tournament, tournament_title = await retrieve_valid_tournament(interaction, db_guild, tournament_title)
    if not db_tournament:
        return False
    # Only allow author or guild admins to finalize tournament
    if user.id != db_tournament['author']['id'] and not user.guild_permissions.administrator:
        await interaction.followup.send(f"Only the author or server admins can finalize the tournament.", ephemeral=True)
        return False
    # Check if in valid channel
    if not await valid_tournament_channel(db_tournament, interaction):
        return False
    # Check if already finalized
    if db_tournament['completed']:
        await interaction.followup.send(f"'***{tournament_title}***' has already been finalized.", ephemeral=True)
        return False
    challonge_id = db_tournament['challonge']['id']
    # Finalize tournament on challonge
    try:
        final_tournament = challonge.tournaments.finalize(challonge_id, include_participants=1, include_matches=1)
    except Exception as e:
        printlog(f"Failed to finalize tournament on challonge ['title'='{tournament_title}'].", e)
        try: # Try and retrive tournament information instead of finalizing
            final_tournament = challonge.tournaments.show(challonge_id, include_participants=1, include_matches=1)
        except:
            print(f"Could not find tournament on challonge ['challonge_id'='{challonge_id}'].")
            return False
    # Create results message
    db_tournament['completed'] = completed_time # update completed time
    embed = create_results_embed(db_tournament, final_tournament['participants'])
    result_message = await channel.send(content=f"'***{tournament_title}***' has been finalized. Here are the results!", embed=embed) # Reply to original tournament message
    # Set tournament to completed in database
    try: 
        db_tournament.update({'result_url': result_message.jump_url}) # update result jump url
        await set_tournament(guild.id, tournament_title, db_tournament)
    except:
        print(f"Failed to update final tournament ['id'='{db_tournament['id']}'].")
        return False
    # Update embed message
    await edit_tournament_message(db_tournament, channel)
    print(f"User ['name'='{user.name}'] Finalized tournament '{tournament_title}' ['id'='{db_tournament['id']}'].")
    # Close thread if applicable
    if db_tournament['thread_id']:
        try:
            tournament_thread: Thread = guild.get_thread(db_tournament['thread_id'])
            await tournament_thread.edit(locked=True, pinned=False)
        except:
            print(f"Failed to edit thread for tournament '{tournament_title}' ['thread_id'='{db_tournament['thread_id']}'].")
    await interaction.followup.send(f"Successfully finalized tournament '***{tournament_title}***'.")
    return True

async def send_results(interaction: Interaction, tournament_title: str):
    """
    Sends the results message of a tournament that has been completed.
    """
    guild: Guild = interaction.guild
    db_guild = await _guild.find_guild(guild.id)
    # Fetch tournament
    # usage = 'Usage: `$tournament results <title>`'
    db_tournament, tournament_title = await retrieve_valid_tournament(interaction, db_guild, tournament_title)
    challonge_id = db_tournament['challonge']['id']
    if not db_tournament:
        return False
    # Check if tournament is completed
    if not db_tournament['completed']:
        await interaction.followup.send(f"'***{tournament_title}***' has not yet been finalized.", ephemeral=True)
        return False
    # Retrive challonge tournament information
    try: 
        final_tournament = challonge.tournaments.show(challonge_id, include_participants=1, include_matches=1)
    except:
        print(f"Could not find tournament on challonge ['challonge_id'='{challonge_id}'].")
        return False
    # Create results message
    embed = create_results_embed(db_tournament, final_tournament['participants'])
    await interaction.followup.send(embed=embed) # Reply to original tournament message
    return True

##################
## BUTTON VIEWS ##
##################

class registration_buttons_view(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Join", style=discord.ButtonStyle.green, custom_id="join_tournament")
    async def join(self: discord.ui.View, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await _participant.add_participant(interaction)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.red, custom_id="leave_tournament")
    async def leave(self: discord.ui.View, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await _participant.remove_participant(interaction)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.blurple, custom_id="start_tournament")
    async def start(self: discord.ui.View, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        db_guild = await _guild.find_guild(interaction.guild.id)
        db_tournament = find_tournament_by_id(db_guild, interaction.message.id)
        tournament_title = db_tournament['title']
        await start_tournament(interaction, tournament_title)

######################
## HELPER FUNCTIONS ##
######################

async def valid_tournament_channel(db_tournament: dict, interaction: Interaction, respond: bool=True):
    """
    Checks if performing command in valid channel.
    i.e. Channel that tournament was created in or the tournament thread if applicable.
    """
    tournament_title = db_tournament['title']
    channel_id: TextChannel | ForumChannel | Thread = interaction.channel_id
    if db_tournament['thread_id'] != channel_id:
        if respond: await interaction.followup.send(f"Command only available in the tournament thread for '***{tournament_title}***': <#{db_tournament['thread_id']}>.", ephemeral=True)
        return False
    return True

async def retrieve_valid_tournament(interaction: Interaction, db_guild: dict, tournament_title: str):
    """"
    Checks if there is a valid tournament.
    By default, finds tournament by tournament title.
    Otherwise, finds the current active tournament or most recent tournament (completed or not completed).
    """
    # Get tournament from database
    if len(tournament_title.strip()) > 0:
        # Check if tournament exists
        db_tournament = find_tournament(db_guild, tournament_title)
        if not db_tournament:
            await interaction.followup.send(f"Tournament with name '{tournament_title}' does not exist.", ephemeral=True)
            return (None, None)
    else:
        # Check if in thread
        if 'thread' in str(interaction.channel.type):
            db_tournament = find_tournament_by_id(db_guild, interaction.channel_id)
            if not db_tournament:
                await interaction.followup.send(f"This thread is not for a tournament.", ephemeral=True)
                return (None, None)
        else:
            await interaction.followup.send(f"Command must be used in a tournament thread..", ephemeral=True)
            return (None, None)
        tournament_title = db_tournament['title']
    return (db_tournament, tournament_title)

def find_index_in_tournament(db_tournament: dict, target_field: str, target_key: str, target_value):
    """
    Returns the index of a dictionary in a tournament list.
    """
    for i, dic in enumerate(db_tournament[target_field]):
        if dic[target_key] == target_value:
            return i
    return -1

async def set_tournament(guild_id: int, tournament_title: str, new_tournament: dict):
    """
    Sets a tournament in a guild to the specified document.
    """
    return await mdb.update_single_document(
        {'guild_id': guild_id, 'tournaments.title': tournament_title, 'tournaments.id': new_tournament['id']}, 
        {'$set': {f'tournaments.$': new_tournament}
        },
        GUILDS)

async def add_to_tournament(guild_id: int, tournament_title: str, target_field: str, document: dict):
    """
    Pushes a document to a tournament subarray.
    """
    return await mdb.update_single_document(
        {'guild_id': guild_id, 'tournaments.title': tournament_title}, 
        {'$push': {f'tournaments.$.{target_field}': document}},
        GUILDS)

async def remove_from_tournament(guild_id: int, tournament_title: str, target_field: str, target_id: int):
    """
    Pulls a document from a tournament subarray.
    """
    return await mdb.update_single_document(
        {'guild_id': guild_id, 'tournaments.title': tournament_title}, 
        {'$pull': {f'tournaments.$.{target_field}': {'id': target_id}}},
        GUILDS)

async def delete_all_matches(channel: TextChannel, db_tournament: dict):
    """
    Deletes all matches in the specified tournament.
    """
    tournament_title = db_tournament['title']
    retval = True
    for match in db_tournament['matches']:
        match_id = match['id']
        try:
            await _match.delete_match(channel, db_tournament, match_id)
        except:
            print(f"Failed to delete match ['id'={match_id}] while deleting tournament ['title'={tournament_title}].")
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

#######################
## MESSAGE FUNCTIONS ##
#######################

def create_tournament_embed(db_tournament: dict, author: Member):
    """
    Creates embed object to include in tournament message.
    """
    tournament_title = db_tournament['title']
    challonge_url = db_tournament['challonge']['url']
    time = db_tournament['start_time']
    
    # Check the status
    if db_tournament['completed']:
        status = "Completed 🏁"
    elif db_tournament['open']:
        status = "Open for Registration! 🚨"
    else:
        status = "Started 🟩"
    # Main embed
    embed = Embed(title=f'🥊  {tournament_title}', description=f"Status: {status}" if not db_tournament['thread_id'] else "", color=WOOP_PURPLE)
    # Author field
    embed.set_author(name="beta-bot | GitHub 🤖", url="https://github.com/fborja44/beta-bot", icon_url=ICON)
    # Tournament description fields
    embed.add_field(name='Tournament Type', value=db_tournament['tournament_type'].title())
    time_str = time.strftime("%A, %B %d, %Y %#I:%M %p %Z") # time w/o ms
    embed.add_field(name='Starting At', value=time_str)
    # Entrants list
    if db_tournament['max_participants']:
        embed.add_field(name='Entrants (0)', value="> *None*", inline=False)
    else:
        max_participants = db_tournament['max_participants']
        embed.add_field(name=f'Entrants (0/{max_participants})', value="> *None*", inline=False)
    embed = update_embed_participants(db_tournament, embed)
    # Bracket link
    embed.add_field(name=f'Bracket Link', value=challonge_url, inline=False)
    # Set footer
    embed.set_footer(text=f'Created by {author.display_name} | {author.name}#{author.discriminator}.', icon_url=db_tournament['author']['avatar_url'])
    return embed

async def edit_tournament_message(db_tournament: dict, channel: TextChannel):
    """
    Edits tournament embed message in a channel.
    """
    tournament_title = db_tournament['title']
    tournament_message: Message = await channel.fetch_message(db_tournament['id'])
    embed = tournament_message.embeds[0]
    embed = update_embed_participants(db_tournament, embed)
    if db_tournament['completed']:
        status = " Completed 🏁"
    elif db_tournament['open']:
        status = "Open for Registration 🚨"
    else:
        await tournament_message.edit(view=None)
        status = "Started 🟩"
    if not db_tournament['thread_id']:
        embed.description = f"Status: {status}"
    if not db_tournament['open']:
        image_embed = None
        try:
            image_embed = create_tournament_image(db_tournament, embed)
        except Exception as e:
            printlog(f"Failed to create image for tournament ['title'='{tournament_title}'].")
            print(e)
        if not image_embed:
            printlog(f"Error when creating image for tournament ['title'='{tournament_title}'].")
        else:
            embed = image_embed
    if db_tournament['completed']:
        time_str = db_tournament['completed'].strftime("%A, %B %d, %Y %#I:%M %p %Z") # time w/o ms
        embed.add_field(name=f'Completed At', value=f"{time_str}\nUse `/t results`", inline=False)
    if db_tournament['thread_id']:
        content = status
    else:
        content = ""
    await tournament_message.edit(content=content, embed=embed)

def update_embed_participants(db_tournament: dict, embed: Embed):
    """
    Updates the participants list in a tournament embed.
    """
    participants = db_tournament['participants']
    if len(participants) > 0:
        participants_content = ""
        for participant in participants:
            # To mention a user:
            # <@{user_id}>
            participants_content += f"> <@{participant['id']}>\n"
    else:
        participants_content = '> *None*'
    max_participants = db_tournament['max_participants']
    name = f'Entrants ({len(participants)}/{max_participants})' if max_participants else f'Entrants ({len(participants)})'
    embed.set_field_at(2, name=name, value=participants_content, inline=False)
    return embed

def create_tournament_image(db_tournament: dict, embed: Embed):
    """
    Creates an image of the tournament.
    Converts the generated svg challonge image to png and uploads it to imgur.
    Discord does not support svg images in preview.
    """
    tournament_title = db_tournament['title']
    challonge_url = db_tournament['challonge']['url']
    if len(db_tournament['participants']) >= 2:
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
            printlog(f"Failed to create image for tournament ['title'='{tournament_title}'].")
            return False
    else:
        printlog(f"Failed to create image for tournament ['title'='{tournament_title}'].")
        return False

def create_results_embed(db_tournament: dict, participants: list):
    """
    Creates embed object with final results to include after finalizing tournament.
    """
    tournament_title = db_tournament['title']
    challonge_url = db_tournament['challonge']['url']
    # jump_url = db_tournament['jump_url']
    # Main embed
    embed = Embed(title=f"🏆  Final Results for '{tournament_title}'", color=GOLD)
    # Author field
    embed.set_author(name="beta-bot | GitHub 🤖", url="https://github.com/fborja44/beta-bot", icon_url=ICON)
    results_content = ""
    participants.sort(key=(lambda participant: participant['participant']['final_rank']))
    # List placements
    for i in range (min(len(participants), 8)):
        participant = participants[i]['participant']
        match participant['final_rank']:
            case 1:
                results_content += f"> 🥇  {participant['name']}\n"
            case 2:
                results_content += f"> 🥈  {participant['name']}\n"
            case 3:
                results_content += f"> 🥉  {participant['name']}\n"
            case _:
                results_content += f"> **{participant['final_rank']}.** {participant['name']}\n"
    embed.add_field(name=f'Placements', value=results_content, inline=False)
    # Other info fields
    embed.add_field(name=f'Bracket Link', value=challonge_url, inline=False)
    time_str = db_tournament['completed'].strftime("%A, %B %d, %Y %#I:%M %p %Z") # time w/o ms
    embed.set_footer(text=f'Completed: {time_str}')
    return embed

def create_info_embed(db_tournament: dict):
    author_name = db_tournament['author']['username']
    thread_id = db_tournament['thread_id']
    tournament_channel_id = db_tournament['channel_id']
    tournament_link = f'<#{thread_id}>' if thread_id else f'<#{tournament_channel_id}>'
    time = db_tournament['start_time']
    embed = Embed(title=f'💥 {author_name} has created a new tournament!', color=WOOP_PURPLE)
    embed.set_author(name="beta-bot | GitHub 🤖", url="https://github.com/fborja44/beta-bot", icon_url=ICON)
    # Tournament description fields
    embed.add_field(name=db_tournament['title'], value=f"Register at: {tournament_link}", inline=False)
    embed.add_field(name='Tournament Type', value=db_tournament['tournament_type'].title())
    time_str = time.strftime("%A, %B %d, %Y %#I:%M %p %Z") # time w/o ms
    embed.add_field(name='Starting At', value=time_str)
    return embed

#######################
## TESTING FUNCTIONS ##
#######################

async def create_test_tournament(interaction: Interaction, num_participants: int = 4):
    """
    Testing function. Creates a test tournament and adds two participants.
    """
    printlog("Creating test tournament...")
    tournament_title = "Test Tournament"
    tournament_db , tournament_message , tournament_challonge = None, None, None
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Only allow guild admins to create a test tournament
    if not user.guild_permissions.administrator:
        return await interaction.followup.send(f"Only admins can create a test tournament.")

    # Delete previous test tournament if it exists
    try:
        db_tournament = find_tournament(db_guild, tournament_title)
        if db_tournament:
            await delete_tournament(interaction, tournament_title, respond=False)
        # Call create_tournament
        db_tournament, tournament_message, tournament_challonge = await create_tournament(interaction, tournament_title, respond=False)

        members = [guild.get_member_named('beta#3096'), guild.get_member_named("pika!#3722"), guild.get_member_named("Wooper#0478"), guild.get_member_named("WOOPBOT#4140")]
        for i in range(num_participants):
            try:
                await _participant.add_participant(interaction, db_tournament, members[i], respond=False)
            except:
                pass
        await interaction.followup.send(f"Finished generating Test Tournament and participants.")
        return True
    except Exception as e:
        printlog("Failed to create test tournament.", channel)
        print_exception(e)
        await interaction.followup.send(f"Something went wrong when generating the test tournament.", ephemeral=True)
        if tournament_message:
            await delete_tournament(interaction, tournament_title, respond=False)
        return False