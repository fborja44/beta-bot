from discord import Embed, Guild, ForumChannel, Interaction, Message, Member, TextChannel, Thread
from pprint import pprint
from tournaments import match as _match, tournament as _tournament
from guilds import guild as _guild
from utils.logger import printlog
import challonge
import re

# participant.py
# Tournament participant functions

user_match = re.compile(r'^<@[0-9]+>$')

def find_participant(db_tournament: dict, participant_id):
    """
    Returns an participant in a tournament by id.
    """
    result = [participant for participant in db_tournament['participants'] if participant['id'] == participant_id]
    if result:
        return result[0]
    return None

async def join_tournament(interaction: Interaction, tournament_title: str):
    """
    Join a tournament through command instead of button.
    """
    guild: Guild = interaction.guild
    db_guild = await _guild.find_add_guild(guild)
    # Fetch tournament
    db_tournament, tournament_title = await _tournament.retrieve_valid_tournament(interaction, db_guild, tournament_title)   
    if not db_tournament:
        return False
    # Check if in valid channel
    if not await _tournament.valid_tournament_thread(db_tournament, interaction):
        return False
    await add_participant(interaction, db_tournament)

async def leave_tournament(interaction: Interaction, tournament_title: str):
    """
    Leave a tournament through command instead of button.
    """
    guild: Guild = interaction.guild
    db_guild = await _guild.find_add_guild(guild)
    # Fetch tournament
    db_tournament, tournament_title = await _tournament.retrieve_valid_tournament(interaction, db_guild, tournament_title)   
    if not db_tournament:
        return False
    # Check if in valid channel
    if not await _tournament.valid_tournament_thread(db_tournament, interaction):
        return False
    await remove_participant(interaction, db_tournament)

