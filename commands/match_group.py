from discord import app_commands, Interaction
from utils.common import MAX_ENTRANTS
from tournaments import match, participant, tournament

# /tournament app commands

MatchGroup = app_commands.Group(name="match", description="Tournament bracket commands.", guild_ids=[133296587047829505, 713190806688628786], guild_only=True)