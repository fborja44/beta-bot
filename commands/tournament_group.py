from typing import Optional, Union
from discord import app_commands, Interaction
from utils.common import MAX_ENTRANTS
from tournaments import match, participant, tournament

# /tournament app commands

TournamentGroup = app_commands.Group(name="t", description="Tournament bracket commands.", guild_ids=[133296587047829505, 713190806688628786], guild_only=True)

@TournamentGroup.command(description="Lists options for tournament bracket commands.")
async def help(interaction: Interaction):
    await interaction.response.send_message("help deez 😎")

@TournamentGroup.command(description="[Privileged] Creates a test tournament bracket.")
async def test(interaction: Interaction, num_participants: int = 4):
    await interaction.response.defer(ephemeral=True)
    await tournament.create_test_tournament(interaction, num_participants)

@TournamentGroup.command(description="Creates a tournament bracket. Times in ET. Default: double elimination.")
async def create(interaction: Interaction, tournament_title: str, time: str="", single_elim: bool = False, max_participants: int = MAX_ENTRANTS):
    await interaction.response.defer(ephemeral=True)
    await tournament.create_tournament(interaction, tournament_title.strip(), time.strip(), single_elim, max_participants)

@TournamentGroup.command(description="Join a tournament bracket.")
async def join(interaction: Interaction, tournament_title: str=""):
    await interaction.response.defer(ephemeral=True)
    await participant.join_tournament(interaction, tournament_title.strip())

@TournamentGroup.command(description="Join a tournament bracket.")
async def leave(interaction: Interaction, tournament_title: str=""):
    await interaction.response.defer(ephemeral=True)
    await participant.leave_tournament(interaction, tournament_title.strip())

@TournamentGroup.command(description="Deletes a tournament bracket.")
async def delete(interaction: Interaction, tournament_title: str=""):
    await interaction.response.defer(ephemeral=True)
    await tournament.delete_tournament(interaction, tournament_title.strip())

@TournamentGroup.command(description="Updates a tournament bracket. Times in ET.")
async def update(interaction: Interaction, tournament_title: str, new_tournament_title: str | None = None, time: str | None = None, 
                    single_elim: bool | None = None, max_participants: int | None = None):
    await interaction.response.defer(ephemeral=True)
    await tournament.update_tournament(interaction, tournament_title.strip(), new_tournament_title.strip(), time.strip(), single_elim, max_participants)

@TournamentGroup.command(description="Starts a tournament bracket.")
async def start(interaction: Interaction, tournament_title: str=""):
    await interaction.response.defer(ephemeral=True)
    await tournament.start_tournament(interaction, tournament_title.strip())

@TournamentGroup.command(description="Resets a tournament bracket.")
async def reset(interaction: Interaction, tournament_title: str=""):
    await interaction.response.defer()
    await tournament.reset_tournament(interaction, tournament_title.strip())

@TournamentGroup.command(description="Finalizes a tournament bracket.")
async def finalize(interaction: Interaction, tournament_title: str=""):
    await interaction.response.defer(ephemeral=True)
    await tournament.finalize_tournament(interaction, tournament_title.strip())

@TournamentGroup.command(description="Sends the results for a completed tournament bracket.")
async def results(interaction: Interaction, tournament_title: str=""):
    await interaction.response.defer()
    await tournament.send_results(interaction, tournament_title.strip())

@TournamentGroup.command(description="Manually reports the result for a tournament bracket match.")
async def report(interaction: Interaction, match_id: int, winner: str):
    await interaction.response.defer()
    await match.override_match_result(interaction, match_id, winner.strip())

@TournamentGroup.command(description="Manually vote for a tournament bracket match.")
async def vote(interaction: Interaction, match_id: int, vote: str):
    await interaction.response.defer(ephemeral=True)
    await match.vote_match(interaction, match_id, vote.strip())

@TournamentGroup.command(description="Disqualifies or removes an participant from a tournament bracket.")
async def disqualify(interaction: Interaction, participant_name: str, tournament_title: str=""):
    await interaction.response.defer()
    await participant.disqualify_participant_main(interaction, participant_name.strip(), tournament_title.strip())

# @TournamentGroup.command(description="Disqualifies self from a tournament bracket.")
# async def disqualify_self(interaction: Interaction):
#     await interaction.response.defer()
#     await bracket.disqualify_participant_main(interaction, interaction.user.name)