from dotenv import load_dotenv
from discord import PartialMessageable, app_commands, Interaction
import os

# common.py

load_dotenv()

CHALLONGE_USER = os.getenv('CHALLONGE_USER')
CHALLONGE_KEY = os.getenv('CHALLONGE_KEY')
MONGO_ADDR = os.getenv('MONGO')
TOKEN = os.getenv('TOKEN')

TOURNAMENTS = 'tournaments'
CHALLENGES = 'challenges'
GUILDS = 'guilds'
MATCHES = 'matches'

ICON = 'https://static-cdn.jtvnw.net/jtv_user_pictures/638055be-8ceb-413e-8972-bd10359b8556-profile_image-70x70.png'
IMGUR_CLIENT_ID = os.getenv('IMGUR_ID')
IMGUR_URL = 'https://api.imgur.com/3'

MAX_ENTRANTS = 24

def is_thread(channel: PartialMessageable):
    """
    Returns True if the channel provided is a thread, False otherwise.
    """
    return 'thread' in str(channel.type)

def full_command(command: app_commands.Command):
    """
    Returns the full string representation of a command, including parent commands.
    """
    if command.parent:
        return f"/{command.parent.name} {command.name}"
    else:
        return f"/{command.name}"

async def valid_bot_permissions(interaction: Interaction, respond: bool=True):
    """
    Checks if the bot user has the proper permissions to use all features of the bot.
    """
    bot_user = interaction.guild.get_member(interaction.client.user.id)
    bot_permissions = interaction.channel.permissions_for(bot_user)
    missing_permissions = ''
    if not bot_permissions.send_messages:
        missing_permissions += '- send_messages\n'
    if not bot_permissions.manage_channels:
        missing_permissions += '- manage_channels\n'
    if not bot_permissions.read_messages:
        missing_permissions += '- read_messages`\n'
    if not bot_permissions.read_message_history:
        missing_permissions += '- read_message_history`\n'
    if not bot_permissions.manage_threads:
        missing_permissions += '- manage_threads\n'
    if not bot_permissions.create_private_threads or not bot_permissions.create_public_threads:
        missing_permissions += '- create_private_threads\n'
    if not bot_permissions.create_public_threads:
        missing_permissions += '- create_public_threads`\n'
    if not bot_permissions.send_messages_in_threads:
        missing_permissions += '- send_messages_in_threads`\n'
    if not bot_permissions.view_channel:
        missing_permissions += '- view_channel`\n'
    if len(missing_permissions) > 0:
        if respond: await interaction.followup.send(f"The bot is missing the following required permissions:\n```{missing_permissions}```")
        return False
    return True