async def add_participant(interaction: Interaction, db_tournament: dict=None, member: Member=None, respond: bool=True):
    """
    Adds an participant to a tournament.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    message: Message = interaction.message
    user: Member = member or interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Fetch tournament
    db_tournament = db_tournament or _tournament.find_tournament_by_id(db_guild, message.id)
    if not db_tournament or not db_tournament['open']:
        if respond: await interaction.followup.send(f"'***{tournament_title}***' is not open for registration.", ephemeral=True)
        return False 
    tournament_title = db_tournament['title']
    participant_ids = [] # list of participant names
    for participant in db_tournament['participants']:
        participant_ids.append(participant['id'])
    challonge_id = db_tournament['challonge']['id']
    # Check if already in participants list
    if user.id in participant_ids:
        # printlog(f"User ['name'='{user.name}']' is already registered as an participant in tournament ['title'='{tournament_title}'].")
        if respond: await interaction.followup.send(f"You have already joined '***{tournament_title}***'.", ephemeral=True)
        return False
    # Check if tournament is at capacity
    if db_tournament['max_participants'] and db_tournament['max_participants'] == len(db_tournament['participants']):
        if respond: await interaction.followup.send(f"Unable to join '***{tournament_title}***'. Tournament has reached maximum participants.")
        return False
    # Add user to challonge tournament
    try:
        response = challonge.participants.create(challonge_id, user.name)
    except Exception as e:
        printlog(f"Failed to add user ['name'='{user.name}'] to challonge tournament. User may already exist.", e)
        if respond: await interaction.followup.send(f"Something went wrong when trying to join '***{tournament_title}***'.", ephemeral=True)
        return False
    # Add user to participants list
    new_participant = {
        'id': user.id, 
        'challonge_id': response['id'],
        'name': user.name, 
        'seed': response['seed'],
        'placement': None,
        'active': True,
        }
    try:
        updated_guild = await _tournament.add_to_tournament(guild.id, tournament_title, 'participants', new_participant)
        db_tournament['participants'].append(new_participant)
    except:
        print(f"Failed to add user '{user.name}' to tournament ['title'='{tournament_title}'] participants.")
        if respond: await interaction.followup.send(f"Something went wrong when trying to join '***{tournament_title}***'.", ephemeral=True)
        return False
    if updated_guild:
        print(f"Added participant '{user.name}' ['id'='{user.id}'] to tournament ['title'='{tournament_title}'].")
        # Update message
        await _tournament.edit_tournament_message(db_tournament, channel)
        # Update thread if applicable
        # if db_tournament['thread_id'] is not None:
        #     tournament_thread: Thread = guild.get_thread(db_tournament['thread_id'])
        #     await tournament_thread.edit(name=f"🥊 {tournament_title} - {db_tournament['tournament_type'].title()} ({len(db_tournament['participants'])} of {db_tournament['max_participants']})")
    else:
        print(f"Failed to add participant '{user.name}' ['id'='{user.id}'] to tournament ['title'='{tournament_title}'].")
        if respond: await interaction.followup.send(f"Something went wrong when trying to join '***{tournament_title}***'.", ephemeral=True)
        return False
    if respond: await interaction.followup.send(f"Successfully joined '***{tournament_title}***'.", ephemeral=True)
    return True

async def remove_participant(interaction: Interaction, db_tournament: dict=None, member: Member=None, respond: bool=True):
    """
    Destroys an participant from a tournament.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    message: Message = interaction.message
    user: Member = member or interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Fetch tournament
    db_tournament = db_tournament or _tournament.find_tournament_by_id(db_guild, message.id)
    if not db_tournament or not db_tournament['open']:
        return False 
    # Remove user from challonge tournament
    tournament_title = db_tournament['title']
    participant_names = [] # list of participant names
    for participant in db_tournament['participants']:
        participant_names.append(participant['id'])
    challonge_id = db_tournament['challonge']['id']
    tournament_id = db_tournament['id']
    # Check if already in participants list
    if user.id not in participant_names:
        printlog(f"User ['id'='{user.id}']' is not registered as an participant in tournament ['title'='{tournament_title}'].")
        if respond: await interaction.followup.send(f"You are not registered for '***{tournament_title}***'.", ephemeral=True)
        return False
    db_participant = list(filter(lambda participant: participant['id'] == user.id, db_tournament['participants']))[0]
    try:
        challonge.participants.destroy(challonge_id, db_participant['challonge_id'])
    except Exception as e:
        printlog(f"Failed to remove user ['name'='{db_participant['name']}'] from challonge tournament. User may not exist.", e)
        if respond: await interaction.followup.send(f"Something went wrong when trying to leave '***{tournament_title}***'.", ephemeral=True)
        return False
    # Remove user from participants list
    try:
        updated_guild = await _tournament.remove_from_tournament(channel.guild.id, tournament_title, 'participants', db_participant['id'])
        db_tournament['participants'] = list(filter(lambda participant: participant['id'] != user.id, db_tournament['participants']))
    except:
        print(f"Failed to remove user '{db_participant['name']}' from tournament ['title'='{tournament_title}'] participants.")
        if respond: await interaction.followup.send(f"Something went wrong when trying to leave '***{tournament_title}***'.", ephemeral=True)
        return False
    if updated_guild:
        print(f"Removed participant ['name'='{db_participant['name']}']from tournament [id='{tournament_id}'].")
        # Update message
        await _tournament.edit_tournament_message(db_tournament, channel)
        # Update thread if applicable
        # if db_tournament['thread_id'] is not None:
        #     tournament_thread: Thread = guild.get_thread(db_tournament['thread_id'])
        #     await tournament_thread.edit(name=f"🥊 {tournament_title} - {db_tournament['tournament_type'].title()} ({len(db_tournament['participants'])} of {db_tournament['max_participants']})")
    else:
        print(f"Failed to remove participant ['name'='{db_participant['name']}']from tournament [id='{tournament_id}'].")
        if respond: await interaction.followup.send(f"Something went wrong when trying to leave '***{tournament_title}***'.", ephemeral=True)
        return False
    if respond: await interaction.followup.send(f"Successfully removed from '***{tournament_title}***'.", ephemeral=True)
    return True

