from typing import Optional, Union
from discord import app_commands, Interaction
from utils.common import MAX_ENTRANTS
from tournaments import bracket, match

# /bracket app commands

BracketGroup = app_commands.Group(name="bracket", description="Tournament bracket commands.", guild_ids=[133296587047829505, 713190806688628786], guild_only=True)

@BracketGroup.command(description="Lists options for bracket commands.")
async def help(interaction: Interaction):
    await interaction.response.send_message("help deez 😎")

@BracketGroup.command(description="[Privileged] Creates a test bracket.")
async def test(interaction: Interaction, num_entrants: int = 4):
    await interaction.response.defer(ephemeral=True)
    await bracket.create_test_bracket(interaction, num_entrants)

@BracketGroup.command(description="Creates a tournament bracket. Times in ET. Default: double elimination.")
async def create(interaction: Interaction, bracket_title: str, time: str="", single_elim: bool = False, max_entrants: int = MAX_ENTRANTS):
    await interaction.response.defer(ephemeral=True)
    await bracket.create_bracket(interaction, bracket_title.strip(), time.strip(), single_elim, max_entrants)

@BracketGroup.command(description="Deletes a tournament bracket.")
async def delete(interaction: Interaction, bracket_title: str=""):
    await interaction.response.defer(ephemeral=True)
    await bracket.delete_bracket(interaction, bracket_title.strip())

@BracketGroup.command(description="Updates a tournament bracket. Times in ET.")
async def update(interaction: Interaction, bracket_title: str, new_bracket_title: str | None = None, time: str | None = None, 
                    single_elim: bool | None = None, max_entrants: int | None = None):
    await interaction.response.defer(ephemeral=True)
    await bracket.update_bracket(interaction, bracket_title.strip(), new_bracket_title.strip(), time.strip(), single_elim, max_entrants)

@BracketGroup.command(description="Starts a tournament bracket.")
async def start(interaction: Interaction, bracket_title: str=""):
    await interaction.response.defer(ephemeral=True)
    await bracket.start_bracket(interaction, bracket_title.strip())

@BracketGroup.command(description="Resets a tournament bracket.")
async def reset(interaction: Interaction, bracket_title: str=""):
    await interaction.response.defer()
    await bracket.reset_bracket(interaction, bracket_title.strip())

@BracketGroup.command(description="Finalizes a tournament bracket.")
async def finalize(interaction: Interaction, bracket_title: str=""):
    await interaction.response.defer(ephemeral=True)
    await bracket.finalize_bracket(interaction, bracket_title.strip())

@BracketGroup.command(description="Sends the results for a completed tournament bracket.")
async def results(interaction: Interaction, bracket_title: str=""):
    await interaction.response.defer()
    await bracket.send_results(interaction, bracket_title.strip())

@BracketGroup.command(description="Manually reports the result for a tournament bracket match.")
async def report(interaction: Interaction, match_id: int, winner: str):
    await interaction.response.defer()
    await match.override_match_result(interaction, match_id, winner.strip())

@BracketGroup.command(description="Disqualifies or removes an entrant from a tournament bracket.")
async def disqualify(interaction: Interaction, entrant_name: str, bracket_title: str=""):
    await interaction.response.defer()
    await bracket.disqualify_entrant_main(interaction, entrant_name.strip(), bracket_title.strip())

# @BracketGroup.command(description="Disqualifies self from a tournament bracket.")
# async def disqualify_self(interaction: Interaction):
#     await interaction.response.defer()
#     await bracket.disqualify_entrant_main(interaction, interaction.user.name)