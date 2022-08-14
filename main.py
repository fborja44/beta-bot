import discord
import logging
import command
import favorite
import os
from pprint import pprint
from pymongo import MongoClient
from dotenv import load_dotenv

# main.py
# beta-bot program

load_dotenv()

TOKEN = os.getenv('TOKEN')
MONGO_ADDR = os.getenv('MONGO')

print("Starting beta-bot...")
print("========================================")

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
    print('Connected to MongoDB database at {0}'.format(MONGO_ADDR))

class MyBot(discord.Client):
    def __init__(self, *args, **kwargs):
        self.cmd_prefix="$" # unsued
        super().__init__(*args, **kwargs)

    async def on_ready(self): # Event called when bot is ready
        print('{0.user} is now ready.'.format(bot_client))

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent): # use raw to include older messages
        # Update favorites
        if payload.emoji.name == '⭐':
            await favorite.update_favorite(self, payload, db)
    
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent): # use raw to include older messages
        # Update favorites
        if payload.emoji.name == '⭐':
            await favorite.update_favorite(self, payload, db)

    async def on_message(self, message): # Event went the bot receives a message
        if message.author == bot_client.user: # Checks if message is from self
            return

        # Send bot help message
        elif message.content.startswith('$info'):
            # TODO
            return

        # Register new command
        elif message.content.startswith('$cmd'): 
            await command.register_cmd(self, message, db)
            message.reactions 
        # Delete registered command
        elif message.content.startswith('$delcmd'):
            await command.delete_cmd(self, message, db)

        # Edit registered command
        elif message.content.startswith('$editcmd'):
            await command.edit_cmd(self, message, db)

        # Custom command call
        else:
            await command.call_cmd(self, message, db)

bot_client = MyBot()
bot_client.run(TOKEN)