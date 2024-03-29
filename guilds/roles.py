from pprint import pprint

from discord import (Embed, Guild, Interaction, Member, Message, Role,
                     TextChannel)

from utils.log import printlog, printlog_msg

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
