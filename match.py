from common import MATCHES, ICON
from datetime import datetime, timedelta, date
from discord import Button, Client, Embed, Guild, Interaction, Member, Message, RawReactionActionEvent, Reaction, TextChannel, User
from gridfs import Database
from logger import printlog
from pprint import pprint
import asyncio
import bracket as _bracket
import challenge as _challenge
import challonge
import discord
import guild as _guild
import mdb
import re

# match.py
# Bracket matches

def find_match(db_bracket: dict, match_id: int):
    """
    Retrieves and returns a match document from the database (if it exists).
    """
    bracket_matches = db_bracket['matches']
    result = [match for match in bracket_matches if match['id'] == match_id]
    if result:
        return result[0]
    return None

def find_match_by_challonge_id(db_bracket: dict, challonge_id: int):
    """
    Retrieves and returns a match document from the database (if it exists).
    """
    bracket_matches = db_bracket['matches']
    result = [match for match in bracket_matches if match['challonge_id'] == challonge_id]
    if result:
        return result[0]
    return None

async def create_match(channel: TextChannel, guild: Guild, db_bracket: dict, challonge_match):
    """
    Creates a new match in a bracket.
    """
    bracket_name = db_bracket['title']
    guild_id = guild.id
    # Create match message and embed
    # Get player names
    player1 = list(filter(lambda entrant: (entrant['challonge_id'] == challonge_match['player1_id']), db_bracket['entrants']))[0]
    player2= list(filter(lambda entrant: (entrant['challonge_id'] == challonge_match['player2_id']), db_bracket['entrants']))[0]
    player1_id = player1['id']
    player2_id = player2['id']

    new_match = {
        "id": None,
        "challonge_id": challonge_match['id'],
        "player1": {
            'id': player1['id'], 
            'vote': None
            },
        "player2": {
            'id': player2['id'], 
            'vote': None
            },
        "round": challonge_match['round'],
        'completed': False,
        "winner_emote": None,
        "next_matches" : []
    }

    # Send embed message
    embed = create_match_embed(db_bracket, new_match)
    match_message = await channel.send(f'<@{player1_id}> vs <@{player2_id}>', embed=embed, view=voting_buttons_view())

    # Add match document to database
    new_match['id'] = match_message.id
    try:
        await _bracket.add_to_bracket(guild_id, bracket_name, MATCHES, new_match)
        print(f"Added new match ['id'='{match_message.id}'] to bracket ['name'='{bracket_name}'].")
    except Exception as e:
        printlog(f"Failed to add match ['id'={new_match['id']}] to bracket ['name'='{bracket_name}'].", e)
        return None
    return new_match

async def delete_match(channel: TextChannel, db_bracket: dict, match_id: int):
    """
    Deletes a match.
    """
    guild: Guild = channel.guild
    guild_id = guild.id
    bracket_name = db_bracket['title']
    # Check if match is in database
    try:
        db_match = find_match(db_bracket, match_id)
    except:
        print("Something went wrong when checking database for match ['id'={match_id}].")
    if db_match:
        # Delete from matches
        try:
            await _bracket.remove_from_bracket(guild_id, bracket_name, MATCHES, match_id)
            print(f"Deleted match ['id'='{db_match['id']}'] from bracket ['name'='{bracket_name}'].")
        except:
            print(f"Failed to delete match [id='{match_id}'] from database.")
            return False
    # Delete match message
    try:
        match_message = await channel.fetch_message(db_match['id'])
        await match_message.delete() # delete message from channel
    except:
        printlog(f"Failed to delete message for match [id='{match_id}']. May not exist.")
        return False
    return True

