import bracket
import command
import challonge
import discord
import favorite
import logging
import os
from colorama import Fore, Back, Style
from dotenv import load_dotenv
from pprint import pprint
from pydoc import describe
from pymongo import MongoClient

# main.py
# beta-bot program

load_dotenv()

TOKEN = os.getenv('TOKEN')
MONGO_ADDR = os.getenv('MONGO')
CHALLONGE_USER = os.getenv('CHALLONGE_USER')
CHALLONGE_KEY = os.getenv('CHALLONGE_KEY')

challonge.set_credentials(CHALLONGE_USER, CHALLONGE_KEY)

print(Fore.CYAN + "Starting beta-bot..." + Style.RESET_ALL)
print(Fore.MAGENTA + "============================================" + Style.RESET_ALL)

# Add logs to discord.log
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# Connect to MongoDB
db_client = MongoClient(MONGO_ADDR)
db = db_client['beta-bot']
# Debugging: serverStatus
serverStatusResult = db.command("serverStatus")
if serverStatusResult:
    print('Connected to MongoDB database at ' + Fore.YELLOW + f'{MONGO_ADDR}' + Style.RESET_ALL)

class MyBot(discord.Client):
    def __init__(self, *args, **kwargs):
        self.cmd_prefix="$" # unsued
        super().__init__(*args, **kwargs)

    async def on_ready(self): # Event called when bot is ready
        print(Fore.YELLOW + f'{bot_client.user} is now ready.' + Style.RESET_ALL)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent): # use raw to include older messages
        # Check if reacting to self 
        if payload.user_id == self.user.id:
            return
        if payload.emoji.name == '⭐':
            # Update favorites
            await favorite.update_favorite(self, payload, db)
        elif payload.emoji.name =='✅':
            # Update bracket entrants
            await bracket.update_bracket_entrants(self, payload, db)
    
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent): # use raw to include older messages
        # Check if reacting to self 
        if payload.user_id == self.user.id:
            return
        if payload.emoji.name == '⭐':
            # Update favorites
            await favorite.update_favorite(self, payload, db)
        elif payload.emoji.name =='✅':
            # Update bracket entrants
            await bracket.update_bracket_entrants(self, payload, db)

    async def on_message(self, message): # Event went the bot receives a message
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
            match argv[1]:
                case "create":
                    await bracket.add_bracket(self, message, db, argv, argc)
                case "edit":
                    await bracket.update_bracket(self, message, db, argv, argc)
                case "delete":
                    await bracket.delete_bracket(self, message, db, argv, argc)
                case "start":
                    await bracket.start_bracket(self, message, db, argv, argc)
                case "finalize":
                    await bracket.finalize_bracket(self, message, db, argv, argc)
                case _:
                    # TODO: List options
                    pass

        # Commands
        elif message.content.startswith('$cmd'): 
            usage = 'Usage: `$cmd <option>`'
            # Parse args
            argv = message.content.split()
            argc = len(argv)
            if argc == 1:
                return await message.channel.send(usage)
            # Get option
            match argv[1]:
                case "delete":
                    # Delete existing command
                    await command.delete_cmd(self, message, db, argv, argc)
                case "edit":
                    # Edit existing
                    await command.edit_cmd(self, message, db, argv, argc)
                case _:
                    # Create new command
                    await command.register_cmd(self, message, db, argv, argc)
        
        else:
            # Parse args
            argv = message.content.split()
            argc = len(argv)

            await command.call_cmd(self, message, db, argv, argc)

bot_client = MyBot()
bot_client.run(TOKEN)