import discord


class voting_buttons_view(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)


class voting_button(discord.ui.Button):
    def __init__(self, id, emoji, label) -> None:
        super().__init__(
            custom_id=id, emoji=emoji, label=label, style=discord.ButtonStyle.grey
        )

    async def callback(self: discord.Button, interaction: discord.Interaction):
        """
        Callback method for voting buttons.
        """
        from tournaments.match import vote_match_button
        await interaction.response.defer(ephemeral=True)
        await vote_match_button(interaction, self)
        
def create_voting_view(match, player1, player2):
    """
    Generates a voting buttons view instance for a match message.

    Args:
        match (_type_): The match to generate buttons for
        player1 (_type_): The first participant in the match
        player2 (_type_): The second participant in the match
    """
    button_view = voting_buttons_view()
    player1_button = voting_button(
        id=f"{match['challonge_id']}-1", emoji="1️⃣", label=player1["name"]
    )
    player2_button = voting_button(
        id=f"{match['challonge_id']}-2", emoji="2️⃣", label=player2["name"]
    )
    button_view.add_item(player1_button)
    button_view.add_item(player2_button)
    return button_view