async def vote_match_button(interaction: Interaction, button: Button):
    """
    Reports the winner for a bracket match using buttons.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    message: Message = interaction.message
    db_guild = await _guild.find_guild(guild.id)
    match_message: Message = await channel.fetch_message(message.id)

    # Get current active bracket, if any
    db_bracket = _bracket.find_active_bracket(db_guild)
    if not db_bracket:
        return False
    # Check if reaction was on a match message
    db_match = find_match(db_bracket, match_message.id)
    if not db_match or db_match['completed']:
        return False
    
    # Call main vote_reaction function
    return await vote_button(interaction, button, match_message, db_guild, db_match, db_bracket)

async def vote_button(interaction: Interaction, button: Button, match_message: Message,
                        db_guild: dict, db_match: dict, db_bracket: dict=None):
    """
    Main function for voting on match results by buttons.
    Used for matches or challenges.
    """
    match_type = "match" if db_bracket else "challenge"
    match_id = db_match['id']
    match_embed: Embed = match_message.embeds[0]
    user: Member = interaction.user
    # Defer response
    await interaction.response.defer(ephemeral=True)
    # Check if user was one of the players
    if user.id == db_match['player1']['id']:
        voter = db_match['player1']
    elif user.id == db_match['player2']['id']:
        voter = db_match['player2']
    else:
        await interaction.followup.send(f"You are not a player in this match.", ephemeral=True)
        return False
    # Check if match is open
    if db_match['completed']:
        await interaction.followup.send(f"Vote failed. This match has already been completed.", ephemeral=True)
        return False
    # Record vote or remove vote
    if voter['vote'] != button.emoji.name:
        vote = button.emoji.name
        action = "Added" if not voter['vote'] else "Changed"
    else:
        vote = None
        action = "Removed"
    # Update match player in database
    try:
        player1 = db_match['player1']
        player2 = db_match['player2']
        if voter == player1:
            player1['vote'] = vote
            if db_bracket:
                result = await update_player(db_guild['guild_id'], db_bracket, match_id, updated_player1=player1)
            else: 
                result = await _challenge.update_player(db_guild, match_id, updated_player1=player1)
            db_match['player1'] = player1
        else:
            player2['vote'] = vote
            if db_bracket:
                result = await update_player(db_guild['guild_id'], db_bracket, match_id, updated_player2=player2)
            else:
                result = await _challenge.update_player(db_guild, match_id, updated_player2=player2)
            db_match['player2'] = player2
        print(f"{action} vote by user ['discord_id'='{user.id}'] for {match_type} ['id'={match_id}']")
    except Exception as e:
        printlog(f"Failed to record vote by user ['discord_id'='{user.id}'] for {match_type} ['id'='{match_id}'].", e)
        await interaction.followup.send(f"Something went wrong while voting for {vote}.", ephemeral=True)
        return False
    if not result:
        print(f"Failed to update player while changing vote in {match_type} ['id'='{match_id}']")
        await interaction.followup.send(f"Something went wrong while voting for {vote}.", ephemeral=True)
        return False

    # Check if both players voted
    if player1['vote'] and player2['vote']:
        # Check who they voted for
        if player1['vote'] == player2['vote']:
            # Report match
            if db_bracket:
                await report_match(match_message, db_guild, db_bracket, db_match, vote)
            else:
                await _challenge.report_challenge(match_message, db_guild, db_match, vote)
        else:
            # Dispute has occurred
            printlog(f"Dispute detected in {match_type} ['id'='{match_id}'].")
            if db_bracket:
                dispute_embed = edit_match_embed_dispute(match_embed)
            else:
                dispute_embed = _challenge.edit_challenge_embed_dispute(match_embed)
            await match_message.edit(embed=dispute_embed)
    if vote:
        await interaction.followup.send(f"Successfully voted for {vote}.", ephemeral=True)
    else:
        await interaction.followup.send(f"Successfully removed vote.", ephemeral=True)
    return True

    # Otherwise, give other player 2 minutes to vote
    # if payload.event_type == 'REACTION_ADD': # TODO: Test what happens if other player votes between time
    #     await asyncio.sleep(10) # TODO: change to 120 seconds
    #     # REDO LOGIC:
    #     # Make sure vote is the same as previous
    #     # If there are no votes, then cancel
    #     match_embed.set_footer("")
    #     check_bracket = _bracket.find_active_bracket(db_guild)
    #     check_match = find_match(check_bracket, db_match['id'])
    #     if not (check_match['player1']['vote'] and check_match['player2']['vote']):
    #         if db_bracket:
    #             await report_match(match_message, db_guild, db_bracket, db_match, vote)
    #             print("Match vote timed out.")
    #         else:
    #             await _challenge.report_challenge(match_message, db_guild, db_match, vote)
    #             print("Match vote timed out.")
    # return True

async def report_match(match_message: Message, db_guild: dict, db_bracket: dict, db_match: dict, winner_emote: str, is_dq: bool=False):
    """
    Reports a match winner and fetches the next matches that have not yet been called.
    """
    bracket_name = db_bracket['title']
    bracket_challonge_id = db_bracket['challonge']['id']
    match_challonge_id = db_match['challonge_id']
    match_id = db_match['id']
    if winner_emote == '1️⃣':
        winner: dict = _bracket.find_entrant(db_bracket, db_match['player1']['id'])
        score = '1-0'
    elif winner_emote == '2️⃣':
        winner: dict = _bracket.find_entrant(db_bracket, db_match['player2']['id'])
        score = '0-1'
    # Update on challonge
    try:    
        challonge.matches.update(bracket_challonge_id, match_challonge_id, scores_csv=score, winner_id=winner['challonge_id'])
    except Exception as e:
        printlog(f"Something went wrong when reporting match ['challonge_id'={match_challonge_id}] on challonge.", e)
        return None, None
    # Update status in db
    try:
        db_match.update({'completed': datetime.now(), 'winner_emote': winner_emote})
        await set_match(db_guild['guild_id'], db_bracket, db_match)
    except Exception as e:
        printlog(f"Failed to report match ['id'={match_id}] in database.", e)
        return None, None

    # Update match embed
    match_embed = match_message.embeds[0]
    entrant1 = _bracket.find_entrant(db_bracket, db_match['player1']['id'])
    entrant2 = _bracket.find_entrant(db_bracket, db_match['player2']['id'])
    confirm_embed = edit_match_embed_confirmed(match_embed, match_challonge_id, entrant1, entrant2, winner_emote, is_dq)
    await match_message.edit(embed=confirm_embed, view=None)
    print("Succesfully reported match [id={0}]. Winner = '{1}'.".format(match_id, winner['name']))

    # Check for matches that have not yet been called
    try:
        challonge_matches = challonge.matches.index(db_bracket['challonge']['id'], state='open')
    except Exception as e:
        printlog("Failed to get new matches.", e)
        return None, None
    # Check if last match
    if len(challonge_matches) == 0 and db_match['round'] == db_bracket['num_rounds']:
        await match_message.channel.send(f"***{bracket_name}*** has been completed! Use `/bracket finalize {bracket_name}` to finalize the results!")
        return db_match, winner
    for challonge_match in challonge_matches:
        # Check if match has already been called (in database)
        try:
            check_match = find_match_by_challonge_id(db_bracket, challonge_match['id'])
        except:
            print("Failed to check match in database..")
            return None, None
        if check_match:
            continue
        new_match = await create_match(match_message.channel, match_message.guild, db_bracket, challonge_match)
        db_bracket['matches'].append(new_match)
        # Add new match message_id to old match's next_matches list
        try:
            db_match['next_matches'].append(new_match['id'])
            await set_match(db_guild['guild_id'], db_bracket, db_match)
            print(f"Added new match ['id'={new_match['id']}] to completed match's ['id'='{db_match['id']}'] next matches.")
        except Exception as e:
            print(f"Failed to add new match ['id'='{new_match['id']}'] to next_matches of match ['id'='{match_id}']")
            print(e)
    
    # Update bracket embed
    try:
        bracket_message: Message = await match_message.channel.fetch_message(db_bracket['id'])
        updated_bracket_embed = _bracket.create_bracket_image(db_bracket, bracket_message.embeds[0])
        await bracket_message.edit(embed=updated_bracket_embed)
    except Exception as e:
        printlog(f"Failed to create image for bracket ['name'='{bracket_name}'].", e)
    
    return db_match, winner
    
async def override_match_result(interaction: Interaction, match_challonge_id: int, winner: str):
    """
    Overrides the results of a match. The status of the match does not matter.
    Only usable by bracket creator or bracket manager
    """
    guild: Guild = interaction.guild
    message: Message = interaction.message
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    usage = "Usage: `$bracket report <match_id> <entrant_name | 1️⃣ | 2️⃣>`"
    # Defer response
    await interaction.response.defer()
    # if not winner_emote or not message.reference:
    #     await interaction.followup.send(usage, ephemeral=True)
    #     return False
    # Fetch active bracket
    db_bracket = _bracket.find_active_bracket(db_guild)
    if not db_bracket:
        await interaction.followup.send(f"There are currently no active brackets.", ephemeral=True)
        return False

    # Only allow author or guild admins to manually report results
    if user.id != db_bracket['author']['id'] or not user.guild_permissions.administrator:
        await interaction.followup.send(f"Only the author or server admins can override match results.", ephemeral=True)
        return False

    # Check if provided emote
    valid1 = ['1', '1️⃣']
    valid2 = ['2', '2️⃣']
    winner_emote = None
    if winner in valid1:
        winner_emote = '1️⃣'
    elif winner in valid2:
        winner_emote = '2️⃣'

    # Get match
    try:
        db_match = find_match_by_challonge_id(db_bracket, match_challonge_id)
    except Exception as e:
        printlog(f"Failed to find match ['challonge_id'='{match_challonge_id}'].", e)
        await interaction.followup.send(f"Something went wrong when finding the match.", ephemeral=True)
        return False
    if not db_match:
        await interaction.followup.send(f"Invalid challonge id.\n{usage}", ephemeral=True)
        return False

    # Find by name if applicable
    if not winner_emote:
        player1 = _bracket.find_entrant(db_bracket, db_match['player1']['id'])
        player2 = _bracket.find_entrant(db_bracket, db_match['player2']['id'])
        if player1['name'].lower() == winner.lower():
            winner_emote = '1️⃣'
        elif player2['name'].lower() == winner.lower():
            winner_emote = '2️⃣'
        else:
            # printlog(f"User ['name'='{entrant_name}']' is not an entrant in match ['id'='{match_id}'].")
            await interaction.followup.send(f"There is no entrant named '{winner}' in this match.\n{usage}", ephemeral=True)
            return False

    # Check if actually changing the winner
    if db_match['winner_emote'] is not None and winner_emote == db_match['winner_emote']:
        await interaction.followup.send("Match report failed; Winner is the same.", ephemeral=True)
        return False

    # Delete previously created matches
    next_matches = db_match['next_matches']
    if len(next_matches) > 0:
        for next_match_id in next_matches:
            try:
                await delete_match(message, db_bracket, next_match_id)
            except:
                print(f"Something went wrong when deleting match ['id'={next_match_id}] while deleting bracket ['name'={db_bracket['title']}].")

    # Report match
    match_message = await interaction.channel.fetch_message(db_match['id'])
    try:
        reported_match, winner = await report_match(match_message, db_guild, db_bracket, db_match, winner_emote)
    except Exception as e:
        printlog("bleh", e)
    printlog(f"User ['name'='{user.name}'] overwrote match ['id'='{db_match['id']}'] New winner: {winner['name']} {winner_emote}.")
    await interaction.followup.send(content=f"Match report successful. New winner: {winner['name']} {winner_emote}")
    return True

##################
## BUTTON VIEWS ##
##################

class voting_buttons_view(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(emoji='1️⃣', style=discord.ButtonStyle.grey, custom_id="vote_player1")
    async def vote_player1(self: discord.ui.View, interaction: discord.Interaction, button: discord.ui.Button):
        await vote_match_button(interaction, button)

    @discord.ui.button(emoji='2️⃣', style=discord.ButtonStyle.grey, custom_id="vote_player2")
    async def vote_player2(self: discord.ui.View, interaction: discord.Interaction, button: discord.ui.Button):
        await vote_match_button(interaction, button)

######################
## HELPER FUNCTIONS ##
######################

async def update_player(guild_id: int, db_bracket: dict, match_id: int, 
                            updated_player1=None, updated_player2=None):
    """
    Updates the players in a match.
    """
    bracket_name = db_bracket['title']
    match_index = _bracket.find_index_in_bracket(db_bracket, MATCHES, 'id', match_id)
    if updated_player1:
        db_bracket['matches'][match_index]['player1'] = updated_player1
    if updated_player2:
        db_bracket['matches'][match_index]['player2'] = updated_player2
    if not (updated_player1 or updated_player2):
        return None
    return await _bracket.set_bracket(guild_id, bracket_name, db_bracket)

async def set_match(guild_id: int, db_bracket: dict, db_match: dict):
    """
    Updates the players in a match.
    """
    bracket_name = db_bracket['title']
    match_index = _bracket.find_index_in_bracket(db_bracket, MATCHES, 'id', db_match['id'])
    db_bracket['matches'][match_index] = db_match
    return await _bracket.set_bracket(guild_id, bracket_name, db_bracket)

#######################
## MESSAGE FUNCTIONS ##
#######################

def create_match_embed(db_bracket: dict, db_match: dict):
    """
    Creates embed object to include in match message.
    """
    bracket_name = db_bracket['title']
    match_challonge_id = db_match['challonge_id']
    jump_url = db_bracket['jump_url']
    round = db_match['round']
    player1_id = db_match['player1']['id']
    player2_id = db_match['player2']['id']
    time = datetime.now().strftime("%#I:%M %p %Z")
    round_name = get_round_name(db_bracket, match_challonge_id, round)
    embed = Embed(title=f"⚔️ {round_name}", description=f"Awaiting result...\nOpened at {time}", color=0x50C878)
    embed.set_author(name=bracket_name, url=jump_url, icon_url=ICON)
    if round_name == "Grand Finals Set 1":
        embed.add_field(name=f"Players", value=f'1️⃣ [W] <@{player1_id}> vs <@{player2_id}> [L] 2️⃣', inline=False)
    elif round_name == "Grand Finals Set 2":
        embed.add_field(name=f"Players", value=f'1️⃣ [L] <@{player1_id}> vs <@{player2_id}> [L] 2️⃣', inline=False)
    else: 
        embed.add_field(name=f"Players", value=f'1️⃣ <@{player1_id}> vs <@{player2_id}> 2️⃣', inline=False)
    # embed.add_field(name=f'Bracket Link', value=url, inline=False)
    embed.set_footer(text=f"Players vote with 1️⃣ or 2️⃣ to report the winner.\nmatch_id: {match_challonge_id}")
    return embed

def edit_match_embed_dispute(embed: Embed):
    """
    Updates embed object for disputes.
    """
    embed.add_field(name="🛑 Result Dispute 🛑", value="Contact a bracket manager or change vote to resolve.")
    embed.color = 0xD4180F
    return embed

def edit_match_embed_confirmed(embed: Embed, match_id: int, player1: dict, player2: dict, winner_emote: str, is_dq: bool=False):
    """
    Updates embed object for confirmed match.
    For tournament bracket matches, match_id is the challonge_id.
    For 1v1 challenge matches, match_id is the id (message_id).
    """
    time = datetime.now().strftime("%#I:%M %p %Z")
    player1_id = player1['id']
    player2_id = player2['id']

    if winner_emote == '1️⃣':
        winner = player1
        player1_emote = '⭐'
        player2_emote = '❌' if not is_dq else '🇩🇶'
    else:
        winner = player2
        player2_emote = '⭐'
        player1_emote = '❌' if not is_dq else '🇩🇶'
    embed.description = f"Winner: **{winner['name']}**\nFinished at {time}"
    embed.set_field_at(index=0, name=f"Players", value=f'{player1_emote} <@{player1_id}> vs <@{player2_id}> {player2_emote}', inline=False)
    if len(embed.fields) > 1:
        # Remove dispute field
        embed.remove_field(1)
    embed.set_footer(text=f"Result finalized. To change result, contact a bracket manager.\nmatch_id: {match_id}")
    embed.color = 0x000000
    return embed

def get_round_name(db_bracket: dict, match_id: int, round: int):
    """
    Returns string value of round number based on number of rounds in a bracket.
    """
    num_rounds = db_bracket['num_rounds']
    if round > 0:
        # Winners Bracket
        match num_rounds - round:
            case 0:
                if db_bracket['tournament_type'] == "double elimination":
                    try:
                        matches = challonge.matches.index(db_bracket['challonge']['id'])
                        matches.sort(reverse=True, key=(lambda match: match['id']))
                        print(matches[0]['id'])
                        if match_id != matches[0]['id']:
                            return "Grand Finals Set 1"
                        else:
                            return "Grand Finals Set 2"
                    except:
                        return "Grand Finals"
                    else:
                        return "Grand Finals"
            case 1:
                return "Winners Finals"
            case 2:
                return "Winners Semifinals"
            case 3: 
                return "Winners Quarterfinals"
            case _:
                return f"Winners Round {round}"
    else:
        # Losers Bracket
        match abs(num_rounds - round):
            case 0:
                return "Losers Finals"
            case 1:
                return "Losers Semiinals"
            case 2:
                return "Losers Quarterfinals"
            case _:
                return f"Losers Round {abs(round)}"