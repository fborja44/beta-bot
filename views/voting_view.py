import discord


class VotingView(discord.ui.View):
    def __init__(self, match, player1, player2) -> None:
        super().__init__(timeout=None)
        player1_button = VotingButton(
            id=f"{match['challonge_id']}-1", emoji="1️⃣", label=player1["name"]
        )
        player2_button = VotingButton(
            id=f"{match['challonge_id']}-2", emoji="2️⃣", label=player2["name"]
        )
        self.add_item(player1_button)
        self.add_item(player2_button)


class VotingButton(discord.ui.Button):
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
