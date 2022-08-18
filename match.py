from datetime import datetime, timedelta, date
from discord import Client, Embed,  Message, Reaction, User
from gridfs import Database
from logger import printlog
from pprint import pprint
import asyncio
import challonge
import mdb
import re

# match.py
# Bracket matches

BRACKETS = 'brackets'
MATCHES = 'matches'
ICON = 'https://static-cdn.jtvnw.net/jtv_user_pictures/638055be-8ceb-413e-8972-bd10359b8556-profile_image-70x70.png'

def create_match_embed(bracket_name: str, player1_id: int, player2_id: int, round: int, jump_url: str):
    """
    Creates embed object to include in match message.
    """
    if round > 0:
        round_str = f"Winners Round {round}"
    else:
        round_str = f"Losers Round {round}"
    time = datetime.now().strftime("%I:%M %p")
    embed = Embed(title=round_str, description=f"Results Pending\nOpened at {time}", color=0x50C878)
    embed.set_author(name=bracket_name, url=jump_url, icon_url=ICON)
    embed.add_field(name=f"Players", value=f'1️⃣ <@{player1_id}> vs <@{player2_id}> 2️⃣', inline=False)
    # embed.add_field(name=f'Bracket Link', value=url, inline=False)
    embed.set_footer(text="React with 1️⃣ or 2️⃣ to report the winner.")
    return embed

def edit_match_embed_dispute(embed: Embed):
    """
    Updates embed object for disputes.
    """
    embed.add_field(name="Dispute Detected 🛑", value="Contact a bracket manager or change reaction to resolve.")
    embed.color = 0xD4180F
    return embed

def edit_match_embed_confirmed(embed: Embed, winner):
    """
    Updates embed object for confirmed match
    """
    time = datetime.now().strftime("%I:%M %p")
    embed.description = f"Winner: {winner['name']}\nFinished at {time}"
    if len(embed.fields) > 1:
        # Remove dispute field
        embed.remove_field(1)
    embed.set_footer(text="Result finalized. To change result, contact a bracket manager.")
    embed.color = 0x000000
    return embed

async def get_match(self: Client, db: Database, match_id: int):
    """
    Retrieves and returns a match document from the database (if it exists).
    """
    return await mdb.find_document(db, {"match_id": match_id}, MATCHES)

async def add_match(self: Client, message: Message, db: Database, bracket, match):
    """
    Creates a new match.
    """
    # Create match message and embed
    # Get player names
    player1 = list(filter(lambda entrant: (entrant['challonge_id'] == match['player1_id']), bracket['entrants']))[0]
    player2= list(filter(lambda entrant: (entrant['challonge_id'] == match['player2_id']), bracket['entrants']))[0]
    player1_id = player1['discord_id']
    player2_id = player2['discord_id']
    embed = create_match_embed(bracket['name'], player1_id, player2_id, match['round'], bracket['jump_url'])
    match_message = await message.channel.send(f'<@{player1_id}> vs <@{player2_id}>', embed=embed)
    
    # React to match message
    await match_message.add_reaction('1️⃣')
    await match_message.add_reaction('2️⃣')

    # Add match document to database
    new_match = {
        "match_id": match['id'],
        "message_id": match_message.id,
        "bracket": {'name': bracket['name'], 'message_id': bracket['message_id'], 'challonge_id': bracket['challonge']['id']},
        "player1": player1,
        "player2": player2,
        "round": match['round'],
        'completed': False,
        "winner": None
    }
    await mdb.add_document(db, new_match, MATCHES)
    match_id = new_match['match_id']

    # Add match id to bracket document
    try:
        print(match_id)
        await mdb.update_single_field(db, {'name': bracket['name']}, {'$push': {'matches': {'match_id', match_id}}}, BRACKETS)
    except:
        print("Failed to add match to bracket document.")

    # Wait for reply
    def check(reaction, user):
        """
        Wait for reply to message that comes from one of the two players
        """
        is_message = (reaction.message.id == match_message.id)
        is_player = (user.id == player1_id or user.id == player2_id)
        is_emote = (str(reaction.emoji) == '1️⃣' or str(reaction.emoji) == '2️⃣')
        return is_message and is_player and is_emote

    # Player match voting loop
    player1_vote = None
    player2_vote = None
    while True:
        reaction, user = await self.wait_for('reaction_add', check=check)
        if user.id == player1['discord_id']:
            player1_vote = report_match_reaction(reaction, user, player1['discord_id'])
            printlog(f"Player '{user.name}' voted on match [id='{match_id}']. [vote='{player1_vote}']")
        elif user.id == player2['discord_id']:
            player2_vote = report_match_reaction(reaction, user, player2['discord_id'])
            printlog(f"Player '{user.name}' voted on match [id='{match_id}']. [vote='{player1_vote}']")
        # Check if both players voted
        if player1_vote and player2_vote:
            if player1_vote == player2_vote:
                # Confirmed
                break
            else:
                # Dispute
                dispute_embed = edit_match_embed_dispute(embed)
                await match_message.edit(embed=dispute_embed)
        elif player1_vote or player2_vote:
            # Start auto-confirm timer
            pass

    # Make sure both votes are the same
    if player1_vote == '1️⃣':
        winner = player1
    elif player1_vote == '2️⃣':
        winner = player2
    # Update score
    await update_match_score(self, db, bracket['challonge']['id'], match_id, winner, embed)
    embed = edit_match_embed_confirmed(embed, winner)
    print("Succesfully reported match [id={0}]. Winner = '{1}'".format(match_id, winner['name']))