async def randomize_seeding(interaction: Interaction, tournament_title: str=""):
    """
    Randomizes the seeding for a tournament bracket.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # usage = 'Usage: `$tournament dq <participant name>`. There must be an active tournament, or must be in a reply to a tournament message.'
    # Retrieve tournament
    db_tournament, tournament_title = await _tournament.retrieve_valid_tournament(interaction, db_guild, tournament_title)
    if not db_tournament:
        return False
    challonge_id = db_tournament['challonge']['id']
    # Only allow author or guild admins to update seeding
    if user != db_tournament['author']['id'] and not user.guild_permissions.administrator:
        await interaction.followup.send(f"Only the author or server admins can update tournament seeding.", ephemeral=True)
        return False
    # Check if in valid channel
    if not await _tournament.valid_tournament_channel(db_tournament, interaction):
        return False
    # Check if tournament has already been started.
    if not db_tournament['open'] or db_tournament['completed']:
        await interaction.followup.send(f"Seeding may only be updated during the registration phase.", ephemeral=True)
        return False
    # Randomize seeding on challonge
    try:
        challonge.participants.randomize(challonge_id)
        result = challonge.participants.index(challonge_id)
    except:
        printlog(f"Failed to randomize seeding for tournament ['title'='{tournament_title}'] on challonge.")
        return False
    # Update seeding in db
    for ch_participant in result:
        p_index = _tournament.find_index_in_tournament(db_tournament, 'participants', 'challonge_id', ch_participant['id'])
        db_tournament['participants'][p_index].update({'seed': ch_participant['seed']})
    await _tournament.set_tournament(guild.id, tournament_title, db_tournament)
    print(f"User ['name'='{user.name}'] randomized seeding in tournament ['title'='{tournament_title}'].")
    await interaction.followup.send("Succesfully randomized seeding for '***{tournament_title}***'.")
    return True

async def set_seed(interaction: Interaction, user_mention: str, seed: int, tournament_title: str=""):
    """
    Sets the seed for a participant.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # usage = 'Usage: `$tournament dq <participant name>`. There must be an active tournament, or must be in a reply to a tournament message.'
    # Retrieve tournament
    db_tournament, tournament_title = await _tournament.retrieve_valid_tournament(interaction, db_guild, tournament_title)
    if not db_tournament:
        return False
    challonge_id = db_tournament['challonge']['id']
    # Check if in valid channel
    if not await _tournament.valid_tournament_channel(db_tournament, interaction):
        return False
    # Only allow author, guild admins, or self to dq a user
    if user.id != db_tournament['author']['id'] and not user.guild_permissions.administrator and user.id != participant.id:
        await interaction.followup.send(f"Only the author or server admins can disqualify/remove participants from tournaments, or participants must disqualify/remove themselves.", ephemeral=True)
        return False
    # Check if valid participant mention
    participant: Member = parse_user_mention(interaction, user_mention)
    if not participant:
        await interaction.followup.send(f"Invalid user mention for `user_mention`. ex. <@{interaction.client.user.id}>", ephemeral=True)
        return False
    # Check if tournament has already been started.
    if not db_tournament['open'] or db_tournament['completed']:
        await interaction.followup.send(f"Seeding may only be updated during the registration phase.", ephemeral=True)
        return False
    # Check if participant exists
    # TODO: make into own function
    participant_name = participant.name
    db_participant = None
    for elem in db_tournament['participants']:
        if elem['name'].lower() == participant_name.lower():
            db_participant = elem
    if not db_participant:
        printlog(f"User ['name'='{participant_name}']' is not an participant in tournament ['title'='{tournament_title}'].")
        await interaction.followup.send(f"There is no participant named '{participant_name}' in '***{tournament_title}***'.")
        return False
    elif not db_participant['active']:
        await interaction.followup.send(f"Participant '{participant_name}' has already been disqualified from '***{tournament_title}***'.", ephemeral=True)
        return False
    # Check if valid seed
    num_entrants = len(db_tournament['participants'])
    if seed <= 0 or seed > num_entrants:
        await interaction.followup.send(f"Invalid seed. Must be greater than 0 and less than or equal to the number of participants'.")
        return False
    # Update seed on challonge
    try:
        challonge.participants.update(challonge_id, db_participant['challonge_id'], seed=seed)
    except:
        printlog(f"Failed to update seed for user ['name'='{participant_name}'] in  tournament ['title'='{tournament_title}'] on challonge.")
        return False
    # Update seed in db
    p_index = _tournament.find_index_in_tournament(db_tournament, 'participants', 'challonge_id', db_participant['challonge_id'])
    db_tournament['participants'][p_index].update({'seed': seed})
    await _tournament.set_tournament(guild.id, tournament_title, db_tournament)
    await interaction.followup.send(f"Succesfully updated seed for <@{participant.id}> to **{seed}**.", ephemeral=True)
    print(f"User ['name'='{user.name}'] updated seed for participant ['name'='{participant_name}'] in tournament ['title'='{tournament_title}'].")
    return True

