from utils.common import BRACKETS, GUILDS, ICON, IMGUR_CLIENT_ID, IMGUR_URL, MAX_ENTRANTS
from discord import Embed, Guild, Interaction, Message, Member, Role, TextChannel
from utils.logger import printlog, printlog_msg
from pprint import pprint
import discord
import guilds.guild as _guild
import tournaments.match as _match

# roles.py
# Tournament organizer/manager roles and others

def create_privileged_role(interaction: Interaction, role_name: str):
    """
    TODO
    Creates a role and adds it to tournament-privileged roles in a guild.
    """

def add_role_to_privileged(interaction: Interaction, role: Role):
    """
    TODO
    Adds a role to tournament-privileged roles in a guild.
    """

def remove_role_from_privileged(interaction: Interaction, role: Role):
    """
    TODO
    Removes a role from tournament-privileged roles in a guild.
    """

def update_role_in_privileged(interaction: Interaction, role: Role, new_role_name: str):
    """
    TODO
    Adds a role to tournament-privileged roles in a guild.
    """
