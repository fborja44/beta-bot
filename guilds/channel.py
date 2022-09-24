from discord import Embed, ForumChannel, Guild, Interaction, Message, Member, TextChannel, CategoryChannel, Thread
from utils.common import TOURNAMENTS
from utils.logger import printlog, printlog_msg
from tournaments import tournament as _tournament
from pprint import pprint
import challonge
import guilds.guild as _guild
import re
import utils.mdb as mdb

# channel.py
# Tournament discord channel

channel_match = re.compile(r'^<#[0-9]+>$')

async def create_tournament_channel(interaction: Interaction, channel_name: str, category_name: str, is_forum: bool, allow_messages: bool):
    """
    Creates a tournament channel.
    TODO: What happens if the channel is deleted manually and bot is offline
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)

    # Only allow author or guild admins to create a tournament channel
    if not user.guild_permissions.administrator:
        await interaction.followup.send(f"Only server admins can create a tournamnet channel.", ephemeral=True)
        return False
    # Check args
    if len(channel_name) <= 0:
        await interaction.followup.send("Channel name cannot be empty.")
        return False
    if len(channel_name) > 60:
        await interaction.followup.send("Channel name can be no longer than 60 characters.")
        return False
    # If set to forum, check if server has community features
    if is_forum and 'COMMUNITY' not in guild.features:
        await interaction.followup.send("This server cannot create forum channels. Must be a community server.")
        return False
    # Check if category is included
    if len(category_name) > 0:
        # Check if category name exists on server
        category_names = []
        map(lambda category: category_names.append(category.name), guild.categories)
        if category_name not in category_names:
            await interaction.followup.send(f"Category with name '{category_name}' does not exist in this server.")
            return False
        target_category = list(filter(lambda category: category.name == category_name, guild.categories))[0]
    else:
        target_category: CategoryChannel = interaction.channel.category
    # Create channel
    command_thread = None
    if is_forum:
        try:
            topic = "Channel for **beta-bot** Tournaments. https://github.com/fborja44/beta-bot"
            new_channel: ForumChannel = await guild.create_forum(channel_name, topic=topic, category=target_category)
            await new_channel.set_permissions(guild.default_role, create_public_threads=False, create_private_threads=False)
            command_thread, command_message = await create_command_thread(new_channel)
        except Exception as e:
            printlog("Failed to create tournament forum channel.", e)
            await interaction.followup.send(f"Failed to create tournament forum channel.")
            return False
    else:
        try:
            new_channel: TextChannel = await guild.create_text_channel(channel_name, topic="Channel for **beta-bot** Tournaments. https://github.com/fborja44/beta-bot", category=target_category)
        except Exception as e:
            printlog("Failed to create tournament forum channel.", e)
            await interaction.followup.send(f"Failed to create tournament text channel.")
            return False
    # Set message permissions
    await new_channel.set_permissions(guild.default_role, send_messages=allow_messages) # TODO: Check if this gets overwritten
    await new_channel.edit(sync_permissions=True)

    # Add channel to guild
    db_guild['config']['tournament_channels'].append({
        'id': new_channel.id,               # Parent channel ID (forum or text)
        'thread_id': command_thread.id,     # Command channel ID (thread) if it exists
        'alert_channels': [],               # Channels that will receive tournament alerts from this tournament channel
    })
    await _guild.set_guild(guild.id, db_guild)
    print(f"User '{user.name}' added tournament channel to guild.")
    await interaction.followup.send(f"Succesfully created new tournament channel <#{new_channel.id}>.")
    return True

async def set_tournament_channel(interaction: Interaction, channel_mention: str, allow_messages: bool):
    """
    TODO
    Sets an existing channel to a tournament channel.
    If channel_mention is empty, targets the current channel.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)

    # Only allow author or guild admins to set a tournament channel
    if not user.guild_permissions.administrator:
        await interaction.followup.send(f"Only server admins can set tournamnet channels.", ephemeral=True)
        return False
    # Check for metioned channel
    channel = parse_channel_mention(interaction, channel_mention)
    if not channel:
        await interaction.followup.send(f"Invalid channel mention. ex. <#{interaction.channel.id}>", ephemeral=True)
        return False
    # Check if channel is already a tournament channel
    if channel.id in db_guild['config']['tournament_channels']:
        await interaction.followup.send(f"<#{channel.id}> is already set as a tournament channel .", ephemeral=True)
        return False
    # Check if channel is Forum or Text
    if str(channel.type) == 'forum':
        await create_command_thread(channel)
        # Check if command message is present; If not, then send one
    elif str(channel.type) == 'text':
        await channel.send("This channel has been set as a tournament channel. Use `/t create` to create a new tournament!")
    else:
        await interaction.followup.send(f"Tournament channels must be a either a Text Channel or a Forum Channel.", ephemeral=True)
        return False
    # Add channel to guild
    db_guild['config']['tournament_channels'].append({
        'id': channel.id,
        'thread_id': None,
        'alert_channels': [],
    })
    await _guild.set_guild(guild.id, db_guild)
    print(f"User '{user.name}' set new tournament channel in guild.")
    await interaction.followup.send(f"Succesfully set new tournament channel <#{channel.id}>.")
    return True

