from common import CHALLENGES, GUILDS, ICON
from datetime import datetime, timedelta, date
from discord import Client, Embed, Guild, Member, Message, RawReactionActionEvent, Reaction, TextChannel, User
from gridfs import Database
from logger import printlog
from pprint import pprint
import asyncio
import bracket as _bracket
import guild as _guild
import match as _match
import challonge
import mdb
import re

# challenge.py
# 1v1 challenges

type_match = re.compile(r'^[Bb][Oo][0-9]+$')
id_match = re.compile(r'^<@[0-9]+>$')

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
            lambda challenge: not challenge['open'] and not challenge['completed']
                and challenge['player1']['id'] == user_id, 
            db_guild['challenges']))[0]
    except:
        return None

async def create_challenge_queue(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Creates a new challenge match and waits for a challenger.
    """
    guild: Guild = message.guild
    # Parse arguments; default type = Bo3
    usage = 'Usage: `$challenge create [type]`\nex. $challenge create bo3'
    if argc < 2:
        await message.channel.send(usage)
        return None
    # Get type
    best_of = 3
    if argc >= 3:
        text_match = type_match.search(argv[2])
        if text_match:
            best_of = int(text_match.group()[2:])
            if best_of % 2 != 1: # must be odd
                await message.channel.send("There must be an odd number of rounds.")
                return None
        else:
            await message.channel.send(f"Invalid input for type.\n{usage}")

    # Call main function
    return await create_challenge(self, message, db, guild, player1=message.author, player2=None, best_of=best_of, open=True)

async def create_challenge_direct(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Creates a new challenge match between two players.
    """
    guild: Guild = message.guild
    # Parse arguments; default type = Bo3
    usage = f'Usage: `$challenge @<user> [type]`\nex. $challenge <@{self.user.id}> bo3'
    if argc < 2:
        await message.channel.send(usage)
        return None
    # Check for metioned user
    if len(message.mentions) == 0:
        await message.channel.send(f"Missing user mention.\n{usage}")
        return False
    elif len(message.mentions) > 1:
        await message.channel.send(f"Too many user mentions.\n{usage}")
        return False
    matched_id = id_match.search(argv[1])
    if matched_id:
        player2 = message.mentions[0]
    else:
        await message.channel.send(f"Invalid input for user.\n{usage}")
        return False
    # Get type
    best_of = 3
    if argc >= 3:
        text_match = type_match.search(argv[2])
        if text_match:
            best_of = int(text_match.group()[2:])
            if best_of % 2 != 1: # must be odd
                await message.channel.send("There must be an odd number of rounds.")
                return None
        else:
            await message.channel.send(f"Invalid input for type.\n{usage}")
    return await create_challenge(self, message, db, guild, player1=message.author, player2=player2, best_of=best_of, open=False)

async def create_challenge(self: Client, message: Message, db: Database, guild: Guild, player1: Member, player2: Member | None, best_of: int, open: bool):
    """
    Creates a new challenge match and adds it to the database.
    """
    # TODO: Check if already has active challenge

    player1_id = player1.id
    player1_name = player1.name
    player2_id = player2.id if player2 else None
    player2_name = player2.name if player2 else None

    new_challenge = {
        "id": None,
        "channel_id": message.channel.id,
        "player1": {
            "id": player1_id,
            "name": player1_name,
            "vote": None
        },
        "player2": {
            "id": player2_id,
            "name": player2_name,
            "vote": None
        },
        "best_of": best_of,
        "winner_emote": None,
        "open": open,
        "completed": False
    }

    # Send embed message
    embed = create_challenge_embed(new_challenge)
    challenge_message: Message = await message.channel.send(embed=embed)
    # Add boxing glove reaction to message
    await challenge_message.add_reaction('🥊')

    # Add challenge to database
    new_challenge['id'] = challenge_message.id
    result = await _guild.push_to_guild(self, db, guild, CHALLENGES, new_challenge)
    print(f"User '{message.author.name}' [id={message.author.id}] created new challenge ['id'={new_challenge['id']}].")
    return new_challenge

async def cancel_challenge(self: Client, message: Message, db: Database, argv: list, argc: int, delete: bool=False):
    """
    Cancels an open challenge match.
    If delete option is True, deletes challenge regardless of status. Only available to guild admins or bracket managers.
    """
    guild: Guild = message.guild
    db_guild = await _guild.find_guild(self, db, guild.id)
    # Fetch challenge
    usage = 'Usage: `$challenge cancel [name]` or `$challenge delete [name]` (admins only)'
    db_challenge, challenge_id = await parse_args(self, message, db, db_guild, usage, argv, argc)
    if not db_challenge:
        return False
    # Cancel or Delete
    if not delete:
        if message.author.id != db_challenge['player1']['id'] or not message.author.guild_permissions.administrator:
            await message.channel.send(f"Only the author or server admins can cancel challenges.")
            return False
    else:
        if not message.author.guild_permissions.administrator:
            await message.channel.send(f"Only the author or server admins can cancel challenges.")
            return False
    # Check if in channel challenge was created in
    if db_challenge['channel_id'] != message.channel.id:
        await message.channel.send(f"Must be in the channel that the challenge was created in: <#{db_challenge['channel_id']}>")
        return False
    # Only cancel if not open
    if not delete:
        if not db_challenge['open'] or db_challenge['completed']:
            await message.channel.send(f"You may not cancel challenges that are in progress or completed.")
            return False

    # Delete challenge message
    challenge_message: Message = await message.channel.fetch_message(message.reference.message_id)
    await challenge_message.delete()
    # Delete challenge document
    try:
        result = await _guild.pull_from_guild(self, db, guild, CHALLENGES, db_challenge)
    except:
        print(f"Failed to delete challenge ['id'={challenge_id}].")
        return False
    if result:
        print(f"User '{message.author.name}' [id={message.author.id}] cancelled challenge ['id'='{challenge_id}'].")
        await message.channel.send("Challenge successfully cancelled.")
        return True
    else:
        return False

    # TODO: If deleting a completed challenge, update leaderboard

async def accept_challenge(self: Client, payload: RawReactionActionEvent, db: Database):
    """
    Accepts an open challenge.
    """
    channel: TextChannel = await self.fetch_channel(payload.channel_id)
    guild: Guild = await self.fetch_guild(payload.guild_id)
    db_guild = await _guild.find_guild(self, db, guild.id)
    challenge_message: Message = await channel.fetch_message(payload.message_id)

    # Check if reaction was on a challenge message
    db_challenge = find_challenge(db_guild, payload.message_id)
    if not db_challenge:
        return False
    # Check if user created the challenge
    if db_challenge['player1']['id'] == payload.member.id:
        return False
    # Check if completed
    if db_challenge['completed']:
        return False
    # Check if direct challenge
    if db_challenge['player2']['id'] is not None: # Direct challenge
        # Check if member reacting is the person being challenged
        if db_challenge['player2']['id'] != payload.member.id:
            return False
    else: # Queuing for challenge
        # Check if open
        if not db_challenge['open']:
            return False

        # Add user to challenge
        db_challenge['player2'] = {
            "id": payload.member.id,
            "name": payload.member.name,
            "vote": None
        }
    
    # Set to closed
    db_challenge['open'] = False
    # Update challenge in databse
    result = await set_challenge(db, guild.id, challenge_message.id, db_challenge)
    if not result:
        print(f"Failed to accept challenge ['id'='{payload.message_id}'].")
        return False
    print(f"User ['name'='{payload.member.name}'] accepted challenge ['id'='{db_challenge['id']}'] by '{db_challenge['player1']['name']}'.")
    # Update message embed
    updated_embed = edit_challenge_embed_start(db_challenge, challenge_message.embeds[0])
    await challenge_message.edit(embed=updated_embed)
    # Remove 🥊 reactions and add 1️⃣ and 2️⃣
    await challenge_message.clear_reactions()
    await challenge_message.add_reaction('1️⃣')
    await challenge_message.add_reaction('2️⃣')
    return True

async def vote_challenge_reaction(self: Client, payload: RawReactionActionEvent, db: Database):
    """
    Reports the winner for a challenge using reactions.
    """
    channel: TextChannel = await self.fetch_channel(payload.channel_id)
    guild: Guild = await self.fetch_guild(payload.guild_id)
    db_guild = await _guild.find_guild(self, db, guild.id)
    challenge_message: Message = await channel.fetch_message(payload.message_id)

    # Check if reaction was on a challenge message
    db_challenge = find_challenge(db_guild, payload.message_id)
    if not db_challenge:
        return False
    # Check if completed
    if db_challenge['completed']:
        return False

    # Call main vote_reaction function
    return await _match.vote_reaction(self, payload, challenge_message, db, db_guild, db_challenge)

async def report_challenge(self: Client, challenge_message: Message, db: Database, db_guild: dict, db_challenge: dict, winner_emote: str, is_dq: bool=False):
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
        db_challenge.update({'completed': datetime.now(), 'winner_emote': winner_emote})
        updated_challenge = await set_challenge(db, db_guild['guild_id'], challenge_id, db_challenge)
    except Exception as e:
        printlog(f"Failed to report challenge ['id'={challenge_id}] in database.", e)
        return None, None
    
    # Update challenge embed
    challenge_embed = challenge_message.embeds[0]
    confirm_embed = _match.edit_match_embed_confirmed(challenge_embed, db_challenge['player1'], db_challenge['player2'], winner_emote, is_dq)
    await challenge_message.edit(embed=confirm_embed)
    print("Succesfully reported challenge [id={0}]. Winner = '{1}'.".format(challenge_id, winner['name']))

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
    # time = datetime.now().strftime("%#I:%M %p")
    embed = Embed(title=f"⚔️  Challenge - Best of {db_challenge['best_of']}", description=f"{player1_name} has issued a challenge!", color=0x56A1E3)
    embed.set_author(name="beta-bot | GitHub 🤖", url="https://github.com/fborja44/beta-bot", icon_url=ICON)
    if not player2_id:
        embed.add_field(name=f"Waiting for Challenger...", value=f'1️⃣ <@{player1_id}> vs ??? 2️⃣', inline=False)
    else:
        embed.add_field(name=f"Players", value=f'1️⃣ <@{player1_id}> vs <@{player2_id}> 2️⃣', inline=False)
    embed.set_footer(text="React with 🥊 to accept this challenge.")
    return embed

def edit_challenge_embed_start(db_challenge: dict, embed: Embed):
    """
    Edits an embed object for a challenge that has been started.
    """
    player1_id = db_challenge['player1']['id']
    player2_id = db_challenge['player2']['id']
    embed.color = 0x50C878
    embed.description += "\nAwaiting result..."
    embed.set_field_at(0, name=f"Players", value=f'1️⃣ <@{player1_id}> vs <@{player2_id}> 2️⃣', inline=False)
    embed.set_footer(text="Players react with 1️⃣ or 2️⃣ to report the winner.")
    return embed

def edit_challenge_embed_dispute(embed: Embed):
    """
    Edits an embed object for disputes.
    """
    embed.add_field(name="🛑 Result Dispute 🛑", value="Contact a bracket manager or change vote to resolve.")
    embed.color = 0xD4180F
    return embed

######################
## HELPER FUNCTIONS ##
######################

async def parse_args(self: Client, message: Message, db: Database, db_guild: dict, usage: str, argv: list, argc: int, f_argc: int=2, send: bool=True):
    """"
    Parses arguments for bracket functions. Checks if there is a valid challenge.
    """
    if argc < f_argc:
        await message.channel.send(usage)
        return (None, None)
    # Get challenge from database
    if message.reference:
        challenge_id = message.reference.message_id
        # Check if challenge exists
        db_challenge = find_challenge(db_guild, challenge_id)
        if not db_challenge:
            if send: 
                await message.channel.send(f"Something went wrong when finding the challenge.")
            return (None, None)
    else:
        # Get user's active match, if exists
        db_challenge = find_active_challenge_by_user(db_guild, message.author.id)
        if not db_challenge:
            if send: 
                await message.channel.send(f"You do not have any open challenges.")
            return (None, None)
        challenge_id = db_challenge['id']
    return (db_challenge, challenge_id)

async def set_challenge(db: Database, guild_id: int, challenge_id: int, new_challenge: dict):
    """
    Sets a challenge in a guild to the specified document.
    """
    return await mdb.update_single_document(db, 
        {'guild_id': guild_id, 'challenges.id': challenge_id}, 
        {'$set': {f'challenges.$': new_challenge}
        },
        GUILDS)

async def update_player(db: Database, db_guild: dict, challenge_id: int, updated_player1=None, updated_player2=None):
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
    return await set_challenge(db, db_guild['guild_id'], challenge_id, db_challenge)