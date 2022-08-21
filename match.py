from datetime import datetime, timedelta, date
from discord import Client, Embed, Guild, Message, RawReactionActionEvent, Reaction, TextChannel, User
from gridfs import Database
from logger import printlog
from pprint import pprint
import asyncio
import bracket as _bracket
import challonge
import mdb
import re

# match.py
# Bracket matches

BRACKETS = 'brackets'
MATCHES = 'matches'
ICON = 'https://static-cdn.jtvnw.net/jtv_user_pictures/638055be-8ceb-413e-8972-bd10359b8556-profile_image-70x70.png'

async def get_match(self: Client, db: Database, match_id: int):
    """
    Retrieves and returns a match document from the database (if it exists).
    """
    return await mdb.find_document(db, {"match_id": match_id}, MATCHES)

async def add_match(self: Client, message: Message, db: Database, bracket, challonge_match):
    """
    Creates a new match.
    """
    # Create match message and embed
    # Get player names
    player1 = list(filter(lambda entrant: (entrant['challonge_id'] == challonge_match['player1_id']), bracket['entrants']))[0]
    player2= list(filter(lambda entrant: (entrant['challonge_id'] == challonge_match['player2_id']), bracket['entrants']))[0]
    player1_id = player1['discord_id']
    player2_id = player2['discord_id']

    player1['vote'] = None
    player2['vote'] = None
    new_match = {
        "match_id": challonge_match['id'],
        "message_id": None,
        "bracket": {
            'name': bracket['name'], 
            'message_id': bracket['message_id'], 
            'challonge_id': bracket['challonge']['id'] },
        "player1": player1,
        "player2": player2,
        "round": challonge_match['round'],
        'completed': False,
        "winner": None,
        "next_matches" : []
    }

    # Send embed message
    embed = create_match_embed(bracket, new_match)
    match_message = await message.channel.send(f'<@{player1_id}> vs <@{player2_id}>', embed=embed)
    # React to match message
    await match_message.add_reaction('1️⃣')
    await match_message.add_reaction('2️⃣')

    # Add match document to database
    new_match['message_id'] = match_message.id
    try:
        await mdb.add_document(db, new_match, MATCHES)
    except:
        return
    match_id = new_match['match_id']
    # Add match id and message id to bracket document
    try:
        await mdb.update_single_document(db, {'name': bracket['name']}, {'$push': {'matches': {'match_id': match_id, 'message_id': match_message.id}}}, BRACKETS)
    except:
        print("Failed to add match to bracket document.")
    return new_match

async def delete_match(self: Client, message: Message, db: Database, match):
    """
    Adds a new match document to the database.
    """
    match_id = match['match_id']
    # Delete match message
    try:
        match_message = await message.channel.fetch_message(match['message_id'])
        await match_message.delete() # delete message from channel
    except:
        print(f"Failed to delete message for match [id='{match_id}']")
    # Check if match is in database
    try:
        match = await get_match(self, db, match_id)
        if not match:
            return False
    except:
        return False
    # Delete from database
    return await mdb.delete_document(db, {"match_id": match_id}, MATCHES)

