from discord import Guild, Message
from colorama import Fore, Back, Style
from common import CHALLONGE_USER, CHALLONGE_KEY, MONGO_ADDR, TOKEN
from dotenv import load_dotenv
from pprint import pprint
from pydoc import describe
from pymongo import MongoClient
import bracket
import command
import challenge
import challonge
import discord
import favorite
import guild as _guild
import logging
import logger
import match
import os

# main.py
# beta-bot program

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
    print('Connected to MongoDB database at ' + Fore.YELLOW + f'{MONGO_ADDR}' + Style.RESET_ALL)

class MyBot(discord.Client):
    def __init__(self, *args, **kwargs):
        self.cmd_prefix="$" # unused
        super().__init__(*args, **kwargs)

    async def on_ready(self): # Event called when bot is ready
        # print(Fore.YELLOW + "Updating guilds..."+ Style.RESET_ALL)
        # for guild in self.guilds:
        #     await _guild.find_update_add_guild(self, db, guild)
        print('---\n' + Fore.YELLOW + f'{bot_client.user} is now ready.' + Style.RESET_ALL)
        logger.printlog('SESSION START')

    async def on_guild_join(self, guild: Guild):
        await _guild.find_update_add_guild(self, db, guild)

    async def on_guild_remove(self, guild: Guild):
        await _guild.delete_guild(self, db, guild)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent): # use raw to include older messages
        # Check if reacting to self 
        if payload.user_id == self.user.id:
            return
        # if payload.emoji.name == '⭐':
        #     # Update favorites
        #     await favorite.update_favorite(self, payload, db)
        elif payload.emoji.name == '✅':
            # Update bracket entrants
            await bracket.update_bracket_entrants(self, payload, db)
        elif payload.emoji.name == '1️⃣' or payload.emoji.name == '2️⃣':
            # Update match or challenge vote
            result = await match.vote_match_reaction(self, payload, db)
            if not result:
                await challenge.vote_challenge_reaction(self, payload, db)
        elif payload.emoji.name == '🥊':
            # Update challenge status
            await challenge.accept_challenge(self, payload, db)
    
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent): # use raw to include older messages
        # Check if reacting to self 
        if payload.user_id == self.user.id:
            return
        # if payload.emoji.name == '⭐':
        #     # Update favorites
        #     await favorite.update_favorite(self, payload, db)
        elif payload.emoji.name == '✅':
            # Update bracket entrants
            await bracket.update_bracket_entrants(self, payload, db)
        elif payload.emoji.name == '1️⃣' or payload.emoji.name == '2️⃣':
            # Update match vote
            await match.vote_match_reaction(self, payload, db)

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
                    await bracket.create_bracket(self, message, db, argv, argc)
                case "edit":
                    await bracket.update_bracket(self, message, db, argv, argc)
                case "delete":
                    await bracket.delete_bracket(self, message, db, argv, argc)
                case "start":
                    await bracket.start_bracket(self, message, db, argv, argc)
                case "finalize":
                    await bracket.finalize_bracket(self, message, db, argv, argc)
                case "reset":
                    await bracket.reset_bracket(self, message, db, argv, argc)
                case "results":
                    await bracket.send_results(self, message, db, argv, argc)
                case "report":
                    await match.override_match_score(self, message, db, argv, argc)
                case "dq":
                    await bracket.disqualify_entrant_main(self, message, db, argv, argc)
                case "test":
                    await bracket.create_test_bracket(self, message, db, argv, argc)
                case _:
                    # TODO: List options
                    await message.channel.send("Command not recognized.")
            # await message.delete()

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
                    await challenge.create_challenge_queue(self, message, db, argv, argc)
                case "cancel":
                    await challenge.cancel_challenge(self, message, db, argv, argc)
                case "delete":
                    await challenge.cancel_challenge(self, message, db, argv, argc, delete=True)
                case "override":
                    pass
                case "test":
                    pass
                case _:
                    if argc >= 2:
                        await challenge.create_challenge_direct(self, message, db, argv, argc)
                    else:
                        # TODO: list options
                        pass
            await message.delete()

        # Commands
        # elif message.content.startswith('$cmd'): 
        #     usage = 'Usage: `$cmd <option>`'
        #     # Parse args
        #     argv = message.content.split()
        #     argc = len(argv)
        #     if argc == 1:
        #         return await message.channel.send(usage)
        #     # Get option
        #     match argv[1]:
        #         case "delete":
        #             # Delete existing command
        #             await command.delete_cmd(self, message, db, argv, argc)
        #         case "edit":
        #             # Edit existing
        #             await command.edit_cmd(self, message, db, argv, argc)
        #         case _:
        #             # Create new command
        #             await command.register_cmd(self, message, db, argv, argc)
        
        # else:
        #     # Parse args
        #     argv = message.content.split()
        #     argc = len(argv)

        #     await command.call_cmd(self, message, db, argv, argc)

intents = discord.Intents.default()
intents.members = True
bot_client = MyBot(intents=intents)
bot_client.run(TOKEN)