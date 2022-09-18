from utils.common import BRACKETS, GUILDS, ICON, IMGUR_CLIENT_ID, IMGUR_URL, MAX_ENTRANTS
from discord import Embed, ForumChannel, Guild, Interaction, Message, Member, TextChannel, CategoryChannel
from utils.logger import printlog, printlog_msg
from pprint import pprint
import discord
import guilds.guild as _guild
import tournaments.match as _match

# channel.py
# Tournament discord channel

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
        await interaction.followup.send(f"Only the author or server admins can create a tournamnet channel.", ephemeral=True)
        return False
    # Check if guild already has a set tournament channel
    tournament_channel = db_guild['config']['tournament_channel']
    if tournament_channel:
        # Check if the channel still exists
        if guild.get_channel(tournament_channel['id']):        
            await interaction.followup.send(f"This server already has a set tournament channel: <#{tournament_channel['id']}>.")
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
    if is_forum:
        try:
            new_channel: ForumChannel = await guild.create_forum(channel_name, topic="Channel for **beta-bot** Tournaments. https://github.com/fborja44/beta-bot", category=target_category, reason=f"{user.name} set tournament channel.", sync_permissions=True)
            new_channel.set_permissions(guild.default_role, create_public_threads=False, create_private_threads=False)
        except:
            await interaction.followup.send(f"Failed to create tournament forum channel.")
            return False
    else:
        try:
            new_channel: TextChannel = await guild.create_text_channel(channel_name, topic="Channel for **beta-bot** Tournaments. https://github.com/fborja44/beta-bot", category=target_category, reason=f"{user.name} set tournament channel.", sync_permissions=True)
        except:
            await interaction.followup.send(f"Failed to create tournament text channel.")
            return False
    # Set message permissions
    await new_channel.set_permissions(guild.default_role, send_messages=allow_messages)
    # Add channel to guild
    db_guild['config']['tournament_channel'] = {
        'id': new_channel.id,
        'type': new_channel.type
    }
    await _guild.set_guild(guild.id, db_guild)
    print(f"User '{user.name}' added tournament channel to guild.")
    await interaction.followup.send(f"Succesfully created new tournament channel <#{new_channel.id}>.")
    return True

async def set_tournament_channel(interaction: Interaction):
    """
    TODO
    Sets the tournament channel in a guild if it does not already exist.
    """

async def delete_tournament_channel(interaction: Interaction):
    """
    Deletes a tournament channel from a guild (if it exists).
    """
    guild: Guild = interaction.guild
    db_guild = await _guild.find_add_guild(guild)
    # Check if guild has a tournament channel
    if not db_guild['config']['tournament_channel']:
        await interaction.followup.send(f"This server does not have a tournament channel.")
        return False
    # Delete the channel
    try:
        tournament_channel = await guild.fetch_channel(db_guild['config']['tournament_channel']['id'])
    except:
        tournament_channel = None
        await interaction.followup.send("Failed to deleted tournament channel; May not exist.")
    if tournament_channel:
        await tournament_channel.delete()
        printlog(f"Deleted tournament channel ['name'='{tournament_channel.name}'] from guild ['name'='{guild.name}']")
    else:
        await interaction.followup.send(f"Tournament channel not found in guild ['name'='{guild.name}']. Could not delete.")
    # Delete from database
    await delete_tournament_channel_db(db_guild)
    if tournament_channel:
        await interaction.followup.send("Successfully deleted tournament channel.")
    return  True

async def delete_tournament_channel_db(db_guild: dict=None):
    db_guild['config']['tournament_channel'] = None
    await _guild.set_guild(db_guild['guild_id'], db_guild)
    print(f"Removed tournament channel from guild ['id'={db_guild['guild_id']}] in database.")
    return True


async def configure_tournament_channel(interaction: Interaction):
    """
    TODO
    Configures a tournament channel
    """