async def vote_match_reaction(self: Client, payload: RawReactionActionEvent, db: Database):
    """
    Reports the winner for a match using reactions.
    """
    channel: TextChannel = await self.fetch_channel(payload.channel_id)
    match_message: Message = await channel.fetch_message(payload.message_id)
    # Check if reaction was on a match message
    try:
        match = await mdb.find_document(db, {'message_id': match_message.id}, MATCHES)
    except:
        return False
    if not match:
        return False
    if match['completed']:
        return False
    match_id = match['match_id']
    match_embed = match_message.embeds[0]
    bracket_id = match['bracket']['message_id']

    # Check if user was one of the players
    if payload.user_id == match['player1']['discord_id']:
        voter = match['player1']
    elif payload.user_id == match['player2']['discord_id']:
        voter = match['player2']
    else:
        return False

    member = channel.guild.get_member(payload.user_id)
    # Record vote or remove vote in database
    if payload.event_type == 'REACTION_ADD':
        vote = payload.emoji.name
        action = "Added"
        try:
            # Remove other vote if applicable
            if vote == '1️⃣':
                await match_message.remove_reaction('2️⃣', member)
            elif vote == '2️⃣':
                await match_message.remove_reaction('1️⃣', member)
        except:
            pass
    elif payload.event_type == 'REACTION_REMOVE':
        if voter['vote'] == payload.emoji.name: # Removed vote
            vote = None
        else:
            return False # Switched vote
        action = "Removed"
    try:
        player1 = match['player1']
        player2 = match['player2']
        if voter == match['player1']:
            player1['vote'] = vote
            updated_match = await mdb.update_single_document(db, {'match_id': match_id}, {'$set': {'player1': player1}}, MATCHES)
        else:
            player2['vote'] = vote
            updated_match = await mdb.update_single_document(db, {'match_id': match_id}, {'$set': {'player2': player2}}, MATCHES)
        print(f"{action} vote by user ['discord_id'='{payload.user_id}'] for match ['match_id'={match_id}']")
    except Exception as e:
        print(e)
        print(f"Failed to record vote by user ['discord_id'='{payload.user_id}'] for match ['match_id'='{match_id}'].")
        return False
    if not updated_match:
        return False

    # Check if both players voted
    if player1['vote'] and player2['vote']:
        # Check who they voted for
        if player1['vote'] == player2['vote']:
            # Report the match score
            winner_emote = vote
            # Get bracket
            try:
                bracket = await mdb.find_document(db, {'message_id': match['bracket']['message_id']}, BRACKETS)
            except:
                return
            if not bracket:
                print(f"Failed to get bracket ['message_id'={bracket_id}] for match ['id'={match_id}].")
                return False
            # Report match
            await report_match(self, match_message, db, bracket, updated_match, winner_emote)
        else:
            # Dispute detected
            dispute_embed = edit_match_embed_dispute(match_embed)
            await match_message.edit(embed=dispute_embed)
    return True

async def report_match(self: Client, match_message: Message, db: Database, bracket, match, winner_emote: str):
    """
    Reports a match winner and fetches the next matches that have not yet been called.
    """
    bracket_name = bracket['name']
    bracket_challonge_id = bracket['challonge']['id']
    match_id = match['match_id']
    if winner_emote == '1️⃣':
        winner: dict = match['player1']
        score = '1-0'
    elif winner_emote == '2️⃣':
        winner: dict = match['player2']
        score = '0-1'
    try:    
        challonge.matches.update(bracket_challonge_id, match_id, scores_csv=score,winner_id=winner['challonge_id'])
    except Exception as e:
        printlog(f"Something went wrong when reporting match ['match_id'={match_id}] on challonge.", e)
        return False
    try:
        winner.pop('vote', None)
        winner['winner_emote'] = winner_emote
        updated_match = await mdb.update_single_document(db, {'match_id': match_id}, { '$set': {'completed': datetime.now(), 'winner': winner}}, MATCHES)
    except:
        print(f"Failed to report match ['match_id'={match_id}] in database.")
        return False

    match_embed = match_message.embeds[0]
    confirm_embed = edit_match_embed_confirmed(match_embed, winner)
    await match_message.edit(embed=confirm_embed)
    print("Succesfully reported match [id={0}]. Winner = '{1}'.".format(match_id, winner['name']))

    # Check for matches that have not yet been called
    try:
        matches = challonge.matches.index(bracket['challonge']['id'], state='open')
    except Exception as e:
        printlog("Failed to get new matches.", e)
        return False
    # Check if last match
    if len(matches) == 0 and match['round'] == bracket['num_rounds']:
        await match_message.channel.send(f"***{bracket_name}*** has been completed! Use `$bracket finalize {bracket_name}` to finalize the results!")
        return True
    for challonge_match in matches:
        # Check if match has already been called (in database)
        try:
            check_match = await mdb.find_document(db, {'match_id': challonge_match['id']}, MATCHES)
        except:
            print("Failed to check match in database..")
            return False
        if check_match:
            continue
        new_match = await add_match(self, match_message, db, bracket, challonge_match)
        # Add new match message_id to old match's next_matches list
        try:
            await mdb.update_single_document(db, {'match_id': match_id}, {'$push': {'next_matches': new_match['message_id']}}, MATCHES)
        except:
            print(f"Failed to add new match ['match_id'='{new_match['match_id']}'] to next_matches of match ['match_id'='{match_id}']")
    return updated_match
    
