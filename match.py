from common import MATCHES, ICON
from datetime import datetime, timedelta, date
from discord import Client, Embed, Guild, Message, RawReactionActionEvent, Reaction, TextChannel, User
from gridfs import Database
from logger import printlog
from pprint import pprint
import asyncio
import bracket as _bracket
import challenge as _challenge
import challonge
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

async def create_match(self: Client, message: Message, db: Database, guild: Guild, db_bracket: dict, challonge_match):
    """
    Creates a new match in a bracket.
    """
    bracket_name = db_bracket['name']
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
    match_message = await message.channel.send(f'<@{player1_id}> vs <@{player2_id}>', embed=embed)
    # React to match message
    await match_message.add_reaction('1️⃣')
    await match_message.add_reaction('2️⃣')

    # Add match document to database
    new_match['id'] = match_message.id
    try:
        updated_guild = await _bracket.add_to_bracket(db, guild_id, bracket_name, MATCHES, new_match)
        print(f"Added new match ['id'='{match_message.id}'] to bracket ['name'='{bracket_name}'].")
    except Exception as e:
        printlog(f"Failed to add match ['id'={new_match['id']}] to bracket ['name'='{bracket_name}'].", e)
        return None
    return new_match

async def delete_match(self: Client, message: Message, db: Database, db_bracket: dict, match_id: int):
    """
    Deletes a match.
    """
    guild: Guild = message.channel.guild
    guild_id = guild.id
    bracket_name = db_bracket['name']
    # Check if match is in database
    try:
        db_match = find_match(db_bracket, match_id)
    except:
        print("Something went wrong when checking database for match ['id'={match_id}].")
    if db_match:
        # Delete from matches
        try:
            updated_guild = await _bracket.remove_from_bracket(db, guild_id, bracket_name, MATCHES, match_id)
            print(f"Deleted match ['id'='{db_match['id']}'] from bracket ['name'='{bracket_name}'].")
        except:
            print(f"Failed to delete match [id='{match_id}'] from database.")
            return False
    # Delete match message
    try:
        match_message = await message.channel.fetch_message(db_match['id'])
        await match_message.delete() # delete message from channel
    except:
        printlog(f"Failed to delete message for match [id='{match_id}']. May not exist.")
        return False
    return True

async def vote_match_reaction(self: Client, payload: RawReactionActionEvent, db: Database):
    """
    Reports the winner for a match using reactions.
    """
    channel: TextChannel = await self.fetch_channel(payload.channel_id)
    guild: Guild = await self.fetch_guild(payload.guild_id)
    db_guild = await _guild.find_guild(self, db, guild.id)
    match_message: Message = await channel.fetch_message(payload.message_id)

    # Get current active bracket, if any
    db_bracket = _bracket.find_active_bracket(db_guild)
    if not db_bracket:
        return False
    # Check if reaction was on a match message
    db_match = find_match(db_bracket, match_message.id)
    if not db_match or db_match['completed']:
        return False
    
    # Call main vote_reaction function
    return await vote_reaction(self, payload, match_message, db, db_guild, db_match, db_bracket)

