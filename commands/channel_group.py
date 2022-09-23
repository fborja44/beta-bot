from discord import app_commands, Interaction
import guilds.channel as channel

# /channel app commands

ChannelGroup = app_commands.Group(name="channel", description="Channel configuration commands.", guild_ids=[133296587047829505, 713190806688628786], guild_only=True)

@ChannelGroup.command(description="Creates a tournament channel. Forum Channels are recommended if available.")
async def create(interaction: Interaction, channel_name: str, is_forum: bool, allow_messages: bool= True, category_name: str = ""):
    await interaction.response.defer(ephemeral=True)
    await channel.create_tournament_channel(interaction, channel_name.strip(), category_name.strip(), is_forum, allow_messages)

@ChannelGroup.command(description="Deletes a tournament channel.")
async def delete(interaction: Interaction, channel_mention: str=""):
    await interaction.response.defer(ephemeral=True)
    await channel.delete_tournament_channel(interaction, channel_mention)


@ChannelGroup.command(description="Set a channel to recieve tournament alerts.")
async def alert(interaction: Interaction, channel_mention: str=""):
    await interaction.response.defer()
    await channel.add_channel_to_alerts(interaction, channel_mention)

@ChannelGroup.command(description="Remove a channel from tournament alerts list.")
async def remove_alert(interaction: Interaction, channel_mention: str=""):
    await interaction.response.defer()
    await channel.remove_channel_from_alerts(interaction, channel_mention)