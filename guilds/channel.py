import re
from pprint import pprint

import challonge
import discord
from discord import (CategoryChannel, Embed, ForumChannel, Guild, Interaction,
                     Member, Message, TextChannel, Thread)

import guilds.guild as _guild
import utils.mdb as mdb
from tournaments import tournament as _tournament
from utils.color import WOOP_PURPLE
from utils.constants import ICON, TOURNAMENTS
from utils.decorators import deprecated
from utils.logger import printlog, printlog_msg

# channel.py
# Tournament discord channel

channel_match = re.compile(r"^<#[0-9]+>$")


@deprecated
async def create_tournament_channel(
    interaction: Interaction, channel_name: str, target_category: str, is_forum: bool
):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.

    Creates a tournament channel.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)

    # Only allow author or guild admins to create a tournament channel
    if not user.guild_permissions.administrator:
        await interaction.followup.send(
            f"Only server admins can create a tournamnet channel.", ephemeral=True
        )
        return False
    # Check args
    if len(channel_name) <= 0:
        await interaction.followup.send("Channel name cannot be empty.")
        return False
    if len(channel_name) > 60:
        await interaction.followup.send(
            "Channel name can be no longer than 60 characters."
        )
        return False
    # If set to forum, check if server has community features
    if is_forum and "COMMUNITY" not in guild.features:
        await interaction.followup.send(
            "Unable to create forum channel. This server is not a community server. Go to `Server Settings` and select `Enable Community` to learn more."
        )
        return False
    # Check if category is included
    if len(target_category) > 0:
        # Check if category name exists on server
        category_names = []
        map(lambda category: category_names.append(category.name), guild.categories)
        if target_category not in category_names:
            await interaction.followup.send(
                f"Category with name '{target_category}' does not exist in this server."
            )
            return False
        target_category = list(
            filter(lambda category: category.name == target_category, guild.categories)
        )[0]
    else:
        target_category: CategoryChannel = interaction.channel.category
    # Create channel
    if is_forum:
        try:
            topic = "Channel for **beta-bot** Tournaments. https://github.com/fborja44/beta-bot"
            new_channel: ForumChannel = await guild.create_forum(
                channel_name, topic=topic, category=target_category
            )
            await new_channel.set_permissions(
                guild.default_role,
                create_public_threads=False,
                create_private_threads=False,
            )
            command_thread, command_message = await create_command_thread(new_channel)
        except Exception as e:
            printlog("Failed to create tournament forum channel.", e)
            await interaction.followup.send(
                f"Failed to create tournament forum channel."
            )
            return False
    else:
        try:
            new_channel: TextChannel = await guild.create_text_channel(
                channel_name,
                topic="Channel for **beta-bot** Tournaments. https://github.com/fborja44/beta-bot",
                category=target_category,
            )
        except Exception as e:
            printlog("Failed to create tournament forum channel.", e)
            await interaction.followup.send(
                f"Failed to create tournament text channel."
            )
            return False
    # Set message permissions
    await new_channel.edit(sync_permissions=True)

    # Add channel to guild
    db_guild["config"]["tournament_channels"].append(
        {
            "id": new_channel.id,  # Parent channel ID (forum or text)
            "thread_id": command_thread.id
            if is_forum
            else None,  # Command channel ID (thread) if it exists
            "alert_channels": [],  # Channels that will receive tournament alerts from this tournament channel
        }
    )
    await _guild.set_guild(guild.id, db_guild)
    print(f"User '{user.name}' added tournament channel to guild.")
    await interaction.followup.send(
        f"Succesfully created new tournament channel: <#{new_channel.id}>."
    )
    return True


