import discord
from guilds import guild

from modules import participant


class RegistrationView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Join", style=discord.ButtonStyle.green, custom_id="join_tournament"
    )
    async def join(
        self: discord.ui.View,
        interaction: discord.Interaction,
        button: discord.Button
    ):
        await interaction.response.defer(ephemeral=True)
        await participant.add_participant(interaction)

    @discord.ui.button(
        label="Leave", style=discord.ButtonStyle.red, custom_id="leave_tournament"
    )
    async def leave(
        self: discord.ui.View,
        interaction: discord.Interaction,
        button: discord.Button
    ):
        await interaction.response.defer(ephemeral=True)
        await participant.remove_participant(interaction)

    @discord.ui.button(
        label="Start", style=discord.ButtonStyle.blurple, custom_id="start_tournament"
    )
    async def start(
        self: discord.ui.View,
        interaction: discord.Interaction,
        button: discord.Button
    ):
        from modules.tournament import find_tournament_by_id, start_tournament

        await interaction.response.defer()
        db_guild = await guild.find_guild(interaction.guild.id)
        db_tournament = find_tournament_by_id(db_guild, interaction.message.id)
        tournament_title = db_tournament["title"]
        await start_tournament(interaction, tournament_title)