async def vote_reaction(self: Client, payload: RawReactionActionEvent, match_message: Message, db: Database, 
                        db_guild: dict, db_match: dict, db_bracket: dict=None):
    """
    Main function for voting on match results by reaction
    """
    match_type = "match" if db_bracket else "challenge"
    match_id = db_match['id']
    match_embed = match_message.embeds[0]
    member = match_message.channel.guild.get_member(payload.user_id)

    # Check if user was one of the players
    if payload.user_id == db_match['player1']['id']:
        voter = db_match['player1']
    elif payload.user_id == db_match['player2']['id']:
        voter = db_match['player2']
    else:
        # Remove reaction
        await match_message.remove_reaction(payload.emoji, member)
        return False

    # Record vote or remove vote
    if payload.event_type == 'REACTION_ADD':
        vote = payload.emoji.name
        action = "Added" if not voter['vote'] else "Changed"
        # Remove other vote if applicable
        if vote == '1️⃣':
            await match_message.remove_reaction('2️⃣', member)
        elif vote == '2️⃣':
            await match_message.remove_reaction('1️⃣', member)
    elif payload.event_type == 'REACTION_REMOVE':
        if voter['vote'] == payload.emoji.name: # Removed vote
            vote = None
        else:
            return False # Switched vote
        action = "Removed"
    # Update match player in database
    try:
        player1 = db_match['player1']
        player2 = db_match['player2']
        if voter == db_match['player1']:
            player1['vote'] = vote
            if db_bracket:
                result = await update_player(db, db_guild['guild_id'], db_bracket, match_id, updated_player1=player1)
            else: 
                result = await _challenge.update_player(db, db_guild, match_id, updated_player1=player1)
            db_match['player1'] = player1
        else:
            player2['vote'] = vote
            if db_bracket:
                result = await update_player(db, db_guild['guild_id'], db_bracket, match_id, updated_player2=player2)
            else:
                result = await _challenge.update_player(db, db_guild, match_id, updated_player2=player2)
            db_match['player2'] = player2
        print(f"{action} vote by user ['discord_id'='{payload.user_id}'] for {match_type} ['id'={match_id}']")
    except Exception as e:
        printlog(f"Failed to record vote by user ['discord_id'='{payload.user_id}'] for {match_type} ['id'='{match_id}'].", e)
        return False
    if not result:
        print(f"Failed to update player while changing vote in {match_type} ['id'='{match_id}']")
        return False

    # Check if both players voted
    if player1['vote'] and player2['vote']:
        # Check who they voted for
        if player1['vote'] == player2['vote']:
            # Report match
            if db_bracket:
                await report_match(self, match_message, db, match_message.guild, db_bracket, db_match, vote)
            else:
                await _challenge.report_challenge(self, match_message, db, match_message.guild, db_match, vote)
        else:
            # Dispute detected
            printlog(f"Dispute detected in {match_type} ['id'='{match_id}'].")
            if db_bracket:
                dispute_embed = edit_match_embed_dispute(match_embed)
            else:
                dispute_embed = _challenge.edit_challenge_embed_dispute(match_embed)
            await match_message.edit(embed=dispute_embed)
    return True

async def report_match(self: Client, match_message: Message, db: Database, guild: Guild, db_bracket: dict, db_match: dict, winner_emote: str, is_dq: bool=False):
    """
    Reports a match winner and fetches the next matches that have not yet been called.
    """
    bracket_name = db_bracket['name']
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
        updated_match = await set_match(db, guild.id, db_bracket, db_match)
    except:
        print(f"Failed to report match ['id'={match_id}] in database.")
        return None, None

    # Update match embed
    match_embed = match_message.embeds[0]
    entrant1 = _bracket.find_entrant(db_bracket, db_match['player1']['id'])
    entrant2 = _bracket.find_entrant(db_bracket, db_match['player2']['id'])
    confirm_embed = edit_match_embed_confirmed(match_embed, entrant1, entrant2, winner_emote, is_dq)
    await match_message.edit(embed=confirm_embed)
    print("Succesfully reported match [id={0}]. Winner = '{1}'.".format(match_id, winner['name']))

    # Check for matches that have not yet been called
    try:
        challonge_matches = challonge.matches.index(db_bracket['challonge']['id'], state='open')
    except Exception as e:
        printlog("Failed to get new matches.", e)
        return None, None
    # Check if last match
    if len(challonge_matches) == 0 and db_match['round'] == db_bracket['num_rounds']:
        await match_message.channel.send(f"***{bracket_name}*** has been completed! Use `$bracket finalize {bracket_name}` to finalize the results!")
        return db_match, winner
    for challonge_match in challonge_matches:
        # Check if match has already been called (in database)
        try:
            check_match = find_match_by_challonge_id(db_bracket, challonge_match['id'])
        except:
            print("Failed to check match in database..")
            return None, None
        if check_match:
            print("match found")
            continue
        new_match = await create_match(self, match_message, db, guild, db_bracket, challonge_match)
        db_bracket['matches'].append(new_match)
        # Add new match message_id to old match's next_matches list
        try:
            db_match['next_matches'].append(new_match['id'])
            await set_match(db, guild.id, db_bracket, db_match)
            print(f"Added new match ['id'={new_match['id']}] to completed match's ['id'='{db_match['id']}'] next matches.")
        except:
            print(f"Failed to add new match ['id'='{new_match['id']}'] to next_matches of match ['id'='{match_id}']")
    
    # Update bracket embed
    try:
        bracket_message: Message = await match_message.channel.fetch_message(db_bracket['id'])
        updated_bracket_embed = _bracket.create_bracket_image(db_bracket, bracket_message.embeds[0])
        await bracket_message.edit(embed=updated_bracket_embed)
    except Exception as e:
        printlog(f"Failed to create image for bracket ['name'='{bracket_name}'].", e)
    
    return db_match, winner
    
