from discord import app_commands, Interaction
from tournaments import challenge

# /challenge app commands

ChallengeGroup = app_commands.Group(name="challenge", description="Challenge commands.", guild_ids=[133296587047829505, 713190806688628786], guild_only=True)

@ChallengeGroup.command(description="Creates a challenge.")
async def create(interaction: Interaction, player_mention: str = "", best_of: int = 3):
    await interaction.response.defer(ephemeral=True)
    await challenge.create_challenge(interaction, player_mention.strip(), best_of)

@ChallengeGroup.command(description="Creates a direct challenge to the mentioned player.")
async def player(interaction: Interaction, player_mention: str, best_of: int = 3):
    await interaction.response.defer(ephemeral=True)
    await challenge.create_challenge(interaction, player_mention.strip(), best_of)

@ChallengeGroup.command(description="Creates a queued challenge.")
async def search(interaction: Interaction, best_of: int = 3):
    await interaction.response.defer(ephemeral=True)
    await challenge.create_challenge(interaction, None, best_of)

@ChallengeGroup.command(description="Cancels a challenge that has not yet been completed.")
async def cancel(interaction: Interaction, challenge_id: str | None = None):
    if not challenge_id.isnumeric():
        await interaction.response.send_message("`challenge_id` must be a valid integer.", ephemeral=True)
        return False
    await interaction.response.defer()
    await challenge.cancel_challenge(interaction, int(challenge_id))

@ChallengeGroup.command(description="[Privileged] Deletes a challenge.")
async def delete(interaction: Interaction, challenge_id: str):
    if not challenge_id.isnumeric():
        await interaction.response.send_message("`challenge_id` must be a valid integer.", ephemeral=True)
        return False
    await interaction.response.defer()
    await challenge.cancel_challenge(interaction, int(challenge_id), delete=True)

@ChallengeGroup.command(description="[Privileged] Manually reports the result for a challenge..")
async def report(interaction: Interaction, challenge_id: str, winner: str):
    if not challenge_id.isnumeric():
        await interaction.response.send_message("`challenge_id` must be a valid integer.", ephemeral=True)
        return False
    await interaction.response.defer()
    await challenge.override_challenge_result(interaction, int(challenge_id), winner.strip())