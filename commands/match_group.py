from discord import app_commands, Interaction
from utils.common import MAX_ENTRANTS
from tournaments import match

# /tournament app commands

MatchGroup = app_commands.Group(name="match", description="Tournament bracket commands.", guild_ids=[133296587047829505, 713190806688628786], guild_only=True)

@MatchGroup.command(description="Manually vote for a tournament bracket match.")
async def vote(interaction: Interaction, match_id: int, vote: str):
    await interaction.response.defer(ephemeral=True)
    await match.vote_match(interaction, match_id, vote.strip())

@MatchGroup.command(description="Manually reports the result for a tournament bracket match.")
async def report(interaction: Interaction, match_id: int, winner: str):
    await interaction.response.defer()
    await match.override_match_result(interaction, match_id, winner.strip())

@MatchGroup.command(description="Resets a match and all matches dependent on it.")
async def reset(interaction: Interaction, match_id: int):
    await interaction.response.defer()
    await match.reset_match(interaction, match_id)

@MatchGroup.command(description="Recalls all missing matches in a tournament.")
async def medic(interaction: Interaction, title: str=""):
    await interaction.response.defer(ephemeral=True)
    await match.repair_match(interaction, title.strip())