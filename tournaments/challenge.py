from datetime import datetime
from discord import Button, Embed, Guild, Interaction, Member, Message, TextChannel, User
from guilds import guild as _guild
from pprint import pprint
from tournaments import leaderboard as _leaderboard, match as _match
from utils.color import GREEN, RED, WOOP_BLUE
from utils.common import CHALLENGES, GUILDS, ICON
from utils.logger import printlog
from utils import mdb
import discord
import pytz
import re

# challenge.py
# 1v1 challenges

type_match = re.compile(r'^[Bb][Oo][0-9]+$')
id_match = re.compile(r'^<@![0-9]+>$')

def find_challenge(db_guild: dict, challenge_id: int):
    """
    Retrieves and returns a challenge match document from the database (if it exists).
    """
    guild_challenges = db_guild['challenges']
    result = [challenge for challenge in guild_challenges if challenge['id'] == challenge_id]
    if result:
        return result[0]
    return None

def find_active_challenge_by_user(db_guild: dict, user_id: int):
    """
    Returns the active challenge match by a user in a guild (if it exists).
    """
    try:
        return list(filter(
            lambda challenge: not challenge['completed']
                and challenge['player1']['id'] == user_id, 
            db_guild['challenges']))[0]
    except:
        return None

async def create_challenge(interaction: Interaction, player_mention: str | None, best_of: int):
    """
    Creates a new challenge match between two players.
    If player_mention is None, waits for a challenger.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    player1: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    # Check if already has active challenge
    active_challenge = find_active_challenge_by_user(db_guild, player1.id)
    if active_challenge:
        await interaction.followup.send("You already have an active challenge.", ephemeral=True)
        return False

    # Parse arguments; default type = Bo3
    # usage = 'Usage: `$challenge create [type]`\nex. $challenge create 3'
    # Check number of rounds
    if best_of % 2 != 1 or best_of < 1: # must be odd
        await interaction.followup.send("There must be an positive odd number of rounds.", ephemeral=True)
        return False

    usage = f'Usage: `/challenge create [best_of] @[player_mention] `\nex. `/challenge create player_mention:` <@!{interaction.user.id}> `best_of: 3`'
    # Check for metioned user
    if player_mention is not None and len(player_mention.strip()) > 0:
        matched_id = id_match.search(player_mention)
        if matched_id:
            player2: Member = await guild.fetch_member(int(player_mention[3:-1]))
        else:
            await interaction.followup.send(f"Invalid player mention.\n{usage}", ephemeral=True)
            return False
    else:
        player2: Member = None

    player1_id = player1.id
    player1_name = player1.name
    player2_id = player2.id if player2 else None
    player2_name = player2.name if player2 else None

    new_challenge = {
        "id": None,
        "channel_id": interaction.channel.id,
        "player1": {
            "id": player1_id,
            "name": player1_name,
            "vote": None,
            "avatar_url": player1.display_avatar.url
        },
        "player2": {
            "id": player2_id,
            "name": player2_name,
            "vote": None
        },
        "best_of": best_of,
        "winner_emote": None,
        "open": player2 is None,
        "accepted": False,
        "completed": False
    }

    # Send embed message
    embed = create_challenge_embed(new_challenge)
    challenge_message: Message = await channel.send(
        content=f"<@!{player2.id}> has been challenged by <@!{player1.id}>!" if player_mention else "",
        embed=embed, 
        view=accept_view()
    )

    # Add challenge to database
    try:
        new_challenge['id'] = challenge_message.id
        await _guild.push_to_guild(guild, CHALLENGES, new_challenge)
    except Exception as e:
        printlog(f"Failed to add challenge ['id'='{challenge_message.id}'] to guild ['guild_id'='{guild.id}'].", e)
        if challenge_message: await challenge_message.delete()
        return None
    print(f"User '{player1.name}' ['id'='{player1.id}'] created new challenge ['id'='{new_challenge['id']}'].")
    await interaction.followup.send(f"Successfully created new challenge.", ephemeral=True)
    return new_challenge

async def cancel_challenge(interaction: Interaction, challenge_id: int, delete: bool=False):
    """
    Cancels an open challenge match.
    If delete option is True, deletes challenge regardless of status. Only available to guild admins or tournament managers.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    # Fetch challenge
    usage = 'Usage: `$challenge cancel [name]` or `$challenge delete [name]` (admins only)'
    db_challenge, challenge_id = await retrieve_valid_challenge(interaction, db_guild, challenge_id)
    if not db_challenge:
        return False
    # Cancel or Delete
    if not delete:
        if user.id != db_challenge['player1']['id'] or not user.guild_permissions.administrator:
            await interaction.followup.send(f"Only the author or server admins can cancel challenges.", ephemeral=True)
            return False
    else:
        if not user.guild_permissions.administrator:
            await interaction.followup.send(f"Only server admins can delete completed challenges.", ephemeral=True)
            return False
    # Check if in channel challenge was created in
    if db_challenge['channel_id'] != channel.id:
        await interaction.followup.send(f"Must be in the channel that the challenge was created in: <#{db_challenge['channel_id']}>", ephemeral=True)
        return False
    # Only cancel if not open
    if not delete:
        if db_challenge['accepted'] or db_challenge['completed']:
            await interaction.followup.send(f"You may not cancel challenges that are in progress or completed.", ephemeral=True)
            return False

    # Delete challenge message
    challenge_message: Message = await channel.fetch_message(challenge_id)
    await challenge_message.delete()
    # Delete challenge document
    try:
        result = await _guild.pull_from_guild(guild, CHALLENGES, db_challenge)
    except:
        print(f"Failed to delete challenge ['id'={challenge_id}].")
        return False
    if not result:
        print(f"Something went wrong when deleting challenge ['id'={challenge_id}].")
        return False
    print(f"User '{user.name}' [id={user.id}] cancelled/deleted challenge ['id'='{challenge_id}'].")
    await interaction.followup.send("Challenge has been successfully cancelled.", ephemeral=True)
    
    # Update leaderboard if deleting a completed match
    if delete and db_challenge['completed']:
        # Find the winner
        if db_challenge['winner_emote'] == '1️⃣':
            db_winner: dict = _leaderboard.find_leaderboard_user(db_guild, db_challenge['player1']['name'])
            db_loser: dict = _leaderboard.find_leaderboard_user(db_guild, db_challenge['player2']['name'])
        else:
            db_winner = _leaderboard.find_leaderboard_user(db_guild, db_challenge['player2']['name'])
            db_loser = _leaderboard.find_leaderboard_user(db_guild, db_challenge['player1']['name'])
        # Update records
        db_winner['matches'] = list(filter(lambda match_id: match_id != db_challenge['id'], db_winner['matches']))
        db_winner.update({'wins': db_winner['wins']-1})
        db_loser['matches'] = list(filter(lambda match_id: match_id != db_challenge['id'], db_winner['matches']))
        db_loser.update({'losses': db_loser['losses']-1})
        await _leaderboard.set_leaderboard_user(guild.id, db_winner['id'], db_winner)
        print(f"Removed win from leaderboard user ['name'='{db_winner['name']}'].")
        await _leaderboard.set_leaderboard_user(guild.id, db_loser['id'], db_loser)
        print(f"Removed loss from leaderboard user ['name'='{db_loser['name']}'].")
    return True

