from discord import app_commands, Interaction
from tournaments import leaderboard

# /leaderboard app commands

LeaderboardGroup = app_commands.Group(name="leaderboard", description="Leaderboard commands.", guild_ids=[133296587047829505, 713190806688628786], guild_only=True)

@app_commands.command(description="Retrieves the leaderboard stats for a player.")
async def player(interaction: Interaction, player_mention: str=""):
    await interaction.response.defer(ephemeral=True)
    await leaderboard.retrieve_leaderboard_user_stats(interaction, player_mention.strip())