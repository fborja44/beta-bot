from discord import app_commands, Guild, Message, Interaction
from colorama import Fore, Back, Style
from common import CHALLONGE_USER, CHALLONGE_KEY, MONGO_ADDR, TOKEN
from dotenv import load_dotenv
from pprint import pprint
from pydoc import describe
from pymongo import MongoClient
import bracket
import challenge
import challonge
import discord
import guild as _guild
import leaderboard
import logging
import logger
import match
import os

# main.py
# beta-bot program

TEST_GUILD = discord.Object(id=133296587047829505)

challonge.set_credentials(CHALLONGE_USER, CHALLONGE_KEY)

print(Fore.CYAN + "Starting beta-bot..." + Style.RESET_ALL)
print(Fore.MAGENTA + "============================================" + Style.RESET_ALL)

# Add logs to discord.log
discord_logger = logging.getLogger('discord')
discord_logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
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
            self.add_view(bracket.registration_buttons_view())
            self.add_view(match.voting_buttons_view())
            self.add_view(challenge.accept_view())
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

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent): # use raw to include older messages
        # Check if reacting to self 
        if payload.user_id == self.user.id:
            return
        elif payload.emoji.name == '✅':
            # Update bracket entrants
            await bracket.update_bracket_entrants(payload, db)
        elif payload.emoji.name == '1️⃣' or payload.emoji.name == '2️⃣':
            # Update match or challenge vote
            result = await match.vote_match_reaction(payload, db)
            if not result:
                await challenge.vote_challenge_reaction(payload, db)
        elif payload.emoji.name == '🥊':
            # Update challenge status
            await challenge.accept_challenge(payload, db)
    
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent): # use raw to include older messages
        # Check if reacting to self 
        if payload.user_id == self.user.id:
            return
        elif payload.emoji.name == '✅':
            # Update bracket entrants
            await bracket.update_bracket_entrants(payload, db)
        elif payload.emoji.name == '1️⃣' or payload.emoji.name == '2️⃣':
            # Update match vote
            await match.vote_match_reaction(payload, db)

    async def on_message(self, message: Message): # Event went the bot receives a message
        if message.author == bot_client.user: # Checks if message is from self
            return

        # Send bot help message
        elif message.content.startswith('$info'):
            # TODO
            return

        # Brackets
        elif message.content.startswith('$bracket'):
            usage = 'Usage: `$bracket <option>`'
            # Parse args
            argv = message.content.split()
            argc = len(argv)
            if argc == 1:
                return await message.channel.send(usage)
            # Get option
            match argv[1].lower():
                case "create":
                    await bracket.create_bracket(message, db, argv, argc)
                case "edit":
                    await bracket.update_bracket(message, db, argv, argc)
                case "delete":
                    await bracket.delete_bracket(message, db, argv, argc)
                case "start":
                    await bracket.start_bracket(message, db, argv, argc)
                case "finalize":
                    await bracket.finalize_bracket(message, db, argv, argc)
                case "reset":
                    await bracket.reset_bracket(message, db, argv, argc)
                case "results":
                    await bracket.send_results(message, db, argv, argc)
                case "report":
                    await match.override_match_score(message, db, argv, argc)
                case "dq":
                    await bracket.disqualify_entrant_main(message, db, argv, argc)
                case "test":
                    await bracket.create_test_bracket(message, db, argv, argc)
                case _:
                    # TODO: List options
                    await message.channel.send("Command not recognized.")
            await message.delete()

        # Challenges
        elif message.content.startswith('$challenge'):
            usage = 'Usage: `$challenge <option>`'
            # Parse args
            argv = message.content.split()
            argc = len(argv)
            if argc == 1:
                return await message.channel.send(usage)
            # Get option
            match argv[1].lower():
                case "create":
                    await challenge.create_challenge_queue(message, db, argv, argc)
                case "cancel":
                    await challenge.cancel_challenge(message, db, argv, argc)
                case "delete":
                    await challenge.cancel_challenge(message, db, argv, argc, delete=True)
                case "override":
                    pass
                case "test":
                    pass
                case _:
                    if argc >= 2:
                        await challenge.create_challenge_direct(message, db, argv, argc)
                    else:
                        # TODO: list options
                        pass
            await message.delete()

        # Leaderboard
        elif message.content.startswith('$leaderboard'):
            # Parse args
            argv = message.content.split()
            argc = len(argv)
            if argc == 1:
                return await message.channel.send(usage)
            # Get option
            match argv[1].lower():
                case "stats":
                    await leaderboard.retrieve_leaderboard_user_stats(message, db, argv, argc)
                case _:
                    # TODO: list options
                    pass
            await message.delete()

