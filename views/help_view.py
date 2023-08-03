import discord


class HelpView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(GithubButton())


class GithubButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            url="https://github.com/fborja44/beta-bot",
            label="GitHub",
            style=discord.ButtonStyle.grey,
        )