@deprecated
async def set_as_tournament_channel(interaction: Interaction, channel_mention: str):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.

    Sets an existing channel to a tournament channel.
    If channel_mention is empty, targets the current channel.

    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Only allow author or guild admins to set a tournament channel
    if not user.guild_permissions.administrator:
        await interaction.followup.send(
            f"Only server admins can set tournamnet channels.", ephemeral=True
        )
        return False
    # Check for metioned channel
    channel = parse_channel_mention(interaction, channel_mention)
    if not channel:
        await interaction.followup.send(
            f"Invalid channel mention. ex. <#{interaction.channel.id}>", ephemeral=True
        )
        return False
    tournament_channel_ids = get_tournament_channel_ids(db_guild)
    # Check if channel is already a tournament channel
    if channel.id in tournament_channel_ids:
        await interaction.followup.send(
            f"<#{channel.id}> is already set as a tournament channel .", ephemeral=True
        )
        return False
    # Check if channel is Forum or Text
    if str(channel.type) == "forum":
        await create_command_thread(channel)
        # Check if command message is present; If not, then send one
    elif str(channel.type) == "text":
        await channel.send(
            "This channel has been set as a tournament channel. Use `/t create` to create a new tournament!"
        )
    else:
        await interaction.followup.send(
            f"Tournament channels must be a either a Text Channel or a Forum Channel.",
            ephemeral=True,
        )
        return False
    # Add channel to guild
    db_guild["config"]["tournament_channels"].append(
        {
            "id": channel.id,
            "thread_id": None,
            "alert_channels": [],
        }
    )
    await _guild.set_guild(guild.id, db_guild)
    print(f"User '{user.name}' set new tournament channel '{channel.name}'.")
    await interaction.followup.send(
        f"Succesfully set <#{channel.id}> as a tournament channel."
    )
    return True


async def delete_tournament_channel(interaction: Interaction, channel_mention: str):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.

    Deletes a tournament channel from a guild (if it exists).
    If channel_mention is empty, targets the current channel.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Check if guild has a tournament channel
    if len(db_guild["config"]["tournament_channels"]) == 0:
        await interaction.followup.send(
            f"This server does not have a tournament channel."
        )
        return False
    # Check for metioned channel
    tournament_channel = parse_channel_mention(interaction, channel_mention)
    if not tournament_channel:
        await interaction.followup.send(
            f"Invalid channel mention. ex. <#{interaction.channel.id}>", ephemeral=True
        )
        return False
    # Check if valid tournament channel
    if not find_tournament_channel(db_guild, tournament_channel.id):
        await interaction.followup.send(
            f"<#{tournament_channel.id}> is not a tournament channel."
        )
        return False
    # Delete the channel
    if tournament_channel:
        await interaction.followup.send(
            f"Succesfully deleted tournament channel '{tournament_channel.name}'."
        )
        await tournament_channel.delete()
        printlog(
            f"Deleted tournament channel ['name'='{tournament_channel.name}'] from guild ['name'='{guild.name}']"
        )
    # Delete all brackets in channel if they have not been completed
    incomplete_tournaments = _tournament.find_incomplete_tournaments(db_guild)
    for db_tournament in incomplete_tournaments:
        if db_tournament["channel_id"] == tournament_channel.id:
            try:
                db_guild = await _guild.pull_from_guild(
                    guild, TOURNAMENTS, db_tournament
                )
                print(
                    f"Deleted tournament ['name'='{db_tournament['title']}'] in database."
                )
            except:
                print(f"Failed to delete tournament ['name'={db_tournament['title']}].")
            try:
                challonge.tournaments.destroy(
                    db_tournament["challonge"]["id"]
                )  # delete tournament from challonge
            except Exception as e:
                printlog(
                    f"Failed to delete tournament [id='{db_tournament['id']}] from challonge [id='{db_tournament['challonge']['id']}].",
                    e,
                )
    # Delete from database
    await delete_tournament_channel_db(db_guild, tournament_channel.id)
    print(
        f"User '{user.name}' [id={user.id}] deleted tournament channel '{tournament_channel.name}'."
    )
    return True


async def delete_tournament_channel_db(db_guild: dict, tournament_channel_id: int):
    """
    ! DEPRECATED: Tournament channels are no longer supported due to unnecessary complexity
    """
    db_guild["config"]["tournament_channels"] = list(
        filter(
            lambda db_channel: db_channel["id"] != tournament_channel_id,
            db_guild["config"]["tournament_channels"],
        )
    )
    await _guild.set_guild(db_guild["guild_id"], db_guild)
    print(
        f"Removed tournament channel ['id'='{tournament_channel_id}'] from guild ['id'='{db_guild['guild_id']}'] in database."
    )
    return True