async def accept_challenge(interaction: Interaction):
    """
    Accepts an open challenge.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    message: Message = interaction.message
    message_id = message.id
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    challenge_message: Message = await channel.fetch_message(message_id)

    # Check if reaction was on a challenge message
    db_challenge: dict = find_challenge(db_guild, message_id)
    if not db_challenge:
        return False
    # Check if user created the challenge
    if db_challenge['player1']['id'] == user.id:
        await interaction.followup.send("You cannot accept your own challenge.", ephemeral=True)
        return False
    # Check if completed
    if db_challenge['completed']:
        await interaction.followup.send("This challenge has already been completed.", ephemeral=True)
        return False
    # Check if direct challenge
    if db_challenge['player2']['id'] is not None: # Direct challenge
        # Check if member reacting is the person being challenged
        if db_challenge['player2']['id'] != user.id:
            await interaction.followup.send("You are not the user being challenged.", ephemeral=True)
            return False
    else: # Queuing for challenge
        # Check if accepted
        if db_challenge['accepted']:
            await interaction.followup.send("This challenge has already been accepted.", ephemeral=True)
            return False

        # Check if open
        if not db_challenge['open']:
            await interaction.followup.send("This challenge is currently not open.", ephemeral=True)
            return False

        # Add user to challenge
        db_challenge['player2'] = {
            "id": user.id,
            "name": user.name,
            "vote": None
        }
    
    # Set to closed
    db_challenge.update({'open': False, 'accepted': datetime.now(tz=pytz.timezone('US/Eastern'))})
    # Update challenge in databse
    result = await set_challenge(guild.id, challenge_message.id, db_challenge)
    if not result:
        print(f"Failed to accept challenge ['id'='{message_id}'].")
        return False
    print(f"User ['name'='{user.name}'] accepted challenge ['id'='{db_challenge['id']}'] by '{db_challenge['player1']['name']}'.")
    # Update message embed and buttons
    updated_embed = edit_challenge_embed_start(challenge_message.embeds[0], db_challenge)
    await challenge_message.edit(embed=updated_embed, view=voting_buttons_view())
    await interaction.followup.send(f"You have accepted the challenge by <@{db_challenge['player1']['id']}>!", ephemeral=True)
    return True

async def vote_challenge_button(interaction: Interaction, button: Button):
    """
    Reports the winner for a challenge using reactions.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    message: Message = interaction.message
    message_id = message.id
    db_guild = await _guild.find_guild(guild.id)
    challenge_message: Message = await channel.fetch_message(message_id)

    # Check if reaction was on a challenge message
    db_challenge = find_challenge(db_guild, message_id)
    if not db_challenge:
        return False
    # Check if completed
    if db_challenge['completed']:
        return False

    # Call main vote_reaction function
    return await _match.vote_button(interaction, button, challenge_message, db_guild, db_challenge)