async def disqualify_participant_main(interaction: Interaction, user_mention: str, tournament_title: str=""):
    """
    Destroys an participant from a tournament or DQs them if the tournament has already started from a command.
    Main function.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # usage = 'Usage: `$tournament dq <participant name>`. There must be an active tournament, or must be in a reply to a tournament message.'
    # Retrieve tournament
    db_tournament, tournament_title = await _tournament.retrieve_valid_tournament(interaction, db_guild, tournament_title)
    if not db_tournament:
        return False
    # Check if in valid channel
    if not await _tournament.valid_tournament_thread(db_tournament, interaction):
        return False
    # Only allow author, guild admins, or self to dq a user
    if user.id != db_tournament['author']['id'] and not user.guild_permissions.administrator and user.id != participant.id:
        await interaction.followup.send(f"Only the author or server admins can disqualify/remove participants from tournaments, or participants must disqualify/remove themselves.", ephemeral=True)
        return False
    # Check if valid participant mention
    participant: Member = parse_user_mention(interaction, user_mention)
    if not participant:
        await interaction.followup.send(f"Invalid user mention for `user_mention`. ex. <@{interaction.client.user.id}>", ephemeral=True)
        return False
    tournament_title = db_tournament['title']
    # Check if participant exists
    participant_name = participant.name
    db_participant = None
    for elem in db_tournament['participants']:
        if elem['name'].lower() == participant_name.lower():
            db_participant = elem
    if not db_participant:
        printlog(f"User ['name'='{participant_name}']' is not an participant in tournament ['title'='{tournament_title}'].")
        await interaction.followup.send(f"There is no participant named '{participant_name}' in '***{tournament_title}***'.")
        return False
    elif not db_participant['active']:
        await interaction.followup.send(f"Participant '{participant_name}' has already been disqualified from '***{tournament_title}***'.", ephemeral=True)
        return False

    # If tournament is still in registration phase, just remove from tournament
    if db_tournament['open']:
        participant: Member = await interaction.guild.fetch_member(db_participant['id'])
        await remove_participant(interaction, db_tournament, participant, respond=False)
        await interaction.followup.send(f"Successfully removed participant from '***{tournament_title}***'.", ephemeral=True)
        print(f"User ['name'='{user.name}'] manually removed participant.")
        return True

    # Call dq helper function
    await disqualify_participant(channel, db_guild, db_tournament, db_participant)
    await interaction.followup.send(f"'{db_participant['name']}' was disqualified from '***{tournament_title}***'.")
    print(f"User ['name'='{user.name}'] manually disqualified participant.")
    return True

async def disqualify_participant(channel: TextChannel, db_guild: dict, db_tournament: dict, db_participant: dict):
    """
    Function to dq an participant in the database and challonge. Updates messages.
    """
    tournament_title = db_tournament['title']
    challonge_id = db_tournament['challonge']['id']
    participant_name = db_participant['name']
    db_participant['active'] = False
    participant_index = _tournament.find_index_in_tournament(db_tournament, 'participants', 'id', db_participant['id'])
    db_tournament['participants'][participant_index] = db_participant
    
    # Update participant in database
    try:
        await _tournament.set_tournament(db_guild['guild_id'], tournament_title, db_tournament)
    except:
        print("Failed to DQ participant in database.")
        return False
    # Disqualify participant on challonge
    try:
        challonge.participants.destroy(challonge_id, db_participant['challonge_id'])
    except Exception as e:
        printlog(f"Failed to DQ participant ['name'='{participant_name}'] from tournament ['title'='{tournament_title}']", e)
        return False

    # Update all open matches
    winner_emote = None
    for tournament_match in db_tournament['matches']:
        # Get match document
        db_match = _match.find_match(db_tournament, tournament_match['id'])
        # Check if match is open
        if db_match['completed']:
            continue
        # Check the players; Other player wins
        if db_match['player1']['id'] == db_participant['id']:
            winner_emote = '2️⃣'
            break
        elif db_match['player2']['id'] == db_participant['id']:
            winner_emote = '1️⃣'
            break
    if winner_emote:
        # Report match
        match_message = await channel.fetch_message(db_match['id'])
        await _match.report_match(match_message, db_guild, db_tournament, db_match, winner_emote, is_dq=True)
    return True

######################
## HELPER FUNCTIONS ##
######################

def parse_user_mention(interaction: Interaction, user_mention: str):
    """
    Parses a channel mention argument.
    """
    if user_mention is not None and len(user_mention.strip()) > 0:
        matched_user_id = user_match.search(user_mention)
        if matched_user_id:
            return interaction.guild.get_member(int(user_mention[2:-1])) or None
        else:
            return None
    else: 
        return interaction.user