@deprecated
async def remove_as_tournament_channel(interaction: Interaction, channel_mention: str):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.

    Removes a channel from being a tournament channel without deleting it from discord.
    If channel_mention is empty, targets the current channel.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Only allow author or guild admins to set a tournament channel
    if not user.guild_permissions.administrator:
        await interaction.followup.send(
            f"Only server admins can set tournamnet channels.", ephemeral=True
        )
        return False
    # Check for metioned channel
    channel = parse_channel_mention(interaction, channel_mention)
    if not channel:
        await interaction.followup.send(
            f"Invalid channel mention. ex. <#{interaction.channel.id}>", ephemeral=True
        )
        return False
    tournament_channel_ids = get_tournament_channel_ids(db_guild)
    # Check if channel is already a tournament channel
    if channel.id not in tournament_channel_ids:
        await interaction.followup.send(
            f"<#{channel.id}> is not set as tournament channel .", ephemeral=True
        )
        return False
    # Check if the channel has an active tournament
    active_tournament = _tournament.find_active_tournament(db_guild)
    if active_tournament is not None and active_tournament["channel_id"] == channel.id:
        await interaction.follow.send(
            f"Unable to remove tournament channel. This channel has an active tournament '***{active_tournament['title']}***'."
        )
        return False
    # Delete incomplete tournaments
    incomplete_tournaments = _tournament.find_incomplete_tournaments(db_guild)
    for db_tournament in incomplete_tournaments:
        if db_tournament["channel_id"] == channel.id:
            await _tournament.delete_tournament(
                interaction, db_tournament["title"], respond=False
            )
    # Delete from database
    await delete_tournament_channel_db(db_guild, channel.id)
    print(
        f"User '{user.name}#{user.discriminator}' removed tournament channel '{channel.name}'."
    )
    await interaction.followup.send(
        f"Succesfully removed <#{channel.id}> as a tournament channel."
    )
    return True


@deprecated
async def repair_tournament_channel(interaction: Interaction, channel_mention: str):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.

    Recreates the management thread in a tournament forum channel.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Check if guild has a tournament channel
    if len(db_guild["config"]["tournament_channels"]) == 0:
        await interaction.followup.send(
            f"This server does not have a tournament channel."
        )
        return False
    # Check for metioned channel
    tournament_channel = parse_channel_mention(interaction, channel_mention)
    if not tournament_channel:
        await interaction.followup.send(
            f"Invalid channel mention. ex. <#{interaction.channel.id}>", ephemeral=True
        )
        return False
    # Check if valid tournament channel
    db_tournament_channel = find_tournament_channel(db_guild, tournament_channel.id)
    if not db_tournament_channel:
        await interaction.followup.send(
            f"<#{tournament_channel.id}> is not a tournament channel."
        )
        return False
    if str(tournament_channel.type) != "forum":
        await interaction.followup.send(
            "This command is only available for Forum Tournament Channels.",
            ephemeral=True,
        )
    # Repair management thread
    tournament_channel_thread = guild.get_thread(db_tournament_channel["thread_id"])
    pprint(tournament_channel_thread)
    if tournament_channel_thread:
        await tournament_channel_thread.delete()
    command_thread, _ = await create_command_thread(tournament_channel)
    # Update guild config
    index = find_index_in_config(
        db_guild, "tournament_channels", "id", db_tournament_channel["id"]
    )
    db_guild["config"]["tournament_channels"][index].update(
        {"thread_id": command_thread.id}
    )
    await _guild.set_guild(guild.id, db_guild)
    printlog(
        f"User '{user.name}#{user.discriminator}' repaired tournament channel '{tournament_channel.name}' ['id'='{tournament_channel.id}']."
    )
    if interaction.channel.id != tournament_channel.id:
        await interaction.followup.send(
            f"Succesfully repaired tournament channel <#{tournament_channel.id}>.",
            ephemeral=True,
        )
    return True


@deprecated
async def configure_tournament_channel(interaction: Interaction):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.

    Configures a tournament channel.
    """
    pass

@deprecated
async def create_command_thread(forum_channel: ForumChannel):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.
    
    Creates the initial post in a forum channel where tournament commands are to be posted.
    """
    name = "ℹ️ Tournament Hub"
    content = (
        "**Tournament Discord Bot Instructions**\n"
        "This thread is used to create new tournaments and manage existing tournaments. Existing tournaments can also be managed in their respective threads.\n\n"
        "Tournaments are configured entirely through Discord, including registration, seeding, bracket type, and capacity. Match reporting and disqualifications are also managed through Discord.\n\n"
        "**Basic Instructions**\n"
        "- To create a new tournament use `/t create`.\n"
        "- To join, leave, or start an existing tournament, use the interactable buttons found under the tournament message.\n"
        "- To view a list of available tournament commands, use `/t help`.\n"
        "- For detailed documentation and information about commands visit the GitHub page: https://github.com/fborja44/beta-bot."
    )
    command_thread, command_message = await forum_channel.create_thread(
        name=name, content=content
    )
    await command_thread.edit(pinned=True)
    return (command_thread, command_message)

