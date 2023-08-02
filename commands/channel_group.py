from discord import app_commands, Interaction
import guilds.channel as channel
from tournaments import tournament

# /channel app commands
# ! [DEPRECATED]: Tournament channels are no longer supported due to unnecessary complexity.

ChannelGroup = app_commands.Group(name="ch", description="Channel configuration commands.", guild_ids=[133296587047829505, 713190806688628786], guild_only=True)

@ChannelGroup.command(description="Lists options for tournament channel commands.")
async def help(interaction: Interaction):
    help_embed, help_view = channel.create_help_embed(interaction)
    await interaction.response.send_message(embed=help_embed, view=help_view, ephemeral=True)

@ChannelGroup.command(description="Creates a tournament channel. Forum Channels are recommended if available.")
async def create(interaction: Interaction, channel_name: str, is_forum: bool, target_category: str = ""):
    await interaction.response.defer(ephemeral=True)
    await channel.create_tournament_channel(interaction, channel_name.strip(), target_category.strip(), is_forum)

@ChannelGroup.command(description="Sets a channel to be a tournament channel. Forum Channels are recommended if available.")
async def set(interaction: Interaction, channel_mention: str=""):
    await interaction.response.defer(ephemeral=True)
    await channel.set_as_tournament_channel(interaction, channel_mention.strip())

@ChannelGroup.command(description="Removes a channel as tournament channel without deleting it.")
async def remove(interaction: Interaction, channel_mention: str=""):
    await interaction.response.defer(ephemeral=True)
    await channel.remove_as_tournament_channel(interaction, channel_mention.strip())

@ChannelGroup.command(description="Lists all current tournament channels.")
async def list(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    await channel.list_tournament_channels(interaction)

@ChannelGroup.command(description="Deletes a tournament channel.")
async def delete(interaction: Interaction, channel_mention: str=""):
    await interaction.response.defer(ephemeral=True)
    await channel.delete_tournament_channel(interaction, channel_mention)

@ChannelGroup.command(description="Recreates the management thread in a tournament forum channel.")
async def repair(interaction: Interaction, channel_mention: str):
    await interaction.response.defer(ephemeral=True)
    await channel.repair_tournament_channel(interaction, channel_mention)

@ChannelGroup.command(description="Set a channel to recieve tournament alerts.")
async def alert(interaction: Interaction, tournament_channel: str, alert_channel: str = ""):
    await interaction.response.defer()
    await channel.add_channel_to_alerts(interaction, tournament_channel, alert_channel)

@ChannelGroup.command(description="Lists all channels receiving alerts from the target tournament channel.")
async def list_alerts(interaction: Interaction, tournament_channel: str=""):
    await interaction.response.defer(ephemeral=True)
    await channel.list_alert_channels(interaction, tournament_channel)

@ChannelGroup.command(description="Remove a channel from tournament alerts list.")
async def remove_alert(interaction: Interaction, tournament_channel: str, alert_channel: str = ""):
    await interaction.response.defer()
    await channel.remove_channel_from_alerts(interaction, tournament_channel, alert_channel)