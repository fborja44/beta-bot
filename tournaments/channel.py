from utils.common import BRACKETS, GUILDS, ICON, IMGUR_CLIENT_ID, IMGUR_URL, MAX_ENTRANTS
from discord import Embed, Guild, Interaction, Message, Member, TextChannel
from utils.logger import printlog, printlog_msg
from pprint import pprint
import discord
import guilds.guild as _guild
import tournaments.match as _match

# channel.py
# Tournament discord channel

def create_tournament_channel(interaction: Interaction, channel_name: str, category_name: str, is_forum: bool, allow_messages: bool):
    """
    TODO
    Creates a tournament channel.
    """

def create_tournament_forum(interaction: Interaction, channel_name: str, allow_messages: bool):
    """
    TODO
    Creates a tournament channel as a forum channel.
    """

def create_tournament_text(interaction: Interaction, channel_name: str, allow_messages: bool):
    """
    TODO
    Creates a tournament channel as a text channel.
    """

def delete_tournament_channel(interaction: Interaction, channel_name: str, channel_id: int):
    """
    TODO
    Deletes a tournament channel.
    """

def configure_tournament_channel(interaction: Interaction):
    """
    TODO
    Configures a tournament channel
    """