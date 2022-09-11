from utils.common import GUILDS, ICON
from discord import Embed, Guild, Interaction, Member, Message, TextChannel, User
from utils.logger import printlog
from pprint import pprint
import tournaments.challenge as _challenge
import guilds.guild as _guild
import utils.mdb as mdb

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

async def retrieve_leaderboard(interaction: Interaction):
    """
    Retrieves all users in a leaderboard.
    Paginated with 10 users per page.
    """
    guild: Guild = interaction.guild
    db_guild: dict = await _guild.find_guild(guild.id)
    db_leaderboard: dict = db_guild['leaderboard']
    leaderboard_embed = create_server_leaderboard_embed(guild, db_leaderboard)
    await interaction.channel.send(embed=leaderboard_embed)
    await interaction.response.send_message(f"Found leaderboard for server '***{guild.name}***'!", ephemeral=True)
    return True

async def retrieve_leaderboard_user_stats(interaction: Interaction, player_mention: str):
    """
    Retrieves the stats for a user in a guild leaderboard.
    If not is not specified, retrieves the stats for the user who issued the command.
    """
    if len(player_mention.strip()) > 0:
        matched_id = _challenge.id_match.search(player_mention)
        if matched_id:
            user: Member = await interaction.guild.fetch_member(int(player_mention[3:-1]))
        else:
            await interaction.response.send_message(f"Invalid player mention.", ephemeral=True)
            return False
    else:
        user: Member = interaction.user
    # Parse args
    # usage = 'Usage: `/leaderboard stats [name]`'
    guild: Guild = interaction.guild
    db_guild = await _guild.find_guild(guild.id)
    # Check if user is in leaderboard
    db_user = find_leaderboard_user_by_id(db_guild, user.id)
    if not db_user:
        await interaction.response.send_message(f"User <@!{user.id}> has no record in the leaderboard.", ephemeral=True)
        return False
    # Send stats of user
    total_matches = len(db_user['matches'])
    wins = db_user['wins']
    losses = db_user['losses']
    win_rate = "{0:.2%}".format(wins / total_matches)
    stat_embed = create_player_stat_embed(db_user, user)
    await interaction.channel.send(embed=stat_embed)
    await interaction.response.send_message(f"Found stats for user <@!{user.id}>!", ephemeral=True)
    return True

async def create_leaderboard_user(guild: Guild, db_challenge: dict, db_player: dict, win: bool):
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
        await _guild.push_to_guild(guild, LEADERBOARD, new_user)
        print(f"Added new user ['id'='{db_player['id']}'] to leaderboard ['guild_id'='{guild.id}'].")
    except Exception as e:
        printlog(f"Failed to add user ['id'={db_player['id']}] to leaderboard ['guild_id'='{guild.id}'].", e)
        return None
    return new_user

async def update_leaderboard_user_score(guild_id: int, db_challenge: dict, db_user: dict, win: bool):
    """
    Updates a user's wins/losses in a guild challenge leaderboard.
    """
    if win:
        db_user['wins'] += 1
    else:
        db_user['losses'] += 1

    # Add challenge to list
    db_user['matches'].append(db_challenge['id'])
    try:
        result = await set_leaderboard_user(guild_id, db_user['id'], db_user)
        if not result: 
            print(f"Failed to update record of to user ['id'='{db_user['id']}'] in leaderboard ['guild_id'='{guild_id}'].")
        if win:
            print(f"Added win to user ['id'='{db_user['id']}'] in leaderboard ['guild_id'='{guild_id}'].")
        else:
            print(f"Added loss to user ['id'='{db_user['id']}'] in leaderboard ['guild_id'='{guild_id}'].")
    except Exception as e:
        if win:
            printlog(f"Failed to add user ['id'={db_user['id']}] in leaderboard ['guild_id'='{guild_id}'].", e)
        else:
            printlog(f"Failed to add loss to user ['id'='{db_user['id']}'] in leaderboard ['guild_id'='{guild_id}'].")
        return None
    return db_user

#######################
## MESSAGE FUNCTIONS ##
#######################

def create_server_leaderboard_embed(guild: Guild, db_leaderboard):
    embed = Embed(title=f"Server Challenge Leaderboard", color=0xFAD25A)
    embed.set_author(name=guild.name, icon_url=guild.icon.url)
    embed.add_field(name="Player", value="1. Zain")
    embed.add_field(name="Rating", value="1200")
    embed.set_footer(text=f"beta-bot | GitHub 🤖", icon_url=ICON)
    return embed

def create_player_stat_embed(db_user: dict, user: Member):
    total_matches = len(db_user['matches'])
    wins = db_user['wins']
    losses = db_user['losses']
    win_rate = "{0:.2%}".format(wins / total_matches)
    embed = Embed(title=f"📈  Leaderboard Player Stats", description=f"Stats for: <@!{db_user['id']}>", color=0xFAD25A)
    embed.set_author(name=f"{user.display_name} | {user.name}#{user.discriminator}", icon_url=user.display_avatar.url)
    embed.add_field(name="Wins", value=f"{wins}")
    embed.add_field(name="Losses", value=f"{losses}")
    embed.add_field(name="Total Challenges", value=f"{total_matches}")
    embed.add_field(name="Win Rate", value=f"{win_rate}")
    embed.set_footer(text=f"beta-bot | GitHub 🤖", icon_url=ICON)
    return embed

######################
## HELPER FUNCTIONS ##
######################

async def set_leaderboard_user(guild_id: int, user_id: int, new_user: dict):
    """
    Sets a leaderboard user in a guild to the specified document.
    """
    return await mdb.update_single_document(
        {'guild_id': guild_id, 'leaderboard.id': user_id}, 
        {'$set': {f'leaderboard.$': new_user}
        },
        GUILDS)