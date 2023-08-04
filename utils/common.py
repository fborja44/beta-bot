from discord import PartialMessageable, app_commands, Interaction

# common.py


def is_thread(channel: PartialMessageable) -> bool:
    """Returns True if the channel provided is a thread, False otherwise.

    Args:
        channel (PartialMessageable): The channel to check.

    Returns:
        bool: True if the channel is a thread. Returns False if the channel is not a thread.
    """
    return "thread" in str(channel.type)


def full_command(command: app_commands.Command) -> str:
    """Returns the full string representation of a command, including parent commands.

    Args:
        command (app_commands.Command): The discord app command.

    Returns:
        str: The string representation of the command.
    """
    if command.parent:
        return f"/{command.parent.name} {command.name}"
    else:
        return f"/{command.name}"


async def valid_bot_permissions(interaction: Interaction, respond: bool = True) -> bool:
    """Checks if the bot user has the proper permissions to use all features of the bot.
    If respond is True, the bot will respond with a message which lists all missing permissions.

    Args:
        interaction (Interaction): The discord command interaction.
        respond (bool, optional): A flag to determine if the bot should send a response. Defaults to True.

    Returns:
        bool: True if bot has all valid permissions. False otherwise.
    """
    bot_user = interaction.guild.get_member(interaction.client.user.id)
    bot_permissions = interaction.channel.permissions_for(bot_user)
    missing_permissions = ""
    if not bot_permissions.send_messages:
        missing_permissions += "- send_messages\n"
    if not bot_permissions.manage_channels:
        missing_permissions += "- manage_channels\n"
    if not bot_permissions.read_messages:
        missing_permissions += "- read_messages`\n"
    if not bot_permissions.read_message_history:
        missing_permissions += "- read_message_history`\n"
    if not bot_permissions.manage_threads:
        missing_permissions += "- manage_threads\n"
    if (
        not bot_permissions.create_private_threads
        or not bot_permissions.create_public_threads
    ):
        missing_permissions += "- create_private_threads\n"
    if not bot_permissions.create_public_threads:
        missing_permissions += "- create_public_threads`\n"
    if not bot_permissions.send_messages_in_threads:
        missing_permissions += "- send_messages_in_threads`\n"
    if not bot_permissions.view_channel:
        missing_permissions += "- view_channel`\n"
    if len(missing_permissions) > 0:
        if respond:
            await interaction.followup.send(
                f"The bot is missing the following required permissions:\n```{missing_permissions}```"
            )
        return False
    return True