async def delete_tournament_channel(interaction: Interaction, channel_mention: str):
    """
    Deletes a tournament channel from a guild (if it exists).
    If channel_mention is empty, targets the current channel.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Check if guild has a tournament channel
    if len(db_guild['config']['tournament_channels']) == 0:
        await interaction.followup.send(f"This server does not have a tournament channel.")
        return False
    # Check for metioned channel
    channel = parse_channel_mention(interaction, channel_mention)
    if not channel:
        await interaction.followup.send(f"Invalid channel mention. ex. <#{interaction.channel.id}>", ephemeral=True)
        return False
    # Check if valid tournament channel
    if 'thread' in str(channel.type):
        if not find_tournament_channel(db_guild, interaction.channel.parent_id):
            await interaction.followup.send(f"<#{channel.id}> is not a tournament channel.")
            return False
        tournament_channel_id = channel.parent_id
    else:
        if not find_tournament_channel(db_guild, channel.id):
            await interaction.followup.send(f"<#{channel.id}> is not a tournament channel.")
            return False
        tournament_channel_id = channel.id
    # Delete the channel
    try:
        tournament_channel = await guild.fetch_channel(tournament_channel_id)
    except:
        tournament_channel = None
        await interaction.followup.send("Failed to deleted tournament channel; May not exist.")
    if tournament_channel:
        # await interaction.followup.send("Successfully deleted tournament channel.")
        await tournament_channel.delete()
        printlog(f"Deleted tournament channel ['name'='{tournament_channel.name}'] from guild ['name'='{guild.name}']")
    else:
        await interaction.followup.send(f"Tournament channel not found in guild ['name'='{guild.name}']. Could not delete.")
    # Delete all brackets in channel if they have not been completed
    incomplete_tournaments = _tournament.find_incomplete_tournaments(db_guild)
    for db_tournament in incomplete_tournaments:
        try:
            await _guild.pull_from_guild(guild, TOURNAMENTS, db_tournament) # TODO: this does not work
            print("Deleted tournament ['name'={db_tournament['title']}] in database.")
        except:
            print(f"Failed to delete tournament ['name'={db_tournament['title']}].")
        try:
            challonge.tournaments.destroy(db_tournament['challonge']['id']) # delete tournament from challonge
        except Exception as e:
            printlog(f"Failed to delete tournament [id='{db_tournament['id']}] from challonge [id='{db_tournament['challonge']['id']}].", e)
    # Delete from database
    await delete_tournament_channel_db(db_guild, tournament_channel_id)
    print(f"User '{user.name}' [id={user.id}] deleted tournament channel '{channel.name}'.")
    await interaction.followup.send(f"Succesfully deleted tournament channel '{tournament_channel.name}'.")
    return  True

async def delete_tournament_channel_db(db_guild: dict, tournament_channel_id: int):
    db_guild['config']['tournament_channels'] = list(filter(lambda db_channel: db_channel['id'] != tournament_channel_id, db_guild['config']['tournament_channels']))
    await _guild.set_guild(db_guild['guild_id'], db_guild)
    print(f"Removed tournament channel ['id'='{tournament_channel_id}'] from guild ['id'='{db_guild['guild_id']}'] in database.")
    return True

async def configure_tournament_channel(interaction: Interaction):
    """
    TODO
    Configures a tournament channel
    """

async def create_command_thread(forum_channel: ForumChannel):
    """
    Creates the initial post in a forum channel where tournament commands are to be posted.
    """
    name = 'ℹ️ Tournament Management'
    content = (
            "**Tournament Discord Bot Instructions**\n"
            "This thread is used to create new tournaments and manage existing tournaments. Existing tournaments can also be managed in their respective threads.\n\n"
            "To create a new tournament use `/t create`.\n\n"
            "To view a list of possible tournament commands, use `/t help`.\n\n")
    command_thread, command_message = await forum_channel.create_thread(name=name, content=content)
    await command_thread.edit(pinned=True)
    return (command_thread, command_message)

async def add_channel_to_alerts(interaction: Interaction, tournament_channel: str, alert_channel: str):
    """
    Adds a channel to channels to receive tournament alerts for the specified tournament channel.
    tournament_channel: channel that alerts come from
    alert_channel: target channel that will receive alerts
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Only allow author or guild admins to update channel alerts
    if not user.guild_permissions.administrator:
        await interaction.followup.send(f"Only server admins can update tournament alerts.", ephemeral=True)
        return False
    # Check channel mentions
    t_channel = parse_channel_mention(interaction, tournament_channel)
    if not t_channel:
        await interaction.followup.send(f"Invalid channel mention for `tournament_channel`. ex. <#{channel.id}>", ephemeral=True)
        return False
    # Check if valid tournament channel
    db_tournament_channel = find_tournament_channel(db_guild, t_channel.id)
    if not db_tournament_channel:
        await interaction.followup.send(f"<#{t_channel.id}> is not a valid tournament channel.", ephemeral=True) # TODO: list tournament channels
        return False
    a_channel = parse_channel_mention(interaction, alert_channel)
    if not a_channel:
        await interaction.followup.send(f"Invalid channel mention for `alert_channel`. ex. <#{channel.id}>", ephemeral=True)
        return False
    # Check if a valid text channel
    if str(a_channel.type) != 'text':
        await interaction.followup.send(f"`alert_channel` must be a valid text channel to receive alerts.", ephemeral=True)
        return False
    # Add channel to guild
    db_tournament_channel['alert_channels'].append(a_channel.id)
    await set_tournament_channel(db_guild, db_tournament_channel)
    print(f"User '{user.name}' set channel ['name'='{a_channel.name}'] to receive tournament alerts from tournament channel ['name'='{t_channel.name}'].")
    await interaction.followup.send(f"<#{a_channel.id}> will now receive tournament alerts from <#{t_channel.id}>.")
    return True