async def report_challenge(challenge_message: Message, db_guild: dict, db_challenge: dict, winner_emote: str, is_forfeit: bool=False):
    """
    Reports a challenge winner and updates the leaderboard
    """
    challenge_id = db_challenge['id']
    # Get winner object
    if winner_emote == '1️⃣':
        winner: dict = db_challenge['player1']
    elif winner_emote == '2️⃣':
        winner: dict = db_challenge['player2']

    # Update status in db
    try:
        db_challenge.update({'completed': datetime.now(tz=pytz.timezone('US/Eastern')), 'winner_emote': winner_emote})
        await set_challenge(db_guild['guild_id'], challenge_id, db_challenge)
    except Exception as e:
        printlog(f"Failed to report challenge ['id'={challenge_id}] in database.", e)
        return None, None
    
    # Update challenge embed
    challenge_embed = challenge_message.embeds[0]
    confirm_embed = _match.edit_match_embed_confirmed(challenge_embed, challenge_id, db_challenge['player1'], db_challenge['player2'], winner_emote, is_forfeit)
    confirm_embed.remove_field(1) # Remove votes field
    await challenge_message.edit(embed=confirm_embed, view=None)
    print("Succesfully reported challenge [id={0}]. Winner = '{1}'.".format(challenge_id, winner['name']))

    # Update leaderboard
    # Check if user(s) are already in leaderboard
    user1 = _leaderboard.find_leaderboard_user_by_id(db_guild, db_challenge['player1']['id'])
    if not user1:
        # Create new leaderboard user
        await _leaderboard.create_leaderboard_user(challenge_message.guild, db_challenge, db_challenge['player1'], winner_emote == '1️⃣')
    else:
        # Update existing leaderboard user
        await _leaderboard.update_leaderboard_user_score(challenge_message.guild.id, db_challenge, user1, winner_emote == '1️⃣')

    user2 = _leaderboard.find_leaderboard_user_by_id(db_guild, db_challenge['player2']['id'])
    if not user2:
        await _leaderboard.create_leaderboard_user(challenge_message.guild, db_challenge, db_challenge['player2'], winner_emote == '2️⃣')
    else:
        # Update existing leaderboard user
        await _leaderboard.update_leaderboard_user_score(challenge_message.guild.id, db_challenge, user2, winner_emote == '2️⃣')
    return True