async def delete_match(self: Client, db: Database, match_id: int, message_id: int, channel_id: int):
    """
    Adds a new match document to the database.
    """
    # Check if match already exists
    try:
        match = await get_match(self, db, match_id)
        if not match:
            return
    except:
        pass
    # Delete match message
    try:
        channel = self.get_channel(channel_id)
        match_message = await channel.fetch_message(message_id)
        await match_message.delete() # delete message from channel
    except:
        print(f"Failed to delete message for match [id='{match_id}']")

    # Delete from database
    return await mdb.delete_document(db, {"match_id": match_id}, MATCHES)

async def update_match_score(self: Client, db: Database, challonge_id: int, match_id: int, winner):
    """
    Updates a match on challonge and in the database.
    """
    if winner == '1️⃣':
        score = "1-0"
    else:
        score = "0-1"
    challonge.matches.update(challonge_id, match_id, scores_csv=score,winner_id=winner['challonge_id'])
    await mdb.update_single_field(db, {'match_id': match_id}, { '$set': {'completed': datetime.now(), 'winner': winner}}, MATCHES)


async def override_match_score():
    """
    Overrides the results of a reported match.
    """

def report_match_reaction(reaction: Reaction, user: User, check_id: int):
    """
    Reports the winner for a match using reactions.
    """
    # Check who reacted to the message
    if user.id == check_id:
        return str(reaction.emoji)

async def report_match_message(self: Client, message: Message, db: Database, match):
    """
    UNUSED + UNFINISHED
    Reports a score for a match using a reply.
    """
    # Split message into strings by space
    # First found name: player 1
    # First found number: player 1 score
    # Second found valid name: player 2
    # Second found number: player 2 score
    message_arr = re.split(" +| *- *| *, *", message.content)
    player1_name = match['player1']['name']
    player2_name = match['player2']['name']
    name1 = None
    name2 = None
    score1 = None
    score2 = None

    for item in message_arr:
        if not name1 and item.lower() == player1_name.lower():
            name1 = player1_name
        elif not name2 and item.lower() == player2_name.lower():
            name2 = player2_name
        elif name1 and not score1 and item.isnumeric():
            score1 = int(item)
        elif name2 and not score2 and item.isnumeric():
            score2 = int(item)
        if name1 and name2 and score1 != None and score2 != None:
            break
    if not name1 or not name2 or score1 == None or score2 == None:
        message.channel.send("Invalid score. Try the format '\{name\} \{score\} - \{score\} \{name\}'")
        return False
    winner = match['player1']['challonge_id'] if score1 > score2 else match['player2']['challonge_id']
    # Wait for confirmation from other player
    user2 = self.get_user(match['player2']['discord_id'])
    def check(reaction,  user):
        return reaction.message.id == message.id and user == user2
    try:
        reaction, user = await self.wait_for('reaction_add', timeout=90.0, check=check)
    except asyncio.TimeoutError:
        # automatically confirm
        confirmed = True
    else:
        # Check reaction emote
        if str(reaction.emoji) == '✅':
            confirmed = True
        elif str(reaction.emoji) == '❌':
            return False

    # Report score on challonge
    challonge.matches.update(match['bracket']['challonge_id'], match['id'], f"{score1}-{score2}", winner)

    # Update message

    # Check for matches that have not yet been called

    return confirmed