intents = discord.Intents.default()
intents.members = True
bot_client = MyBot(intents=intents)
tree = app_commands.CommandTree(bot_client)

# Bracket Commands
BracketGroup = app_commands.Group(name="bracket", description="Tournament bracket commands.", guild_ids=[133296587047829505, 713190806688628786], guild_only=True)
@BracketGroup.command(description="[Privileged] Creates a test bracket.")
async def test(interaction: Interaction, num_entrants: int = 4):
    await bracket.create_test_bracket(interaction, num_entrants)

@BracketGroup.command(description="Creates a tournament bracket.")
async def create(interaction: Interaction, bracket_title: str, time: str=""):
    await bracket.create_bracket(interaction, bracket_title, time)

@BracketGroup.command(description="Deletes a tournament bracket.")
async def delete(interaction: Interaction, bracket_title: str=""):
    await bracket.delete_bracket(interaction, bracket_title)

@BracketGroup.command(description="Starts a tournament bracket.")
async def start(interaction: Interaction, bracket_title: str=""):
    await bracket.start_bracket(interaction, bracket_title)

@BracketGroup.command(description="Resets a tournament bracket.")
async def reset(interaction: Interaction, bracket_title: str=""):
    await bracket.reset_bracket(interaction, bracket_title)

@BracketGroup.command(description="Finalizes a tournament bracket.")
async def finalize(interaction: Interaction, bracket_title: str=""):
    await bracket.finalize_bracket(interaction, bracket_title)

@BracketGroup.command(description="Sends the results for a completed tournament bracket.")
async def results(interaction: Interaction, bracket_title: str=""):
    await bracket.send_results(interaction, bracket_title)

@BracketGroup.command(description="Manually reports the score for a tournament bracket match.")
async def report(interaction: Interaction, match_challonge_id: int, winner: str):
    await match.override_match_result(interaction, match_challonge_id, winner)

@BracketGroup.command(description="Disqualifies or removes an entrant from a tournament bracket.")
async def disqualify(interaction: Interaction, entrant_name: str, bracket_title: str=""):
    await bracket.disqualify_entrant_main(interaction, entrant_name, bracket_title)

# Challenge Commands
ChallengeGroup = app_commands.Group(name="challenge", description="Challenge commands.", guild_ids=[133296587047829505, 713190806688628786], guild_only=True)
@ChallengeGroup.command(description="Creates a challenge.")
async def create(interaction: Interaction, best_of: int = 3, player_mention: str = ""):
    await challenge.create_challenge(bot_client, interaction, best_of, player_mention)

@ChallengeGroup.command(description="Cancels a challenge that has not yet been completed.")
async def cancel(interaction: Interaction, challenge_id: int = None):
    await challenge.cancel_challenge(interaction, challenge_id)

@ChallengeGroup.command(description="[Privileged] Deletes a challenge.")
async def delete(interaction: Interaction, challenge_id: str = None):
    if not challenge_id.isnumeric():
        await interaction.response.send_message("`challenge_id` must be a valid integer.", ephemeral=True)
        return False
    await challenge.cancel_challenge(interaction, int(challenge_id), delete=True)

tree.add_command(BracketGroup, guild=TEST_GUILD)
tree.add_command(BracketGroup, guild=discord.Object(id=713190806688628786))

tree.add_command(ChallengeGroup, guild=TEST_GUILD)
tree.add_command(ChallengeGroup, guild=discord.Object(id=713190806688628786))

bot_client.run(TOKEN)