@deprecated
async def add_channel_to_alerts(
    interaction: Interaction, tournament_channel: str, alert_channel: str
):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.
    
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
        await interaction.followup.send(
            f"Only server admins can update tournament alerts.", ephemeral=True
        )
        return False
    # Check channel mentions
    t_channel: ForumChannel | TextChannel = parse_channel_mention(
        interaction, tournament_channel
    )
    if not t_channel:
        await interaction.followup.send(
            f"Invalid channel mention for `tournament_channel`. ex. <#{channel.id}>",
            ephemeral=True,
        )
        return False
    # Check if valid tournament channel
    db_tournament_channel = find_tournament_channel(db_guild, t_channel.id)
    if not db_tournament_channel:
        channel_id_list = get_tournament_channel_ids(db_guild)
        channel_embed = create_channel_list_embed(
            channel_id_list, f"Tournament Channels for '{guild.name}'"
        )
        await interaction.followup.send(
            f"<#{t_channel.id}> is not a valid tournament channel.",
            embed=channel_embed,
            ephemeral=True,
        )
        return False
    a_channel: TextChannel = parse_channel_mention(interaction, alert_channel)
    if not a_channel:
        await interaction.followup.send(
            f"Invalid channel mention for `alert_channel`. ex. <#{channel.id}>",
            ephemeral=True,
        )
        return False
    # Check if a valid text channel
    if str(a_channel.type) != "text":
        await interaction.followup.send(
            f"`alert_channel` must be a valid text channel to receive alerts.",
            ephemeral=True,
        )
        return False
    # Check if sending alerts to self
    if a_channel.id == t_channel.id:
        await interaction.followup.send(
            f"`alert_channel` cannot be the same as `tournament_channel`.",
            ephemeral=True,
        )
        return False
    # Add channel to guild
    db_tournament_channel["alert_channels"].append(a_channel.id)
    await set_tournament_channel(db_guild, db_tournament_channel)
    print(
        f"User '{user.name}' set channel ['name'='{a_channel.name}'] to receive tournament alerts from tournament channel ['name'='{t_channel.name}']."
    )
    await interaction.followup.send(
        f"<#{a_channel.id}> will now receive tournament alerts from <#{t_channel.id}>."
    )
    return True

@deprecated
async def remove_channel_from_alerts(
    interaction: Interaction, tournament_channel: str, alert_channel: str
):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.
    
    Adds a channel to channels to receive tournament alerts.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Check channel mentions
    t_channel = parse_channel_mention(interaction, tournament_channel)
    if not t_channel:
        await interaction.followup.send(
            f"Invalid channel mention for `tournament_channel`. ex. <#{channel.id}>",
            ephemeral=True,
        )
        return False
    # Check if valid tournament channel
    db_tournament_channel = find_tournament_channel(db_guild, t_channel.id)
    if not db_tournament_channel:
        channel_id_list = get_tournament_channel_ids(db_guild)
        channel_embed = create_channel_list_embed(
            channel_id_list, f"Tournament Channels for '{guild.name}'"
        )
        await interaction.followup.send(
            f"<#{t_channel.id}> is not a valid tournament channel.",
            embed=channel_embed,
            ephemeral=True,
        )
        return False
    a_channel = parse_channel_mention(interaction, alert_channel)
    if not a_channel:
        await interaction.followup.send(
            f"Invalid channel mention for `alert_channel`. ex. <#{channel.id}>",
            ephemeral=True,
        )
        return False
    # Only allow author or guild admins to update channel alerts
    if not user.guild_permissions.administrator:
        await interaction.followup.send(
            f"Only server admins can update tournament alerts.", ephemeral=True
        )
        return False
    # Remove channel from alerts
    await delete_alert_channel_db(db_guild, db_tournament_channel, a_channel.id)
    await interaction.followup.send(
        f"<#{channel.id}> will no longer receive tournament alerts."
    )
    return True

