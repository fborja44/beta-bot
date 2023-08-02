from discord import app_commands, Interaction
from utils.constants import MAX_ENTRANTS
from tournaments import match, participant, tournament

# /tournament app commands

TournamentGroup = app_commands.Group(name="t", description="Tournament bracket commands.", guild_ids=[133296587047829505, 713190806688628786], guild_only=True)

@TournamentGroup.command(description="Lists options for tournament bracket commands.")
async def help(interaction: Interaction):
    help_embed, help_view = tournament.create_help_embed(interaction)
    await interaction.response.send_message(embed=help_embed, view=help_view, ephemeral=True)

@TournamentGroup.command(description="[Privileged] Creates a test tournament bracket.")
async def test(interaction: Interaction, num_participants: int = 4):
    await interaction.response.defer(ephemeral=True)
    await tournament.create_test_tournament(interaction, num_participants)

@TournamentGroup.command(description="Creates a tournament bracket. Times in ET. Default: double elimination.")
async def create(interaction: Interaction, title: str, time: str="", single_elim: bool = False, max_participants: int = MAX_ENTRANTS, as_thread: bool = False):
    await interaction.response.defer(ephemeral=True)
    await tournament.create_tournament(interaction, title.strip(), time.strip(), single_elim, max_participants, as_thread)

@TournamentGroup.command(description="Join a tournament bracket.")
async def join(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    await participant.join_tournament(interaction)

@TournamentGroup.command(description="Join a tournament bracket.")
async def leave(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    await participant.leave_tournament(interaction)

@TournamentGroup.command(description="Display the seeding for a tournament bracket.")
async def seeding(interaction: Interaction, title: str=""):
    await interaction.response.defer()
    await tournament.send_seeding(interaction, title.strip())

@TournamentGroup.command(description="Sets the seed for a participant in a tournament bracket.")
async def seed(interaction: Interaction, user_mention: str, seed: int, title: str=""):
    await interaction.response.defer(ephemeral=True)
    await participant.set_seed(interaction, user_mention.strip(), seed, title.strip())

@TournamentGroup.command(description="Randomize the seeding for a tournament bracket.")
async def randomize(interaction: Interaction, title: str=""):
    await interaction.response.defer(ephemeral=True)
    await participant.randomize_seeding(interaction, title.strip())

@TournamentGroup.command(description="Deletes a tournament bracket.")
async def delete(interaction: Interaction, title: str=""):
    await interaction.response.defer(ephemeral=True)
    await tournament.delete_tournament(interaction, title.strip())

@TournamentGroup.command(description="Updates a tournament bracket. Times in ET.")
async def update(interaction: Interaction, title: str, new_title: str | None = None, time: str | None = None, 
                    single_elim: bool | None = None, max_participants: int | None = None):
    await interaction.response.defer(ephemeral=True)
    await tournament.update_tournament(interaction, title, new_title, time, single_elim, max_participants)

@TournamentGroup.command(description="Starts a tournament bracket.")
async def start(interaction: Interaction, title: str=""):
    await interaction.response.defer(ephemeral=True)
    await tournament.start_tournament(interaction, title.strip())

@TournamentGroup.command(description="Resets a tournament bracket.")
async def reset(interaction: Interaction, title: str=""):
    await interaction.response.defer(ephemeral=True)
    await tournament.reset_tournament(interaction, title.strip())

@TournamentGroup.command(description="Finalizes a tournament bracket.")
async def finalize(interaction: Interaction, title: str=""):
    await interaction.response.defer(ephemeral=True)
    await tournament.finalize_tournament(interaction, title.strip())

@TournamentGroup.command(description="Sends the results for a completed tournament bracket.")
async def results(interaction: Interaction, title: str=""):
    await interaction.response.defer() # Change to ephemeral?
    await tournament.send_results(interaction, title.strip())

@TournamentGroup.command(description="Disqualifies or removes an participant from a tournament bracket.")
async def disqualify(interaction: Interaction, user_mention: str):
    await interaction.response.defer() # Change to ephemeral
    await participant.disqualify_participant_main(interaction, user_mention.strip())

@TournamentGroup.command(description="Opens the tournament bracket for registration.")
async def open(interaction: Interaction, title: str=""):
    await interaction.response.defer(ephemeral=True)
    await tournament.open_close_tournament(interaction, title.strip(), open=True)

@TournamentGroup.command(description="Opens the tournament bracket for registration.")
async def close(interaction: Interaction, title: str=""):
    await interaction.response.defer(ephemeral=True)
    await tournament.open_close_tournament(interaction, title.strip(), open=False)

@TournamentGroup.command(description="Adds a user to a tournament regardless of registration status.")
async def add(interaction: Interaction, user_mention: str, title: str=""):
    await interaction.response.defer(ephemeral=True)
    # await tournament.open_close_tournament(interaction, title.strip(), open=False)

@TournamentGroup.command(description="Removes a user from a tournament regardless of registration status.")
async def remove(interaction: Interaction, user_mention: str, title: str=""):
    await interaction.response.defer(ephemeral=True)
    # await tournament.open_close_tournament(interaction, title.strip(), open=False)