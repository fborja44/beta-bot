from discord import app_commands, Guild, Member, Message, Interaction
from colorama import Fore, Back, Style
from commands import challenge_group, channel_group, leaderboard_group, tournament_group
from guilds import channel as _channel
from pprint import pprint
from pymongo import MongoClient
from tournaments import challenge, match, tournament
from utils.common import CHALLONGE_USER, CHALLONGE_KEY, MONGO_ADDR, MAX_ENTRANTS, TOKEN
from utils import logger
import challonge
import discord
import guilds.guild as _guild
import logging

# main.py
# beta-bot program

TEST_GUILD = discord.Object(id=133296587047829505)

challonge.set_credentials(CHALLONGE_USER, CHALLONGE_KEY)

print(Fore.CYAN + "Starting beta-bot..." + Style.RESET_ALL)
print(Fore.MAGENTA + "============================================" + Style.RESET_ALL)

# Add logs to discord.log
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='logs/discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
discord_logger.addHandler(handler)

# Connect to MongoDB
db_client = MongoClient(MONGO_ADDR)
db = db_client['beta-bot']
# Debugging: serverStatus
serverStatusResult = db.command("serverStatus")
if serverStatusResult:
    print('Connected to MongoDB database at ' + Fore.YELLOW + f'{MONGO_ADDR}' + Style.RESET_ALL + '\n---')

class MyBot(discord.Client):
    def __init__(self, *args, **kwargs):
        self.cmd_prefix="$" # unused
        self.synced = False # ensures commands are only synced once
        self.views = False  # ensures views are reset when bot is restarted
        super().__init__(*args, **kwargs)

    async def on_ready(self): # Event called when bot is ready
        # Sync commands
        await self.wait_until_ready()
        if not self.synced: # Do NOT reset more than once per minute
            await tree.sync(guild=TEST_GUILD) # change to global when ready
            await tree.sync(guild=discord.Object(id=713190806688628786))
            self.synced = True
        if not self.views:
            self.add_view(tournament.registration_buttons_view())
            # self.add_view(match.voting_buttons_view())
            # self.add_view(challenge.accept_view())
            # self.add_view(challenge.voting_buttons_view())
            self.views = True
        # print(Fore.YELLOW + "Updating guilds..."+ Style.RESET_ALL)
        # for guild in self.guilds:
        #     await _guild.find_update_add_guild(self, db, guild)
        print('---\n' + Fore.YELLOW + f'{bot_client.user} is now ready.' + Style.RESET_ALL)
        logger.printlog('SESSION START')

    async def on_guild_join(self, guild: Guild):
        await _guild.find_update_add_guild(db, guild)

    async def on_guild_remove(self, guild: Guild):
        await _guild.delete_guild(db, guild)

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        # Check if tournament channel; If it is, update the guild.
        guild: Guild = channel.guild
        db_guild: dict = await _guild.find_guild(guild.id)
        if channel.id in db_guild['config']['tournament_channels']:
            await _channel.delete_tournament_channel_db(db_guild, channel.id)

intents = discord.Intents.default()
intents.members = True
bot_client = MyBot(intents=intents)
tree = app_commands.CommandTree(bot_client)

tree.add_command(channel_group.ChannelGroup, guild=TEST_GUILD)
tree.add_command(channel_group.ChannelGroup, guild=discord.Object(id=713190806688628786))

tree.add_command(tournament_group.TournamentGroup, guild=TEST_GUILD)
tree.add_command(tournament_group.TournamentGroup, guild=discord.Object(id=713190806688628786))

# tree.add_command(challenge_group.ChallengeGroup, guild=TEST_GUILD)
# tree.add_command(challenge_group.ChallengeGroup, guild=discord.Object(id=713190806688628786))

# tree.add_command(leaderboard_group.LeaderboardGroup, guild=TEST_GUILD)
# tree.add_command(leaderboard_group.LeaderboardGroup, guild=discord.Object(id=713190806688628786))


bot_client.run(TOKEN)