@deprecated
async def list_tournament_channels(interaction: Interaction):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.
    
    Lists all tournament channels in the server.
    """
    guild: Guild = interaction.guild
    db_guild = await _guild.find_add_guild(guild)
    channel_id_list = get_tournament_channel_ids(db_guild)
    list_embed = create_channel_list_embed(
        channel_id_list, f"Tournament Channels for '{guild.name}'"
    )
    await interaction.followup.send(embed=list_embed, ephemeral=True)
    return True

@deprecated
async def list_alert_channels(interaction: Interaction, tournament_channel: str):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.
    
    Lists all channels receiving alerts from the target tournament channel.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    db_guild = await _guild.find_add_guild(guild)
    # Check channel mentions
    t_channel = parse_channel_mention(interaction, tournament_channel)
    if not t_channel:
        await interaction.followup.send(
            f"Invalid channel mention for `tournament_channel`. ex. <#{channel.id}>",
            ephemeral=True,
        )
        return False
    # Check if valid tournament channel
    db_tournament_channel = find_tournament_channel(db_guild, t_channel.id)
    if not db_tournament_channel:
        channel_id_list = get_tournament_channel_ids(db_guild)
        channel_embed = create_channel_list_embed(
            channel_id_list, f"Tournament Channels for '{guild.name}'"
        )
        await interaction.followup.send(
            f"<#{t_channel.id}> is not a valid tournament channel.",
            embed=channel_embed,
            ephemeral=True,
        )
        return False
    channel_id_list = db_tournament_channel["alert_channels"]
    list_embed = create_channel_list_embed(
        channel_id_list, f"Alert Channels for '{t_channel.name}'"
    )
    await interaction.followup.send(embed=list_embed, ephemeral=True)


######################
## HELPER FUNCTIONS ##
######################

@deprecated
def find_tournament_channel(db_guild: dict, channel_id: int):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.
    
    Returns the tournament channel entry in the database with the given channel_id (if it exists)
    """
    guild_tournament_channels = db_guild["config"]["tournament_channels"]
    result = [
        db_channel
        for db_channel in guild_tournament_channels
        if db_channel["id"] == channel_id
    ]
    if result:
        return result[0]
    return None

@deprecated
def find_tournament_channel_by_thread_id(db_guild: dict, thread_id: int):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.
    
    Returns the tournament channel entry in the database with the given channel_id (if it exists)
    """
    guild_tournament_channels = db_guild["config"]["tournament_channels"]
    result = [
        db_channel
        for db_channel in guild_tournament_channels
        if db_channel["thread_id"] == thread_id
    ]
    if result:
        return result[0]
    return None

@deprecated
def parse_channel_mention(interaction: Interaction, channel_mention: str):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.
    
    Parses a channel mention argument.
    """
    if channel_mention is not None and len(channel_mention.strip()) > 0:
        matched_channel = channel_match.search(channel_mention)
        if matched_channel:
            return (
                interaction.guild.get_channel_or_thread(int(channel_mention[2:-1]))
                or None
            )
        else:
            return None
    else:
        if "thread" in str(interaction.channel.type):
            return interaction.channel.parent or interaction.channel
        else:
            return interaction.channel

@deprecated
def find_index_in_config(
    db_guild: dict, target_field: str, target_key: str, target_value
):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.
    
    Returns the index of a dictionary in a config list.
    """
    for i, dic in enumerate(db_guild["config"][target_field]):
        if dic[target_key] == target_value:
            return i
    return -1

@deprecated
async def delete_alert_channel_db(
    db_guild: dict, db_tournament_channel: dict, alert_channel_id: int
):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.
    
    Deletes an alert channel in the database
    """
    db_tournament_channel["alert_channels"] = list(
        filter(
            lambda channel_id: channel_id != alert_channel_id,
            db_tournament_channel["alert_channels"],
        )
    )
    await set_tournament_channel(db_guild, db_tournament_channel)
    print(
        f"Removed channel ['id'='{alert_channel_id}'] from alerts from tournament channel ['id'='{db_tournament_channel['id']}'] in database."
    )
    return True

@deprecated
async def set_tournament_channel(db_guild: dict, db_tournament_channel: dict):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.
    
    Updates a tournament channel in the database.
    """
    channel_index = find_index_in_config(
        db_guild, "tournament_channels", "id", db_tournament_channel["id"]
    )
    db_guild["config"]["tournament_channels"][channel_index] = db_tournament_channel
    return await _guild.set_guild(db_guild["guild_id"], db_guild)

@deprecated
def get_tournament_channel_ids(db_guild):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.
    
    Returns a list of tournament channel ids.
    """
    return [channel["id"] for channel in db_guild["config"]["tournament_channels"]]