async def remove_channel_from_alerts(interaction: Interaction, tournament_channel: str, alert_channel: str):
    """
    Adds a channel to channels to receive tournament alerts.
    TODO: channel mention
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Check channel mentions
    t_channel = parse_channel_mention(interaction, tournament_channel)
    if not t_channel:
        await interaction.followup.send(f"Invalid channel mention for `tournament_channel`. ex. <#{channel.id}>", ephemeral=True)
        return False
    # Check if valid tournament channel
    db_tournament_channel = find_tournament_channel(db_guild, t_channel.id)
    if not db_tournament_channel:
        await interaction.followup.send(f"<#{t_channel.id}> is not a valid tournament channel.", ephemeral=True) # TODO: list tournament channels
        return False
    a_channel = parse_channel_mention(interaction, alert_channel)
    if not a_channel:
        await interaction.followup.send(f"Invalid channel mention for `alert_channel`. ex. <#{channel.id}>", ephemeral=True)
        return False
    # Only allow author or guild admins to update channel alerts
    if not user.guild_permissions.administrator:
        await interaction.followup.send(f"Only server admins can update tournament alerts.", ephemeral=True)
        return False
    # Remove channel from alerts
    await delete_alert_channel_db(db_guild, db_tournament_channel, a_channel.id)
    await interaction.followup.send(f"<#{channel.id}> will no longer receive tournament alerts.")
    return True


######################
## HELPER FUNCTIONS ##
######################

def find_tournament_channel(db_guild: dict, channel_id: int):
    """
    Returns the tournament channel entry in the database with the given channel_id (if it exists)
    """
    guild_tournament_channels = db_guild['config']['tournament_channels']
    result = [db_channel for db_channel in guild_tournament_channels if db_channel['id'] == channel_id]
    if result:
        return result[0]
    return None

def find_tournament_channel_by_thread_id(db_guild: dict, thread_id: int):
    """
    Returns the tournament channel entry in the database with the given channel_id (if it exists)
    """
    guild_tournament_channels = db_guild['config']['tournament_channels']
    result = [db_channel for db_channel in guild_tournament_channels if db_channel['thread_id'] == thread_id]
    if result:
        return result[0]
    return None

def parse_channel_mention(interaction: Interaction, channel_mention: str):
    """
    Parses a channel mention argument.
    """
    if channel_mention is not None and len(channel_mention.strip()) > 0:
        matched_channel = channel_match.search(channel_mention)
        if matched_channel:
            return interaction.guild.get_channel_or_thread(int(channel_mention[2:-1])) or None # TODO: test
        else:
            return None
    else: 
        return interaction.channel

def find_index_in_config(db_guild: dict, target_field: str, target_key: str, target_value):
    """
    Returns the index of a dictionary in a config list.
    """
    for i, dic in enumerate(db_guild['config'][target_field]):
        if dic[target_key] == target_value:
            return i
    return -1

async def delete_alert_channel_db(db_guild: dict, db_tournament_channel: dict, alert_channel_id: int):
    db_tournament_channel['alert_channels'] = list(filter(lambda channel_id: channel_id != alert_channel_id, db_tournament_channel['alert_channels']))
    await set_tournament_channel(db_guild, db_tournament_channel)
    print(f"Removed channel ['id'='{alert_channel_id}'] from alerts from tournament channel ['id'='{db_tournament_channel['id']}'] in database.")
    return True

async def set_tournament_channel(db_guild: dict, db_tournament_channel: dict):
    """
    Updates a tournament channel in the database.
    """
    channel_index = find_index_in_config(db_guild, 'tournament_channels', 'id', db_tournament_channel['id'])
    db_guild['config']['tournament_channels'][channel_index] = db_tournament_channel
    return await _guild.set_guild(db_guild['guild_id'], db_guild)