from common import CHALLENGES, GUILDS, ICON
from datetime import datetime, timedelta, date
from discord import Client, Embed, Guild, Member, Message, RawReactionActionEvent, Reaction, TextChannel, User
from gridfs import Database
from logger import printlog
from pprint import pprint
import asyncio
import bracket as _bracket
import discord
import guild as _guild
import match as _match
import challonge
import mdb
import re

# leaderboard.py
# leaderboard for 1v1 challenges

LEADERBOARD = 'leaderboard'

def find_leaderboard_user(db_guild: dict, user_name: int):
    """
    Retrieves and returns a leaderboard user document from the database (if it exists).
    """
    guild_leaderboard = db_guild['leaderboard']
    result = [user for user in guild_leaderboard if user['name'] == user_name]
    if result:
        return result[0]
    return None

def find_leaderboard_user_by_id(db_guild: dict, user_id: int):
    """
    Retrieves and returns a leaderboard user document from the database (if it exists).
    """
    guild_leaderboard = db_guild['leaderboard']
    result = [user for user in guild_leaderboard if user['id'] == user_id]
    if result:
        return result[0]
    return None

async def retrieve_leaderboard(message: Message, db: Database, argv: list, argc: int):
    """
    Retrieves all users in a leaderboard.
    Paginated with 10 users per page.
    """
    guild = message.guild
    db_guild = await _guild.find_guild(db, guild.id)
    db_leaderboard = db_guild['leaderboard']

async def retrieve_leaderboard_user_stats(message: Message, db: Database, argv: list, argc: int):
    """
    Retrieves the stats for a user in a guild leaderboard.
    If not is not specified, retrieves the stats for the user who issued the command.
    """
    # Parse args
    usage = 'Usage: `$leaderboard stats [name]`'
    if argc < 2:
        await message.channel.send(usage)
        return False
    guild = message.guild
    db_guild = await _guild.find_guild(db, guild.id)
    # Get name of user
    if argc == 2:
        user_name = message.author.name
    else:
        user_name = ' '.join(argv[2:])
    # Check if user is in leaderboard
    db_user = find_leaderboard_user(db_guild, user_name)
    if not db_user:
        await message.channel.send(f"User '{user_name}' has no record in the leaderboard.")
        return False
    # Send stats of user
    total_matches = len(db_user['matches'])
    wins = db_user['wins']
    losses = db_user['losses']
    win_rate = "{0:.2%}".format(wins / total_matches)
    await message.channel.send(f"📈 Stats for user '{user_name}':\nTotal Challenges: {total_matches}\n🏆 Wins: {wins}\n❌ Losses: {losses}\n Win %: {win_rate}")
    return True

async def create_leaderboard_user(db: Database, guild: Guild, db_challenge: dict, db_player: dict, win: bool):
    """
    Creates a new user in a guild challenge leaderboard.
    """
    new_user = {
        "id": db_player['id'],
        "name": db_player['name'],
        "wins": 1 if win else 0,
        "losses": 0 if win else 1,
        "matches": [db_challenge['id']]
    }
    try:
        await _guild.push_to_guild(db, guild, LEADERBOARD, new_user)
        print(f"Added new user ['id'='{db_player['id']}'] to leaderboard ['guild_id'='{guild.id}'].")
    except Exception as e:
        printlog(f"Failed to add user ['id'={db_player['id']}] to leaderboard ['guild_id'='{guild.id}'].", e)
        return None
    return new_user

async def update_leaderboard_user_score(db: Database, guild: Guild, db_challenge: dict, db_user: dict, win: bool):
    """
    Updates a user's wins/losses in a guild challenge leaderboard.
    """
    db_user['total_matches'] += 1
    if win:
        db_user['wins'] += 1
    else:
        db_user['losses'] += 1

    # Add challenge to list
    db_user['matches'].append(db_challenge['id'])
    try:
        await set_leaderboard_user(db, guild, LEADERBOARD, db_user)
        if win:
            print(f"Added win to user ['id'='{db_user['id']}'] in leaderboard ['guild_id'='{guild.id}'].")
        else:
            print(f"Added loss to user ['id'='{db_user['id']}'] in leaderboard ['guild_id'='{guild.id}'].")
    except Exception as e:
        if win:
            printlog(f"Failed to add user ['id'={db_user['id']}] in leaderboard ['guild_id'='{guild.id}'].", e)
        else:
            printlog(f"Failed to add loss to user ['id'='{db_user['id']}'] in leaderboard ['guild_id'='{guild.id}'].")
        return None
    return db_user

async def set_leaderboard_user(db: Database, guild_id: int, user_id: int, new_user: dict):
    """
    Sets a leaderboard user in a guild to the specified document.
    """
    return await mdb.update_single_document(db, 
        {'guild_id': guild_id, 'leaderboard.id': user_id}, 
        {'$set': {f'leaderboard.$': new_user}
        },
        GUILDS)