def in_forum(interaction: Interaction):
    """
    Returns whether or not an interaction was sent in a thread of a forum channel.
    """
    return (
        "thread" in str(interaction.channel.type)
        and str(interaction.channel.parent.type) == "forum"
    )


#######################
## MESSAGE FUNCTIONS ##
#######################

@deprecated
def create_channel_list_embed(channel_id_list: list, list_title: str):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.
    
    Creates a channel list embed.
    """
    embed = Embed(title=f"💬  {list_title}", description="", color=WOOP_PURPLE)
    embed.set_author(
        name="beta-bot | GitHub 🤖",
        url="https://github.com/fborja44/beta-bot",
        icon_url=ICON,
    )
    # Create channels list
    if len(channel_id_list) == 0:
        embed.description = "> `No channels found.`"
        return embed
    for i in range(0, len(channel_id_list)):
        embed.description += f"> **{i+1}.** <#{channel_id_list[i]}>\n"
    # Footer
    embed.set_footer(text=f"For a list of channel commands, use `/ch help`.")
    return embed

@deprecated
def create_help_embed(interaction: Interaction):
    """
    ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.
    
    Creates a channel help embed
    """
    embed = Embed(title=f"❔ Channel Help", color=WOOP_PURPLE)
    embed.description = (
        "Channel configuration commands. Only available to server admins."
    )
    embed.set_author(
        name="beta-bot | GitHub 🤖",
        url="https://github.com/fborja44/beta-bot",
        icon_url=ICON,
    )
    # Create
    create_value = """Create a tournament channel.
                    `/ch create channel_name: ssbm is_forum: True`
                    `/ch create channel_name: ssbm is_forum: False allow_messages: False`
                    `/ch create channel_name: ssbm is_forum: False category_name: games`"""
    embed.add_field(name="/ch create", value=create_value, inline=False)
    # Set
    create_value = """Sets an existing channel to be a tournament channel.
                    `/ch set`
                    `/ch set channel_mention: ssbm`"""
    embed.add_field(name="/ch set", value=create_value, inline=False)
    # List
    list_value = """Lists all current tournament channels.
                    `/ch list`"""
    embed.add_field(name="/ch list", value=list_value, inline=False)
    # Remove
    remove_value = """Removes a channel as a tournament channel. All incomplete tournaments are deleted.
                    `/ch remove`
                    `/ch remove channel_mention: ssbm`"""
    embed.add_field(name="/ch remove", value=remove_value, inline=False)
    # Delete
    delete_value = """Deletes a tournament channel. All incomplete tournaments are also deleted.
                    `/ch delete`
                    `/ch delete channel_mention: ssbm`"""
    embed.add_field(name="/ch delete", value=delete_value, inline=False)
    # Join
    delete_value = f"""Delete a tournament channel.
                    `/ch delete`
                    `/ch delete channel_mention: `<#{interaction.channel_id}>"""
    embed.add_field(name="/ch join", value=delete_value, inline=False)
    # Add Alert
    alert_value = f"""Send alerts for a tournament channel to a text channel.
                    `/ch alert tournament_channel: `<#{interaction.channel_id}>
                    `/ch alert tournament_channel: `<#{interaction.channel_id}> `alert_channel: `<#{interaction.guild.text_channels[0].id}>"""
    embed.add_field(name="/ch leave", value=alert_value, inline=False)
    # Remove Alert
    remove_alert_value = f"""Removes a text channel from receiving alerts.
                    `/ch remove_alert tournament_channel: `<#{interaction.channel_id}>
                    `/ch remove_alert tournament_channel: `<#{interaction.channel_id}> `alert_channel: `<#{interaction.guild.text_channels[0].id}>"""
    embed.add_field(name="/ch delete", value=remove_alert_value, inline=False)
    # List Alerts
    remove_alert_value = f"""Lists all channels receiving alerts from the target tournament channel.
                    `/ch list_alerts`
                    `/ch list_alerts tournament_channel: `<#{interaction.channel_id}>"""
    embed.add_field(name="/ch delete", value=remove_alert_value, inline=False)
    # Footer
    embed.set_footer(text=f"For more detailed docs, see the README on GitHub.")
    # GitHub Button
    view = discord.ui.View(timeout=None)
    github_button = discord.ui.Button(
        label="GitHub",
        url="https://github.com/fborja44/beta-bot",
        style=discord.ButtonStyle.grey,
    )
    view.add_item(github_button)
    return (embed, view)
