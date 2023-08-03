import logging
import os

import challonge
import discord
from colorama import Back, Fore, Style
from discord import Guild, app_commands
from pymongo import MongoClient

import guilds.guild as _guild
from app_commands import match_group, tournament_group
from guilds import channel as _channel
import tournaments.tournament as _tournament
import tournaments.participant as _participant
from utils import log
from utils.constants import (
    CHALLONGE_KEY,
    CHALLONGE_USER,
    DISCORD_TOKEN,
    MAX_ENTRANTS,
    MONGO_ADDR,
)
from views.voting_buttons import create_voting_view

# main.py
# beta-bot tournament bot

TEST_GUILD = discord.Object(id=133296587047829505)

challonge.set_credentials(CHALLONGE_USER, CHALLONGE_KEY)

print(Fore.CYAN + "Starting beta-bot..." + Style.RESET_ALL)
print(Fore.MAGENTA + "============================================" + Style.RESET_ALL)

# Create logs directory if it doesn't exist
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Add logs to discord.log
discord_logger = logging.getLogger("discord")
discord_logger.setLevel(logging.DEBUG)
file_handler = logging.FileHandler(
    filename="logs/discord.log", encoding="utf-8", mode="w"
)
file_handler_formatter = logging.Formatter(
    "[{asctime}] [{levelname:<8}] {name}: {message}", "%Y-%m-%d %H:%M:%S", style="{"
)
file_handler.setFormatter(file_handler_formatter)
discord_logger.addHandler(file_handler)

# Connect to MongoDB
db_client = MongoClient(MONGO_ADDR)
db = db_client["beta-bot"]
# Debugging: serverStatus
serverStatusResult = db.command("serverStatus")
if serverStatusResult:
    print(
        "Connected to MongoDB database at "
        + Fore.YELLOW
        + f"{MONGO_ADDR}"
        + Style.RESET_ALL
        + "\n---"
    )


class MyBot(discord.Client):
    def __init__(self, *args, **kwargs):
        self.cmd_prefix = "$"  # unused
        self.synced = False  # ensures commands are only synced once
        super().__init__(*args, **kwargs)

    async def setup_hook(self) -> None:
        """
        Register views for persistent functionality
        """
        # Get guild tournaments from database
        guilds = await _guild.get_all_guilds()

        for db_guild in guilds:
            # Find all incomplete tournaments not in progress
            reg_tournaments = _tournament.find_registration_tournaments(db_guild)
            for tournament in reg_tournaments:
                self.add_view(
                    _tournament.registration_buttons_view(), message_id=tournament["id"]
                )

            # Find all in-progress tournaments
            active_tournament = _tournament.find_active_tournament(db_guild)
            if active_tournament:
                for match in active_tournament["matches"]:
                    if not match["completed"]:
                        player1 = _participant.find_participant(active_tournament, match["player1"]["id"])
                        player2 = _participant.find_participant(active_tournament, match["player2"]["id"])
                        voting_buttons_view = create_voting_view(match, player1, player2)
                        self.add_view(voting_buttons_view, message_id=match["id"])

        # self.add_view(challenge.accept_view())
        # self.add_view(challenge.voting_buttons_view())

    async def on_ready(self):  # Event called when bot is ready
        # Sync commands
        await self.wait_until_ready()
        if not self.synced:  # Do NOT reset more than once per minute
            await tree.sync(guild=TEST_GUILD)  # change to global when ready
            await tree.sync(guild=discord.Object(id=713190806688628786))
            self.synced = True
        # print(Fore.YELLOW + "Updating guilds..."+ Style.RESET_ALL)
        # for guild in self.guilds:
        #     await _guild.find_update_add_guild(self, db, guild)
        print(
            "---\n" + Fore.YELLOW + f"{bot_client.user} is now ready." + Style.RESET_ALL
        )
        log.printlog("SESSION START")

    async def on_guild_join(self, guild: Guild):
        await _guild.find_update_add_guild(db, guild)

    async def on_guild_remove(self, guild: Guild):
        await _guild.delete_guild(db, guild)

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        # Check if tournament channel; If it is, update the guild.
        guild: Guild = channel.guild
        db_guild: dict = await _guild.find_guild(guild.id)
        if channel.id in db_guild["config"]["tournament_channels"]:
            await _channel.delete_tournament_channel_db(db_guild, channel.id)


intents = discord.Intents.default()
intents.members = True
bot_client = MyBot(intents=intents)
tree = app_commands.CommandTree(bot_client)

# tree.add_command(channel_group.ChannelGroup, guild=TEST_GUILD)
# tree.add_command(channel_group.ChannelGroup, guild=discord.Object(id=713190806688628786))

tree.add_command(tournament_group.TournamentGroup, guild=TEST_GUILD)
tree.add_command(
    tournament_group.TournamentGroup, guild=discord.Object(id=713190806688628786)
)

tree.add_command(match_group.MatchGroup, guild=TEST_GUILD)
tree.add_command(match_group.MatchGroup, guild=discord.Object(id=713190806688628786))

# tree.add_command(challenge_group.ChallengeGroup, guild=TEST_GUILD)
# tree.add_command(challenge_group.ChallengeGroup, guild=discord.Object(id=713190806688628786))

# tree.add_command(leaderboard_group.LeaderboardGroup, guild=TEST_GUILD)
# tree.add_command(leaderboard_group.LeaderboardGroup, guild=discord.Object(id=713190806688628786))


bot_client.run(DISCORD_TOKEN)
