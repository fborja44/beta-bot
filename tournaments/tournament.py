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
        return guild_tournaments
    except Exception as e:
        print(e)
        return None

async def create_tournament(interaction: Interaction, tournament_title: str, time: str="", single_elim: bool = False, max_participants: int = 24, respond: bool = True):
    """
    Creates a new tournament and adds it to the guild.
    """
    guild: Guild = interaction.guild
    channel: ForumChannel | TextChannel = interaction.channel if 'thread' not in str(interaction.channel.type) else interaction.channel.parent
    thread: Thread = interaction.channel if 'thread' in str(interaction.channel.type) else None
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Check if the server has a tournament channel set
    if len(db_guild['config']['tournament_channels']) == 0:
        if respond: await interaction.followup.send('This server does not have a tournament channel set. To create a tournament channel, use `/ch create`.')
        return False
    # Check if in a valid tournament channel/thread
    db_tournament_channel = None
    if thread:
        db_tournament_channel = _channel.find_tournament_channel_by_thread_id(db_guild, thread.id)
    else:
        db_tournament_channel = _channel.find_tournament_channel(db_guild, channel.id)
    if not db_tournament_channel:
        channel_id_list = _channel.get_tournament_channel_ids(db_guild)
        channel_embed = _channel.create_channel_list_embed(channel_id_list, f"Tournament Channels for '{guild.name}'")
        if respond: await interaction.followup.send(f"<#{channel.id if not thread else thread.id}> is not a valid tournament channel.", embed=channel_embed)
        return False
    channel = guild.get_channel(db_tournament_channel['id'])
    # Check if bot has thread permissions
    bot_user = guild.get_member(interaction.client.user.id)
    bot_permissions = channel.permissions_for(bot_user)
    if not bot_permissions.create_private_threads or not bot_permissions.create_public_threads:
        if respond: await interaction.followup.send("The bot is needs permissions to post private/public threads to create tournaments.")
        return False
    # Parse time; Default is 1 hour from current time
    try:
        parsed_time = parse_time(time)
    except ValueError as e:
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
        if respond: await interaction.followup.send(f"Tournament with title '{tournament_title}' already exists in this server.")
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
            'id': None,                                             # Message ID and Thread ID; Initialized later
            'channel_id': channel.id,                               # TextChannel/Thread that the create command was called in
            'title': tournament_title, 
            'tournament_type': tournament_challonge['tournament_type'],
            'jump_url': None,                                       # Initialized later
            'result_url': None,
            'author': {
                'username': f"{user.name}#{user.discriminator}", 
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
        thread_title = f"🥊 {tournament_title} - {tournament_challonge['tournament_type'].title()}"
        thread_content = "Open for Registration 🚨"
        if str(channel.type) == 'forum': # Creating as a forum channel thread
            tournament_thread, tournament_message = await channel.create_thread(name=thread_title, content=thread_content , embed=embed, view=registration_buttons_view())
        else: # Creating as a text channel thread
            tournament_message = await channel.send(embed=embed)
            tournament_thread = await channel.create_thread(name=thread_title, message=tournament_message)
            await tournament_thread.starter_message.edit(view=registration_buttons_view())
        # Update tournament object
        new_tournament['id'] = tournament_message.id
        new_tournament['jump_url'] = tournament_message.jump_url
        # Send creation message in alert channels (including forum channel)
        info_embed = create_info_embed(new_tournament)
        if thread:
            await interaction.channel.send(embed=info_embed)
        for channel_id in db_tournament_channel['alert_channels']:
            alert_channel: TextChannel = guild.get_channel(channel_id)
            await alert_channel.send(embed=info_embed)

        # Add tournament to database
        result = await _guild.push_to_guild(guild, TOURNAMENTS, new_tournament)
        print(f"User '{user.name}#{user.discriminator}' [id={user.id}] created new tournament '{tournament_title}'.")

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
        # Delete thread
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

async def send_seeding(interaction: Interaction, tournament_title: str):
    """
    Sends the seeding for a tournament.
    """
    guild: Guild = interaction.guild
    db_guild = await _guild.find_guild(guild.id)
    # Fetch tournament
    db_tournament, tournament_title, _ = await find_valid_tournament(interaction, db_guild, tournament_title)
    if not db_tournament:
        return False
    # Create seeding message
    embed = create_seeding_embed(db_tournament)
    await interaction.followup.send(embed=embed)
    return True   

async def delete_tournament(interaction: Interaction, tournament_title: str, respond: bool=True):
    """
    Deletes the specified tournament (if it exists).
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    retval = True
    # Validate arguments
    try:
        db_tournament, tournament_title, tournament_thread, tournament_channel = await validate_arguments_tournament(
        interaction, db_guild, tournament_title, respond=respond)
    except:
        return False
    # Delete tournament document
    try:
        result = await _guild.pull_from_guild(guild, TOURNAMENTS, db_tournament)
    except:
        print(f"Failed to delete tournament ['name'={tournament_title}].")
    if result:
        try:
            challonge.tournaments.destroy(db_tournament['challonge']['id']) # delete tournament from challonge
        except Exception as e:
            printlog(f"Failed to delete tournament [id='{db_tournament['id']}] from challonge [id='{db_tournament['challonge']['id']}].", e)
            retval = False
        print(f"User '{user.name}#{user.discriminator}' [id={user.id}] deleted tournament '{tournament_title}'.")
    else:
        if respond: await interaction.followup.send(f"Failed to delete tournament '***{tournament_title}***'.", ephemeral=True)
        retval = False
    # Delete thread
    try:
        await tournament_thread.delete()
    except:
        print(f"Failed to delete thread for tournament '{tournament_title}' ['id'='{db_tournament['id']}'].")
    # Delete tournament message if tournament channel is Text Channel
    if str(tournament_channel.type) == 'text':
        try:
            tournament_message: Message = await tournament_channel.fetch_message(db_tournament['id'])
            await tournament_message.delete() # delete message from channel
        except discord.NotFound:
            print(f"Failed to delete message for tournament '{tournament_title}' ['id'='{db_tournament['id']}']; Not found.")
        except discord.Forbidden:
            print(f"Failed to delete message for tournament '{tournament_title}' ['id'='{db_tournament['id']}']; Bot does not have proper permissions.")
            return False
    if respond and interaction.channel.id != tournament_thread.id: await interaction.followup.send(f"Successfully deleted tournament '***{tournament_title}***'.")
    return retval

async def update_tournament(interaction: Interaction, tournament_title: str , new_tournament_title: str | None=None, time: str | None=None, single_elim: bool | None=None, max_participants: int | None=None):
    """
    Updates the specified tournament (if it exists).
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    # Validate arguments
    try:
        db_tournament, tournament_title, tournament_thread, tournament_channel = await validate_arguments_tournament(
            interaction, db_guild, tournament_title)
    except ValueError:
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
            return False
        if len(new_tournament_title.strip()) > 60:
            await interaction.followup.send(f"Tournament title can be no longer than 60 characters.")
            return False
        db_tournament['title'] = new_tournament_title.strip()
    # Updating time
    if time is not None:
        db_tournament['start_time'] = parse_time(time.strip())
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
    if _channel.in_forum(interaction):
        tournament_message: Message = await tournament_thread.fetch_message(db_tournament['id'])
    else:
        tournament_message: Message = await tournament_channel.fetch_message(db_tournament['id'])
    author: Member = await guild.fetch_member(db_tournament['author']['id']) or interaction.user
    new_tournament_embed = create_tournament_embed(db_tournament, author)
    await tournament_message.edit(embed=new_tournament_embed)
    if interaction.channel.id != tournament_thread.id:
        await tournament_thread.send(f"This tournament has been updated by <@{user.id}>.")
    await interaction.followup.send(f"Successfully updated tournament.")
    return True

async def start_tournament(interaction: Interaction, tournament_title: str):
    """
    Starts a tournament created by the user.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Validate arguments
    try:
        db_tournament, tournament_title, tournament_thread, tournament_channel = await validate_arguments_tournament(
            interaction, db_guild, tournament_title)
    except ValueError:
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
        active_tournament_id = active_tournament['channel_id'] or active_tournament['id']
        await interaction.followup.send(f"There may only be one active tournament per server.\nCurrent active tournament in: <#{active_tournament_id}>.", ephemeral=True)
        return False
    # Start tournament on challonge
    try:
        challonge.tournaments.start(db_tournament['challonge']['id'], include_participants=1, include_matches=1)
    except Exception as e:
        printlog(f"Failed to start tournament ['title'='{tournament_title}'] on challonge.")
        await interaction.followup.send(f"Something went wrong when starting '***{tournament_title}***' on challonge.")
        return False
    printlog(f"User ['name'='{user.name}#{user.discriminator}'] started tournament '{tournament_title}' [id={db_tournament['id']}].")
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
    print(f"User ['name'='{user.name}#{user.discriminator}'] started tournament ['title'='{tournament_title}'].")
    # Send start message
    await tournament_thread.send(content=f"'***{tournament_title}***' has now started!")
    # Get each initial open matches
    matches = list(filter(lambda match: (match['state'] == 'open'), challonge_matches))
    for match in matches:
        try:
            await _match.create_match(tournament_thread, db_guild, db_tournament, match)
        except Exception as e:
            printlog(f"Failed to add match ['match_id'='{match['id']}'] to tournament ['title'='{tournament_title}']", e)
    # Update embed message
    await edit_tournament_message(db_tournament, tournament_channel, tournament_thread)
    await interaction.followup.send(f"Successfully started tournament '***{tournament_title}***'.", ephemeral=True)
    return True

async def reset_tournament(interaction: Interaction, tournament_title: str):
    """
    Resets a tournament if it has been started.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    # Validate arguments
    try:
        db_tournament, tournament_title, tournament_thread, tournament_channel = await validate_arguments_tournament(
            interaction, db_guild, tournament_title)
    except ValueError:
        return False
    challonge_id = db_tournament['challonge']['id']
    # Check if it has been started
    if db_tournament['open']:
        await interaction.followup.send(f"Cannot reset a tournament during the registration phase.", ephemeral=True)
        return False
    # Check if already completed
    if db_tournament['completed']: 
        await interaction.followup.send(f"Cannot reset a finalized tournament.", ephemeral=True)
        return False
    # Delete every match message and document associated with the tournament
    await delete_all_matches(tournament_thread, db_guild, db_tournament)
    # Set all participants back to active
    for i in range(len(db_tournament['participants'])):
        if not db_tournament['participants'][i]['active']:
            db_tournament['participants'][i].update({'active': True})
    # Reset tournament on challonge
    try:
        challonge.tournaments.reset(challonge_id)
    except Exception as e:
        printlog(f"Something went wrong when resetting tournament ['title'='{tournament_title}'] on challonge.", e)
    # Set open to true and reset number of rounds
    db_tournament.update({'open': True, 'num_rounds': None, 'matches': []})
    await set_tournament(guild.id, tournament_title, db_tournament)
    print(f"User ['name'='{user.name}#{user.discriminator}'] reset tournament ['title'='{tournament_title}'].")
    # Reset tournament message
    author: Member = await guild.fetch_member(db_tournament['author']['id']) or interaction.user
    new_tournament_embed = create_tournament_embed(db_tournament, author)
    # Check if forum channel before editing content
    if _channel.in_forum(interaction):
        tournament_message = await tournament_thread.fetch_message(db_tournament['id']) # CANNOT FETCH INITIAL MESSAGE IN THREAD
        await tournament_message.edit(content="Open for Registration 🚨", embed=new_tournament_embed, view=registration_buttons_view())
    else:
        tournament_message = await tournament_channel.fetch_message(db_tournament['id']) # CANNOT FETCH INITIAL MESSAGE IN THREAD
        await tournament_message.edit(embed=new_tournament_embed, view=registration_buttons_view())
    if interaction.channel.id != tournament_thread.id:
        await tournament_thread.send(f"This tournament has been reset by <@{user.id}>.")
    await interaction.followup.send(f"Successfully reset tournament '***{tournament_title}***'.", ephemeral=True)
    return True

async def finalize_tournament(interaction: Interaction, tournament_title: str):
    """
    Closes a tournament if completed.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    completed_time = datetime.now(tz=EASTERN_ZONE)
    # Validate arguments
    try:
        db_tournament, tournament_title, tournament_thread, tournament_channel = await validate_arguments_tournament(
            interaction, db_guild, tournament_title)
    except ValueError:
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
    # Update participants in database with placement
    db_participants = db_tournament['participants']
    ch_participants = final_tournament['participants']
    for i in range (min(len(ch_participants), 8)):
        ch_participant = ch_participants[i]['participant']
        p_index = find_index_in_tournament(db_tournament, 'participants', 'challonge_id', ch_participant['id'])
        db_participants[p_index].update({'placement': ch_participant['final_rank']})
    db_tournament['participants'] = db_participants
    # await set_tournament(guild.id, tournament_title, db_tournament)
    # Create results message
    db_tournament['completed'] = completed_time # update completed time
    embed = create_results_embed(db_tournament)
    result_message = await tournament_thread.send(content=f"'***{tournament_title}***' has been finalized. Here are the results!", embed=embed) # Reply to original tournament message
    # Set tournament to completed in database
    try: 
        db_tournament.update({'result_url': result_message.jump_url}) # update result jump url
        await set_tournament(guild.id, tournament_title, db_tournament)
    except:
        print(f"Failed to update final tournament ['id'='{db_tournament['id']}'].")
        return False
    # Update embed message
    await edit_tournament_message(db_tournament, tournament_channel, tournament_thread)
    print(f"User ['name'='{user.name}#{user.discriminator}'] Finalized tournament '{tournament_title}' ['id'='{db_tournament['id']}'].")
    # Close thread
    try:
        await tournament_thread.edit(locked=True, pinned=False)
    except:
        print(f"Failed to edit thread for tournament '{tournament_title}' ['id'='{db_tournament['id']}'].")
    await interaction.followup.send(f"Successfully finalized tournament '***{tournament_title}***'.", ephemeral=True)
    return True

async def send_results(interaction: Interaction, tournament_title: str):
    """
    Sends the results message of a tournament that has been completed.
    """
    guild: Guild = interaction.guild
    db_guild = await _guild.find_guild(guild.id)
    # Fetch tournament
    db_tournament, tournament_title, _ = await find_valid_tournament(interaction, db_guild, tournament_title)
    if not db_tournament:
        return False
    # Check if tournament is completed
    if not db_tournament['completed']:
        await interaction.followup.send(f"'***{tournament_title}***' has not yet been finalized.", ephemeral=True)
        return False
    # Create results message
    results_embed = create_results_embed(db_tournament)
    await interaction.followup.send(embed=results_embed)
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

async def validate_arguments_tournament(interaction: Interaction, db_guild: dict, tournament_title: str="", admin=True, respond=True):
    """
    
    Validate general arguments passed for tournament admin commands.
    """
    user: Member = interaction.user
    # Fetch tournament
    db_tournament, tournament_title, tournament_thread = await find_valid_tournament(interaction, db_guild, tournament_title)
    if not db_tournament:
        raise ValueError(f"Invalid tournament title. title='{tournament_title}'")
    # Check if in valid channel
    tournament_channel = await valid_tournament_channel(db_tournament, interaction, respond)
    if not tournament_channel:
        raise ValueError(f"Invalid tournament channel.")
    # Only allow author or guild admins to delete tournament
    if admin and user != db_tournament['author']['id'] and not user.guild_permissions.administrator:
        if respond: await interaction.followup.send(f"Only available to server admins or the tournament author.", ephemeral=True)
        raise ValueError(f"User does not have tournament admin permissions.")
    return (db_tournament, tournament_title, tournament_thread, tournament_channel)

async def valid_tournament_channel(db_tournament: dict, interaction: Interaction, respond: bool=True):
    """
    Checks if performing command in valid channel.
    i.e. Channel that tournament was created in or the tournament thread.
    Returns the tournament channel (TextChannel or ForumChannel).
    """
    channel_id = interaction.channel_id if 'thread' not in str(interaction.channel.type) else interaction.channel.parent_id
    if db_tournament['id'] != channel_id and channel_id != db_tournament['channel_id']:
        if respond: await interaction.followup.send(f"Command only available in <#{db_tournament['id']}> or <#{db_tournament['channel_id']}>.", ephemeral=True)
        return None
    return interaction.guild.get_channel_or_thread(db_tournament['channel_id']) # Returns the tournament channel (text or forum), not the tournament thread

async def valid_tournament_thread(db_tournament: dict, interaction: Interaction, respond: bool=True): # TODO: fix args
    """
    Checks if performing command in the tournament thread.
    """
    channel_id = interaction.channel_id # Should be a thread ID
    if db_tournament['id'] != channel_id: 
        if respond: await interaction.followup.send(f"Command only available in <#{db_tournament['id']}>.", ephemeral=True)
        return None
    return interaction.guild.get_channel_or_thread(db_tournament['id'])

async def find_valid_tournament(interaction: Interaction, db_guild: dict, tournament_title: str=""):
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
            await interaction.followup.send(f"Tournament with `title` '***{tournament_title}***' does not exist.", ephemeral=True)
            return (None, None, None)
    else:
        # Check if in thread
        if 'thread' in str(interaction.channel.type):
            db_tournament = find_tournament_by_id(db_guild, interaction.channel_id)
            if not db_tournament:
                await interaction.followup.send(f"Invalid channel. Either provide the `title` parameter if available or use this command in the tournament thread.", ephemeral=True)
                return (None, None, None)
        else:
            await interaction.followup.send(f"Invalid channel. Either provide the `title` parameter if available or use this command in the tournament thread.", ephemeral=True)
            return (None, None, None)
    # Get tournament thread
    tournament_thread = interaction.guild.get_thread(db_tournament['id'])
    return (db_tournament, db_tournament['title'], tournament_thread)

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
    Returns the updated guild and updated tournament.
    """
    updated_guild = await mdb.update_single_document(
        {'guild_id': guild_id, 'tournaments.title': tournament_title, 'tournaments.id': new_tournament['id']}, 
        {'$set': {f'tournaments.$': new_tournament}
        },
        GUILDS)
    return updated_guild, find_tournament(updated_guild, tournament_title)

async def add_to_tournament(guild_id: int, tournament_title: str, target_field: str, document: dict):
    """
    Pushes a document to a tournament subarray.
    Returns the updated guild and updated tournament.
    """
    updated_guild = await mdb.update_single_document(
        {'guild_id': guild_id, 'tournaments.title': tournament_title}, 
        {'$push': {f'tournaments.$.{target_field}': document}},
        GUILDS)
    return updated_guild, find_tournament(updated_guild, tournament_title)

async def remove_from_tournament(guild_id: int, tournament_title: str, target_field: str, target_id: int):
    """
    Pulls a document from a tournament subarray.
    Returns the updated guild and updated tournament.
    """
    updated_guild = await mdb.update_single_document(
        {'guild_id': guild_id, 'tournaments.title': tournament_title}, 
        {'$pull': {f'tournaments.$.{target_field}': {'id': target_id}}},
        GUILDS)
    return updated_guild, find_tournament(updated_guild, tournament_title)

async def delete_all_matches(tournament_thread: Thread, db_guild: dict, db_tournament: dict):
    """
    Deletes all matches in the specified tournament.
    """
    tournament_title = db_tournament['title']
    for match in db_tournament['matches']:
        match_id = match['id']
        try:
            db_guild, db_tournament = await _match.delete_match(tournament_thread, db_guild, db_tournament, match_id)
        except Exception as e:
            printlog(f"Failed to delete match ['id'={match_id}] in tournament ['title'='{tournament_title}'].", e)
            return (None, None)
    return (db_guild, db_tournament)

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
    embed = Embed(title=f'🥊  {tournament_title}', description=f"Status: {status}", color=WOOP_PURPLE)
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

async def edit_tournament_message(db_tournament: dict, tournament_channel: TextChannel | ForumChannel, tournament_thread: Thread):
    """
    Edits tournament embed message in a channel.
    TODO: Update content if made in forum channel
    """
    tournament_title = db_tournament['title']
    if str(tournament_channel.type) == 'forum':
        tournament_message = await tournament_thread.fetch_message(db_tournament['id'])
    else:
        tournament_message = await tournament_channel.fetch_message(db_tournament['id'])
    embed = tournament_message.embeds[0]
    embed = update_embed_participants(db_tournament, embed)
    if db_tournament['completed']:
        status = " Completed 🏁"
    elif db_tournament['open']:
        status = "Open for Registration 🚨"
    else:
        await tournament_message.edit(view=None)
        status = "Started 🟩"
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
    content = status if 'thread' in str(tournament_channel.type) and tournament_channel.parent.type == 'forum' else ""
    await tournament_message.edit(content=content, embed=embed)
    return True

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

def create_seeding_embed(db_tournament: dict):
    """
    Creates embed object with final results to include after finalizing tournament.
    """
    tournament_title = db_tournament['title']
    challonge_url = db_tournament['challonge']['url']
    # jump_url = db_tournament['jump_url']
    # Main embed
    embed = Embed(title=f"Seeding for '{tournament_title}'", description="", color=WOOP_PURPLE)
    # Author field
    embed.set_author(name="beta-bot | GitHub 🤖", url="https://github.com/fborja44/beta-bot", icon_url=ICON)
    db_participants = db_tournament['participants']
    db_participants.sort(key=(lambda participant: participant['seed']))
    # List placements
    for i in range (min(len(db_participants), 8)):
        db_participant = db_participants[i]
        mention = f"<@{db_participant['id']}>"
        embed.description += f"> **{db_participant['seed']}.** {mention}\n"
    # Other info fields
    embed.add_field(name=f'Bracket Link', value=challonge_url, inline=False)
    # embed.set_footer(text=f'To update seeding, use `/t seed`')
    return embed

def create_results_embed(db_tournament: dict):
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
    db_participants = db_tournament['participants']
    db_participants.sort(key=(lambda participant: participant['placement']))
    # List placements
    for i in range (min(len(db_participants), 8)):
        db_participant = db_participants[i]
        mention = f"<@{db_participant['id']}>"
        match db_participant['placement']:
            case 1:
                results_content += f"> 🥇 {mention}\n"
            case 2:
                results_content += f"> 🥈 {mention}\n"
            case 3:
                results_content += f"> 🥉 {mention}\n"
            case _:
                results_content += f"> **{db_participant['placement']}.** {mention}\n"
    embed.add_field(name=f'Placements', value=results_content, inline=False)
    # Other info fields
    embed.add_field(name=f'Bracket Link', value=challonge_url, inline=False)
    time_str = db_tournament['completed'].strftime("%A, %B %d, %Y %#I:%M %p %Z") # time w/o ms
    embed.set_footer(text=f'Completed: {time_str}')
    return embed

def create_info_embed(db_tournament: dict):
    author_name = db_tournament['author']['username']
    thread_id = db_tournament['id']
    tournament_link = f'<#{thread_id}>'
    time = db_tournament['start_time']
    embed = Embed(title=f'💥 {author_name} has created a new tournament!', color=WOOP_PURPLE)
    embed.set_author(name="beta-bot | GitHub 🤖", url="https://github.com/fborja44/beta-bot", icon_url=ICON)
    # Tournament description fields
    embed.add_field(name=db_tournament['title'], value=f"Register at: {tournament_link}", inline=False)
    embed.add_field(name='Tournament Type', value=db_tournament['tournament_type'].title())
    time_str = time.strftime("%A, %B %d, %Y %#I:%M %p %Z") # time w/o ms
    embed.add_field(name='Starting At', value=time_str)
    embed.set_footer(text="Visit the tournament thread to view more details and join.")
    return embed

def create_help_embed(interaction: Interaction):
    embed = Embed(title=f'❔ Tournament Help', color=WOOP_PURPLE)
    embed.description = 'Tournaments must be created in designiated tournament channels. Created tournaments can only be managed by the author or server admins.'
    embed.set_author(name="beta-bot | GitHub 🤖", url="https://github.com/fborja44/beta-bot", icon_url=ICON)
    # Create
    create_value = """Create a tournament using Discord.
                    `/t create title: GENESIS 9`
                    `/t create title: The Big House 10 time: 10:00 PM`
                    `/t create title: Low Tier City single_elim: True max_participants: 12`"""
    embed.add_field(name='/t create', value=create_value, inline=False)
    # Join
    join_value = """Join a tournament in registration phase.
                    `/t join`
                    `/t join title: GENESIS 9`"""
    embed.add_field(name='/t join', value=join_value, inline=False)
    # Leave
    leave_value = """Leave a tournament in registration phase.
                    `/t leave`
                    `/t leave title: GENESIS 9`"""
    embed.add_field(name='/t leave', value=leave_value, inline=False)
    # Seeding
    seeding_value = """Displays the seeding for a tournament.
                    `/t seeding`
                    `/t seeding title: GENESIS 9`"""
    embed.add_field(name='/t seeding', value=seeding_value, inline=False)
    # Set Seed
    set_seed_value = f"""Sets the seed for a participant in a tournament.
                    `/t seed user_mention: `<@{interaction.client.user.id}> `seed: 1`
                    `/t seed user_mention: `<@{interaction.client.user.id}> `seed: 1 title: GENESIS 9`"""
    embed.add_field(name='/t seed', value=set_seed_value, inline=False)
    # Randomize Seeding
    randomize_value = """Randomizes the seeding for a tournament.
                    `/t randomize`
                    `/t randomize title: GENESIS 9`"""
    embed.add_field(name='/t randomize', value=randomize_value, inline=False)
    # Delete
    delete_value = """Delete a tournament.
                    `/t delete`
                    `/t delete title: GENESIS 9`"""
    embed.add_field(name='/t delete', value=delete_value, inline=False)
    # Update
    update_value = """Updates a tournament according to specified fields.
                    `/t update title: GENESIS 9 new_title: GENESIS 10`
                    `/t update title: The Big House 10 time: 9:30 PM`
                    `/t update title: Low Tier city single_elim: False max_participants: 16`"""
    embed.add_field(name='/t update', value=update_value, inline=False)
    # Start
    start_value = """Starts a tournament with at least 2 participants.
                    `/t start`
                    `/t start title: GENESIS 9`"""
    embed.add_field(name='/t start', value=start_value, inline=False)
    # Reset
    reset_value = """Resets a tournament back to registration phase.
                    `/t reset`
                    `/t reset title: GENESIS 9`"""
    embed.add_field(name='/t reset', value=reset_value, inline=False)
    # Finalize
    finalize_value = """Finalizes the results of a tournament if available.
                    `/t finalize`
                    `/t finalize title: GENESIS 9`"""
    embed.add_field(name='/t finalize', value=finalize_value, inline=False)
    # Results
    results_value = """Displays the results of a finalized tournament if available.
                    `/t results`
                    `/t results title: GENESIS 9`"""
    embed.add_field(name='/t results', value=results_value, inline=False)
    # Disqualify
    disqualify_value = f"""Disqualifies a user from a tournament.
                        `/t disqualify user_mention:` <@{interaction.client.user.id}>"""
    embed.add_field(name='/t disqualify', value=disqualify_value, inline=False)
    # Vote
    vote_value = f"""Vote for a winner in a tournament match.
                    `/match vote match_id: 1034908912 vote: ` <@{interaction.client.user.id}>
                    `/match vote match_id: 1034908912 vote: 1️⃣`
                    `/match vote match_id: 1034908912 vote: 1`"""
    embed.add_field(name='/match vote', value=vote_value, inline=False)
    # Report
    report_value = f"""Manually report the result of a tournament match.
                    `/match report match_id: 1034908912 winner: ` <@{interaction.client.user.id}>
                    `/match report match_id: 1034908912 winner: 1️⃣`
                    `/match report match_id: 1034908912 winner: 1`"""
    embed.add_field(name='/match report', value=report_value, inline=False)
    # Medic
    report_value = f"""Re-calls any missing matches in discord.
                    `/match medic`"""
    embed.add_field(name='/match medic', value=report_value, inline=False)
    # Footer
    embed.set_footer(text=f'For more detailed docs, see the README on GitHub.')
    # GitHub Button
    view = discord.ui.View(timeout=None)
    github_button = discord.ui.Button(label='GitHub', url="https://github.com/fborja44/beta-bot", style=discord.ButtonStyle.grey)
    view.add_item(github_button)
    return (embed, view)

#######################
## TESTING FUNCTIONS ##
#######################

async def create_test_tournament(interaction: Interaction, num_participants: int = 4):
    """
    Testing function. Creates a test tournament and adds two participants.
    """
    printlog("Creating test tournament...")
    tournament_title = "Test Tournament"
    _ , tournament_message , _ = None, None, None
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
        db_tournament, tournament_message, _ = await create_tournament(interaction, tournament_title, respond=False)

        members = [guild.get_member_named('beta#3096'), guild.get_member_named("pika!#3722"), guild.get_member_named("Wooper#0478"), guild.get_member_named("WOOPBOT#4140")]
        for i in range(num_participants):
            try:
                await _participant.add_participant(interaction, db_tournament, member=members[i], respond=False)
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