async def override_match_score(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Overrides the results of a match. The status of the match does not matter.
    Only usable by bracket creator or bracket manager
    """
    guild = message.channel.guild
    db_guild = await _guild.find_guild(self, db, guild.id)
    usage = "Usage: `$bracket override <entrant_name | 1️⃣ | 2️⃣>`. Must be in a reply to a match."
    if argc < 3 or not message.reference:
        await message.channel.send(usage)
        return False
    # Fetch active bracket
    db_bracket = _bracket.find_active_bracket(db_guild)
    if not db_bracket:
        return False

    # Only allow author or guild admins to finalize bracket
    if message.author.id != db_bracket['author']['id'] or not message.author.guild_permissions.administrator:
        await message.channel.send(f"Only the author or server admins can override match score.")
        return False

    # Check if valid winner was provided
    valid1 = ['1', '1️⃣']
    valid2 = ['2', '2️⃣']
    winner_emote = None
    if argv[2] in valid1:
        winner_emote = '1️⃣'
    elif argv[2] in valid2:
        winner_emote = '2️⃣'
    else:
        # Get provided name
        entrant_name = ' '.join(argv[2:])


    # Check if replying to a match message
    match_message = await message.channel.fetch_message(message.reference.message_id)
    try:
        db_match = find_match(db_bracket, match_message.id)
    except:
        return False
    if not db_match:
        await message.channel.send("Match override must be in reply to a match message.")
        return False

    # Find by name if applicable
    if not winner_emote:
        player1 = _bracket.find_entrant(db_bracket, db_match['player1']['id'])
        player2 = _bracket.find_entrant(db_bracket, db_match['player2']['id'])
        if player1['name'].lower() == entrant_name.lower():
            winner_emote = '1️⃣'
        elif player2['name'].lower() == entrant_name.lower():
            winner_emote = '2️⃣'
        else:
            # printlog(f"User ['name'='{entrant_name}']' is not an entrant in match ['id'='{match_id}'].")
            await message.channel.send(f"There is no entrant named '{entrant_name}' in this match.")
            return False

    # Check if actually changing the winner
    if db_match['winner_emote'] is not None and winner_emote == db_match['winner_emote']:
        await message.channel.send("Match override failed; Winner is the same.")
        return False

    # Delete previously created matches
    next_matches = db_match['next_matches']
    if len(next_matches) > 0:
        for next_match_id in next_matches:
            try:
                await delete_match(self, message, db, db_bracket, next_match_id)
            except:
                print(f"Something went wrong when deleting match ['id'={next_match_id}] while deleting bracket ['name'={db_bracket['name']}].")

    # Report match
    reported_match, winner = await report_match(self, match_message, db, guild, db_bracket, db_match, winner_emote)
    printlog(f"User ['name'='{message.author.name}'] overwrote match ['id'='{db_match['id']}'] New winner: {winner['name']} {winner_emote}.")
    await message.channel.send(f"Match override successful. New winner: {winner['name']} {winner_emote}")
    await message.delete()
    return True

async def disqualify_entrant_match(self: Client, message: Message, db: Database, db_guild: dict, db_bracket: dict, db_match: dict, entrant_name: str):
    """
    Destroys an entrant from a tournament or DQs them if the tournament has already started from a command.
    Match version.
    """
    db_entrant = None
    # Check if entrant exists
    player1 = _bracket.find_entrant(db_bracket, db_match['player1']['id'])
    player2 = _bracket.find_entrant(db_bracket, db_match['player2']['id'])
    db_entrant = None
    if player1['name'].lower() == entrant_name.lower():
        db_entrant = db_match['player1']
        entrant_name = db_entrant['name']
    elif player2['name'].lower() == entrant_name.lower():
        db_entrant = db_match['player2']
        entrant_name = db_entrant['name']
    else:
        # printlog(f"User ['name'='{entrant_name}']' is not an entrant in match ['id'='{match_id}'].")
        await message.channel.send(f"There is no entrant named '{entrant_name}' in this match.")
        return False

    # Check if already disqualified
    bracket_name = db_bracket['name']
    bracket_entrant = list(filter(lambda elem: elem['name'] == entrant_name, db_bracket['entrants']))[0]
    if not bracket_entrant['active']:
        await message.channel.send(f"Entrant '{entrant_name}' has already been disqualified from ***{bracket_name}***.")
        return False

    # Call dq helper function
    return await _bracket.disqualify_entrant(self, message, db, db_guild, db_bracket, db_entrant)

######################
## HELPER FUNCTIONS ##
######################

async def update_player(db: Database, guild_id: int, db_bracket: dict, 
                        match_id: int, updated_player1=None, updated_player2=None):
    """
    Updates the players in a match.
    """
    bracket_name = db_bracket['name']
    match_index = _bracket.find_index_in_bracket(db_bracket, MATCHES, 'id', match_id)
    if updated_player1:
        db_bracket['matches'][match_index]['player1'] = updated_player1
    if updated_player2:
        db_bracket['matches'][match_index]['player2'] = updated_player2
    if not (updated_player1 or updated_player2):
        return None
    return await _bracket.set_bracket(db, guild_id, bracket_name, db_bracket)

async def set_match(db: Database, guild_id: int, db_bracket: dict, db_match: dict):
    """
    Updates the players in a match.
    """
    bracket_name = db_bracket['name']
    match_index = _bracket.find_index_in_bracket(db_bracket, MATCHES, 'id', db_match['id'])
    db_bracket['matches'][match_index] = db_match
    return await _bracket.set_bracket(db, guild_id, bracket_name, db_bracket)

#######################
## MESSAGE FUNCTIONS ##
#######################

def create_match_embed(db_bracket: dict, db_match: dict):
    """
    Creates embed object to include in match message.
    """
    bracket_name = db_bracket['name']
    match_id = db_match['id']
    jump_url = db_bracket['jump_url']
    round = db_match['round']
    player1_id = db_match['player1']['id']
    player2_id = db_match['player2']['id']
    time = datetime.now().strftime("%#I:%M %p")
    embed = Embed(title=f"⚔️ {get_round_name(db_bracket, match_id, round)}", description=f"Awaiting result...\nOpened at {time}", color=0x50C878)
    embed.set_author(name=bracket_name, url=jump_url, icon_url=ICON)
    embed.add_field(name=f"Players", value=f'1️⃣ <@{player1_id}> vs <@{player2_id}> 2️⃣', inline=False)
    # embed.add_field(name=f'Bracket Link', value=url, inline=False)
    embed.set_footer(text="Players react with 1️⃣ or 2️⃣ to report the winner.")
    return embed

def edit_match_embed_dispute(embed: Embed):
    """
    Updates embed object for disputes.
    """
    embed.add_field(name="🛑 Result Dispute 🛑", value="Contact a bracket manager or change vote to resolve.")
    embed.color = 0xD4180F
    return embed

def edit_match_embed_confirmed(embed: Embed, player1: dict, player2: dict, winner_emote: str, is_dq: bool=False):
    """
    Updates embed object for confirmed match
    """
    time = datetime.now().strftime("%#I:%M %p")
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
    embed.set_footer(text="Result finalized. To change result, contact a bracket manager.")
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
                try:
                    matches = challonge.matches.index(db_bracket['challonge']['id'])
                    matches.sort(reverse=True, key=(lambda match: match['id']))
                    if match_id != matches[0]['id']:
                        return "Grand Finals Set 1"
                    else:
                        return "Grand Finals Set 2"
                except:
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