async def override_match_score(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Overrides the results of a match. The status of the match does not matter.
    Only usable by bracket creator or bracket manager
    """
    usage = "Usage: `$bracket override <1️⃣ | 2️⃣>`. Must be in a reply to a match"
    if argc < 3 or not message.reference:
        return await message.channel.send(usage)

    # Make sure valid winner was provided
    valid1 = ['1', '1️⃣']
    valid2 = ['2', '2️⃣']
    if argv[2] in valid1:
        winner_emote = '1️⃣'
    elif argv[2] in valid2:
        winner_emote = '2️⃣'
    else:
        return await message.channel.send(usage) 

    # Make sure replying to a match message
    match_message = await message.channel.fetch_message(message.reference.message_id)
    try:
        match = await mdb.find_document(db, {'message_id': match_message.id}, MATCHES)
    except:
        return
    if not match:
        return await message.channel.send("Match override must be in reply to a match message.")

    # Check if actually changing the winner
    if match['winner'] is not None and winner_emote == match['winner']['winner_emote']:
        await message.channel.send("Match override failed; Winner is the same.")
        return False

    # Get bracket the match is in
    match_id = match['match_id']
    bracket_name = match['bracket']['name']
    bracket = await _bracket.get_bracket(self, db, bracket_name)
    if not bracket:
        printlog(f"Failed to get bracket ['name'={bracket_name}] for match ['id'={match_id}].")
        return False

    # Delete previously created matches
    next_matches = match['next_matches']
    if len(next_matches) > 0:
        for message_id in next_matches:
            # Delete message
            message_to_delete: Message = await message.channel.fetch_message(message_id)
            await message_to_delete.delete()
            # Delete database document
            try:
                await mdb.delete_document(db, {'message_id': message_id}, MATCHES)
            except:
                print(f"Failed to delete match ['message_id'='{message_id}'] on override.'")

    # Report match
    # winner = match['player1'] if winner_emote == '1️⃣' else match['player2']
    reported_match = await report_match(self, match_message, db, bracket, match, winner_emote)

    print("Match succesfully overwritten.")
    await message.channel.send(f"Match override successful. New winner: {reported_match['winner']['name']} {winner_emote}")
    return True

#######################
## MESSAGE FUNCTIONS ##
#######################

def create_match_embed(bracket, match):
    """
    Creates embed object to include in match message.
    """
    bracket_name = bracket['name']
    match_id = match['match_id']
    jump_url = bracket['jump_url']
    round = match['round']
    player1_id = match['player1']['discord_id']
    player2_id = match['player2']['discord_id']
    time = datetime.now().strftime("%#I:%M %p")
    embed = Embed(title=get_round_name(bracket, match_id, round), description=f"Results Pending\nOpened at {time}", color=0x50C878)
    embed.set_author(name=bracket_name, url=jump_url, icon_url=ICON)
    embed.add_field(name=f"Players", value=f'1️⃣ <@{player1_id}> vs <@{player2_id}> 2️⃣', inline=False)
    # embed.add_field(name=f'Bracket Link', value=url, inline=False)
    embed.set_footer(text="React with 1️⃣ or 2️⃣ to report the winner.")
    return embed

def edit_match_embed_dispute(embed: Embed):
    """
    Updates embed object for disputes.
    """
    embed.add_field(name="🛑 Score Dispute 🛑", value="Contact a bracket manager or change vote to resolve.")
    embed.color = 0xD4180F
    return embed

def edit_match_embed_confirmed(embed: Embed, winner):
    """
    Updates embed object for confirmed match
    """
    time = datetime.now().strftime("%#I:%M %p")
    embed.description = f"Winner: **{winner['name']}**\nFinished at {time}"
    if len(embed.fields) > 1:
        # Remove dispute field
        embed.remove_field(1)
    embed.set_footer(text="Result finalized. To change result, contact a bracket manager.")
    embed.color = 0x000000
    return embed

def get_round_name(bracket, match_id, round):
    """
    Returns string value of round number based on number of rounds in a bracket.
    """
    num_rounds = bracket['num_rounds']
    if round > 0:
        # Winners Bracket
        match num_rounds - round:
            case 0:
                try:
                    matches = challonge.matches.index(bracket['challonge']['id'])
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