async def override_challenge_result(interaction: Interaction, challenge_id: int, winner: str):
    """
    Overrides the results of a match. The status of the match does not matter.
    Only usable by tournament creator or tournament manager
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    usage = "Usage: `$challenge report <challenge_id> <entrant_name | 1️⃣ | 2️⃣>`"
    # Only allow guild admins to manually report results
    if not user.guild_permissions.administrator:
        await interaction.followup.send(f"Only the author or server admins can override challenge results.", ephemeral=True)
        return False
    # Check if provided emote
    valid1 = ['1', '1️⃣']
    valid2 = ['2', '2️⃣']
    winner_emote = None
    if winner in valid1:
        winner_emote = '1️⃣'
    elif winner in valid2:
        winner_emote = '2️⃣'
    # Get challenge
    try:
        db_challenge = find_challenge(db_guild, challenge_id)
    except Exception as e:
        printlog(f"Failed to find challenge ['id'='{challenge_id}'].", e)
        await interaction.followup.send(f"Something went wrong when finding the challenge.", ephemeral=True)
        return False
    if not db_challenge:
        await interaction.followup.send(f"Invalid challenge id.", ephemeral=True)
        return False
    # Check if challenge has been accepted
    if not db_challenge['accepted']:
        await interaction.followup.send(f"This challenge has not been accepted yet.", ephemeral=True)
        return False
    # Find by name if applicable
    if not winner_emote:
        player1 = db_challenge['player1']['id']
        player2 = db_challenge['player2']['id']
        if player1['name'].lower() == winner.lower():
            winner_emote = '1️⃣'
        elif player2['name'].lower() == winner.lower():
            winner_emote = '2️⃣'
        else:
            await interaction.followup.send(f"There is no entrant named '{winner}' in this challenge.\n{usage}", ephemeral=True)
            return False
    # Check if actually changing the winner
    if db_challenge['winner_emote'] is not None and winner_emote == db_challenge['winner_emote']:
        await interaction.followup.send("Challenge report failed; Winner is the same.", ephemeral=True)
        return False
    # Report match
    challenge_message = await interaction.channel.fetch_message(db_challenge['id'])
    try:
        await report_challenge(challenge_message, db_guild, db_challenge, winner_emote)
    except Exception as e:
        printlog(f"Failed to report match ['id'='{db_challenge['id']}']", e)
        return False
    printlog(f"User ['name'='{user.name}'] overwrote result for challenge ['id'='{db_challenge['id']}']. Winner: {winner['name']} {winner_emote}.")
    await interaction.followup.send(content=f"Challenge report successful. Winner: {winner['name']} {winner_emote}")
    return True

#######################
## MESSAGE FUNCTIONS ##
#######################

def create_challenge_embed(db_challenge: dict):
    """
    Creates embed object to include in challenge message.
    """
    player1_id = db_challenge['player1']['id']
    player1_name = db_challenge['player1']['name']
    player2_id = db_challenge['player2']['id']
    # Main embed
    embed = Embed(title=f"⚔️  Challenge - Best of {db_challenge['best_of']}", description=f"{player1_name} has issued a challenge!", color=WOOP_BLUE)
    # Author field
    embed.set_author(name="beta-bot | GitHub 🤖", url="https://github.com/fborja44/beta-bot", icon_url=ICON)
    # Challenge info field
    if not player2_id:
        embed.add_field(name=f"Waiting for Challenger...", value=f'1️⃣ <@{player1_id}> vs ??? 2️⃣', inline=False)
    else:
        embed.add_field(name=f"Players", value=f'1️⃣ <@{player1_id}> vs <@{player2_id}> 2️⃣', inline=False)
    # Challenge footer
    embed.set_footer(text=f"Created by {player1_name}\nchallenge_id: {db_challenge['id']}.")
    return embed

def edit_challenge_embed_start(embed: Embed, db_challenge: dict):
    """
    Edits an embed object for a challenge that has been started.
    """
    player1_id = db_challenge['player1']['id']
    player2_id = db_challenge['player2']['id']
    player1_vote = db_challenge['player1']['vote']
    player2_vote = db_challenge['player2']['vote']
    embed.color = GREEN
    # Update fields for live match
    embed.description += "\nAwaiting result..."
    embed.set_field_at(0, name=f"Players", value=f'1️⃣ <@{player1_id}> vs <@{player2_id}> 2️⃣', inline=False)
    # Challenge votes
    embed.add_field(name=f"Results Reporting", value=f'<@{player1_id}>: *{player1_vote}*\n<@{player2_id}>: *{player2_vote}*', inline=False)
    embed.set_footer(text=f"\nPlayers react with 1️⃣ or 2️⃣ to report the winner.\nmatch_id: {db_challenge['id']}")
    return embed

def edit_challenge_embed_dispute(embed: Embed):
    """
    Edits an embed object for disputes.
    """
    embed.add_field(name="🛑 Result Dispute 🛑", value="Contact a tournament manager or change vote to resolve.")
    embed.color = RED
    return embed

##################
## BUTTON VIEWS ##
##################

class accept_view(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Accept", emoji='🥊', style=discord.ButtonStyle.green, custom_id="accept_challenge")
    async def accept(self: discord.ui.View, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await accept_challenge(interaction)

    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="cancel_challenge")
    async def Cancel(self: discord.ui.View, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await cancel_challenge(interaction, interaction.message.id)

class voting_buttons_view(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(emoji='1️⃣', style=discord.ButtonStyle.grey, custom_id="vote_player1")
    async def vote_player1(self: discord.ui.View, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await vote_challenge_button(interaction, button)

    @discord.ui.button(emoji='2️⃣', style=discord.ButtonStyle.grey, custom_id="vote_player2")
    async def vote_player2(self: discord.ui.View, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await vote_challenge_button(interaction, button)

######################
## HELPER FUNCTIONS ##
######################

async def retrieve_valid_challenge(interaction: Interaction, db_guild: dict, challenge_id: int=None, send: bool=True):
    """"
    Parses arguments for tournament functions. Checks if there is a valid challenge.
    """
    # Get challenge from database
    if challenge_id:
        # Check if challenge exists
        db_challenge = find_challenge(db_guild, challenge_id)
        if not db_challenge:
            if send: 
                await interaction.followup.send(f"Something went wrong when finding the challenge.", ephemeral=True)
            return (None, None)
    else:
        # Get user's active match, if exists
        db_challenge = find_active_challenge_by_user(db_guild, interaction.user.id)
        if not db_challenge:
            if send: 
                await interaction.followup.send(f"You do not have any open challenges.", ephemeral=True)
            return (None, None)
        challenge_id = db_challenge['id']
    return (db_challenge, challenge_id)

async def set_challenge(guild_id: int, challenge_id: int, new_challenge: dict):
    """
    Sets a challenge in a guild to the specified document.
    """
    return await mdb.update_single_document(
        {'guild_id': guild_id, 'challenges.id': challenge_id}, 
        {'$set': {f'challenges.$': new_challenge}
        },
        GUILDS)

async def update_player(db_guild: dict, challenge_id: int, updated_player1=None, updated_player2=None):
    """
    Updates the players in a match.
    """
    db_challenge = find_challenge(db_guild, challenge_id)
    if updated_player1:
        db_challenge['player1'] = updated_player1
    if updated_player2:
        db_challenge['player2'] = updated_player2
    if not (updated_player1 or updated_player2):
        return None
    return await set_challenge(db_guild['guild_id'], challenge_id, db_challenge)