import re
from pprint import pprint

import challonge
from discord import (
    Client,
    Embed,
    ForumChannel,
    Guild,
    Interaction,
    Member,
    Message,
    TextChannel,
    Thread,
)

from guilds import guild as _guild
from modules import match as _match
from modules import tournament as _tournament
from utils.log import printlog

# participant.py
# Tournament participant functions

user_match = re.compile(r"^<@[0-9]+>$")


def find_participant(db_tournament: dict, participant_id: int):
    """Returns an participant in a tournament by id.

    Args:
        db_tournament (dict): The tournament database document.
        participant_id (int): The target participant id.

    Returns:
        The participant document if found. Otherwise, None.
    """
    result = [
        participant
        for participant in db_tournament["participants"]
        if participant["id"] == participant_id
    ]
    if result:
        return result[0]
    return None


def find_participant_by_challonge_id(db_tournament: dict, challonge_id):
    result = [
        participant
        for participant in db_tournament["participants"]
        if participant["challonge_id"] == challonge_id
    ]
    if result:
        return result[0]
    return None


async def join_tournament(interaction: Interaction) -> bool:
    """Allows a user to join a tournament through a command instead of a button.

    Args:
        interaction (Interaction): The Discord command interaction.

    Returns:
        bool: True if successful. Otherwise, False.
    """
    guild: Guild = interaction.guild
    db_guild = await _guild.find_add_guild(guild)
    # Fetch tournament
    db_tournament, _, tournament_thread = await _tournament.find_valid_tournament(
        interaction, db_guild
    )
    if not db_tournament or not tournament_thread:
        return False

    # Check if in valid thread
    if not await _tournament.valid_tournament_thread(db_tournament, interaction):
        return False
    return await add_participant(interaction, db_tournament, tournament_thread)


async def leave_tournament(interaction: Interaction) -> bool:
    """Leave a tournament through command instead of button.

    Args:
        interaction (Interaction): The Discord command interaction.

    Returns:
        bool: True if successful. Otherwise, False.
    """
    guild: Guild = interaction.guild
    db_guild = await _guild.find_add_guild(guild)

    # Fetch tournament
    db_tournament, _, tournament_thread = await _tournament.find_valid_tournament(
        interaction, db_guild
    )
    if not db_tournament or not tournament_thread:
        return False

    # Check if in valid thread
    if not await _tournament.valid_tournament_thread(db_tournament, interaction):
        return False
    return await remove_participant(interaction, db_tournament, tournament_thread)


async def add_participant(
    interaction: Interaction,
    db_tournament: dict = None,
    tournament_thread: Thread = None,
    member: Member = None,
    respond: bool = True,
) -> bool:
    """Adds an participant to a tournament.

    Args:
        interaction (Interaction): The Discord command interaction.
        db_tournament (dict, optional): The tournament database document. Defaults to None.
        tournament_thread (Thread, optional): The tournament Discord thread. Defaults to None.
        member (Member, optional): The Discord member for the participant. Defaults to None.
        respond (bool, optional): Flag to determine whether to respond with a Discord message. Defaults to True.

    Returns:
        bool: True if successful. Otherwise, False.
    """
    guild: Guild = interaction.guild
    message: Message = interaction.message
    user: Member = member or interaction.user
    db_guild = await _guild.find_add_guild(guild)

    # Fetch tournament
    if not db_tournament:
        db_tournament = _tournament.find_tournament_by_id(db_guild, message.id)
    if (
        not db_tournament
        or not db_tournament["open"]
        or db_tournament["in_progress"]
        or db_tournament["completed"]
    ):
        if respond:
            await interaction.followup.send(
                f"This tournament is not open for registration.", ephemeral=True
            )
        return False

    # Fetch tournament channel
    tournament_channel = await _tournament.valid_tournament_channel(
        db_tournament, interaction, respond
    )
    if not tournament_channel:
        return False

    # Fetch tournament thread
    if not tournament_thread:
        tournament_thread = guild.get_thread(db_tournament["id"])
    if not tournament_thread:
        if respond:
            await interaction.followup.send(
                f"Failed to find tournament thread.", ephemeral=True
            )
        return False
    tournament_title = db_tournament["title"]
    participant_ids = []  # list of participant names
    for participant in db_tournament["participants"]:
        participant_ids.append(participant["id"])
    challonge_id = db_tournament["challonge"]["id"]

    # Check if already in participants list
    if user.id in participant_ids:
        if respond:
            await interaction.followup.send(
                f"You have already joined '***{tournament_title}***'.", ephemeral=True
            )
        return False

    # Check if tournament is at capacity
    if db_tournament["max_participants"] and db_tournament["max_participants"] == len(
        db_tournament["participants"]
    ):
        if respond:
            await interaction.followup.send(
                f"Unable to join '***{tournament_title}***'. Tournament has reached maximum participants."
            )
        return False

    # Add user to challonge tournament
    try:
        response = challonge.participants.create(
            challonge_id, f"{user.name}#{user.discriminator}"
        )
    except Exception as e:
        printlog(
            f"Failed to add user ['name'='{user.name}#{user.discriminator}'] to challonge tournament. User may already exist.",
            e,
        )
        if respond:
            await interaction.followup.send(
                f"Something went wrong when trying to join '***{tournament_title}***'.",
                ephemeral=True,
            )
        return False

    # Add user to participants list in database
    new_participant = {
        "id": user.id,
        "challonge_id": response["id"],
        "name": f"{user.name}#{user.discriminator}",
        "seed": response["seed"],
        "placement": None,
        "active": True,
    }
    try:
        db_guild, db_tournament = await _tournament.add_to_tournament(
            guild.id, tournament_title, "participants", new_participant
        )
    except:
        print(
            f"Failed to add user '{new_participant['name']}' to tournament ['title'='{tournament_title}'] participants."
        )
        if respond:
            await interaction.followup.send(
                f"Something went wrong when trying to join '***{tournament_title}***'.",
                ephemeral=True,
            )
        return False
    if db_guild:
        print(
            f"Added participant '{new_participant['name']}' ['id'='{user.id}'] to tournament ['title'='{tournament_title}']."
        )
        # Update message
        await _tournament.edit_tournament_message(
            db_tournament, tournament_channel, tournament_thread
        )
    else:
        print(
            f"Failed to add participant '{new_participant['name']}' ['id'='{user.id}'] to tournament ['title'='{tournament_title}']."
        )
        if respond:
            await interaction.followup.send(
                f"Something went wrong when trying to join '***{tournament_title}***'.",
                ephemeral=True,
            )
        return False
    await sync_seeding(db_guild, db_tournament)
    if respond:
        await interaction.followup.send(
            f"Successfully joined '***{tournament_title}***'.", ephemeral=True
        )
    return True


async def remove_participant(
    interaction: Interaction,
    db_tournament: dict = None,
    tournament_thread: Thread = None,
    member: Member = None,
    respond: bool = True,
) -> bool:
    """Destroys an participant from a tournament.

    Args:
        interaction (Interaction): The Discord command interaction.
        db_tournament (dict, optional): The tournament database document. Defaults to None.
        tournament_thread (Thread, optional): The tournament Discord thread. Defaults to None.
        member (Member, optional): The Discord member for the participant. Defaults to None.
        respond (bool, optional): Flag to determine whether to respond with a Discord message. Defaults to True.

    Returns:
        bool: True if successful. Otherwise, False.
    """
    guild: Guild = interaction.guild
    message: Message = interaction.message
    user: Member = member or interaction.user
    db_guild = await _guild.find_add_guild(guild)

    # Fetch tournament
    if not db_tournament:
        db_tournament = _tournament.find_tournament_by_id(db_guild, message.id)
    if (
        not db_tournament
        or not db_tournament["open"]
        or db_tournament["in_progress"]
        or db_tournament["completed"]
    ):
        if respond:
            await interaction.followup.send(
                f"This tournament is past its registration phase.", ephemeral=True
            )
        return False

    # Fetch tournament channel
    tournament_channel = await _tournament.valid_tournament_channel(
        db_tournament, interaction, respond
    )
    if not tournament_channel:
        return False

    # Fetch tournament thread
    if not tournament_thread:
        tournament_thread = guild.get_thread(db_tournament["id"])
    if not tournament_thread:
        if respond:
            await interaction.followup.send(
                f"Failed to find tournament thread.", ephemeral=True
            )
        return False

    # Remove user from challonge tournament
    tournament_title = db_tournament["title"]
    participant_names = []  # list of participant names
    for participant in db_tournament["participants"]:
        participant_names.append(participant["id"])
    challonge_id = db_tournament["challonge"]["id"]
    tournament_id = db_tournament["id"]

    # Check if already in participants list
    if user.id not in participant_names:
        printlog(
            f"User ['id'='{user.id}']' is not registered as an participant in tournament ['title'='{tournament_title}']."
        )
        if respond:
            await interaction.followup.send(
                f"You are not registered for '***{tournament_title}***'.",
                ephemeral=True,
            )
        return False
    db_participant = list(
        filter(
            lambda participant: participant["id"] == user.id,
            db_tournament["participants"],
        )
    )[0]
    try:
        challonge.participants.destroy(challonge_id, db_participant["challonge_id"])
    except Exception as e:
        printlog(
            f"Failed to remove user ['name'='{db_participant['name']}'] from challonge tournament. User may not exist.",
            e,
        )
        if respond:
            await interaction.followup.send(
                f"Something went wrong when trying to leave '***{tournament_title}***'.",
                ephemeral=True,
            )
        return False

    # Remove user from participants list
    try:
        db_guild, db_tournament = await _tournament.remove_from_tournament(
            guild.id, tournament_title, "participants", db_participant["id"]
        )
    except:
        print(
            f"Failed to remove user '{db_participant['name']}' from tournament ['title'='{tournament_title}'] participants."
        )
        if respond:
            await interaction.followup.send(
                f"Something went wrong when trying to leave '***{tournament_title}***'.",
                ephemeral=True,
            )
        return False
    if db_guild:
        print(
            f"Removed participant ['name'='{db_participant['name']}']from tournament [id='{tournament_id}']."
        )
        # Update message
        await _tournament.edit_tournament_message(
            db_tournament, tournament_channel, tournament_thread
        )  # breaks in forum channel
    else:
        print(
            f"Failed to remove participant ['name'='{db_participant['name']}']from tournament [id='{tournament_id}']."
        )
        if respond:
            await interaction.followup.send(
                f"Something went wrong when trying to leave '***{tournament_title}***'.",
                ephemeral=True,
            )
        return False
    await sync_seeding(db_guild, db_tournament)
    if respond:
        await interaction.followup.send(
            f"Successfully removed from '***{tournament_title}***'.", ephemeral=True
        )
    return True


async def randomize_seeding(
    interaction: Interaction, tournament_title: str = ""
) -> bool:
    """Randomizes the seeding for a tournament bracket.

    If the tournament title is not provided, defaults to the guild's current active tournament,
    or the most recently created tournament.

    Args:
        interaction (Interaction): The Discord command interaction.
        tournament_title (str, optional): The title of the target tournament. Defaults to "".

    Returns:
        bool: True if successful. Otherwise, False.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    try:
        db_tournament, tournament_title, _, _ = await validate_arguments_seeding(
            interaction, db_guild, tournament_title
        )
    except ValueError:
        return False
    tournament_challonge_id = db_tournament["challonge"]["id"]

    # Randomize seeding on challonge
    try:
        challonge.participants.randomize(tournament_challonge_id)
    except:
        printlog(
            f"Failed to randomize seeding for tournament ['title'='{tournament_title}'] on challonge."
        )
        return False

    # Update seeding in db
    await sync_seeding(db_guild, db_tournament)
    print(
        f"User ['name'='{user.name}'] randomized seeding in tournament ['title'='{tournament_title}']."
    )
    await interaction.followup.send(
        f"Succesfully randomized seeding for '***{tournament_title}***'.",
        ephemeral=True,
    )
    # await tournament_thread.send(f"Seeding has been randomized by <@{user.id}>.")
    return True


async def set_seed(
    interaction: Interaction, user_mention: str, seed: int, tournament_title: str = ""
) -> bool:
    """Sets the seed for a participant.

    If the tournament title is not provided, defaults to the guild's current active tournament,
    or the most recently created tournament.

    Args:
        interaction (Interaction): The Discord command interaction.
        user_mention (str): A Discord user mention. [<@user_id>]
        seed (int): The new seed for the participant.
        tournament_title (str, optional): The title of the target tournament. Defaults to "".

    Returns:
        bool: True if successful. Otherwise, False.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)

    # Validate arguments
    try:
        db_tournament, tournament_title, _, _ = await validate_arguments_seeding(
            interaction, db_guild, tournament_title
        )
    except ValueError:
        return False
    tournament_challonge_id = db_tournament["challonge"]["id"]

    # Check if valid participant mention
    participant: Member = parse_user_mention(interaction, user_mention)
    if not participant:
        await interaction.followup.send(
            f"Invalid user mention for `user_mention`. ex. <@{interaction.client.user.id}>",
            ephemeral=True,
        )
        return False

    # Check if participant exists
    participant_name = participant.name
    db_participant = await validate_participant(interaction, db_tournament, participant)
    if not db_participant:
        return False

    # Check if valid seed
    num_entrants = len(db_tournament["participants"])
    if seed <= 0 or seed > num_entrants:
        await interaction.followup.send(
            f"Invalid seed. Must be greater than 0 and less than or equal to the number of participants'."
        )
        return False

    # Update seed on challonge
    try:
        challonge.participants.update(
            tournament_challonge_id, db_participant["challonge_id"], seed=seed
        )
    except:
        printlog(
            f"Failed to update seed for user ['name'='{participant_name}'] in  tournament ['title'='{tournament_title}'] on challonge."
        )
        return False

    # Update seed in db
    p_index = _tournament.find_index_in_tournament(
        db_tournament, "participants", "challonge_id", db_participant["challonge_id"]
    )
    db_tournament["participants"][p_index].update({"seed": seed})
    await _tournament.set_tournament(guild.id, tournament_title, db_tournament)
    await interaction.followup.send(
        f"Succesfully updated seed for <@{participant.id}> to **{seed}**.",
        ephemeral=True,
    )
    print(
        f"User ['name'='{user.name}'] updated seed for participant ['name'='{participant_name}'] in tournament ['title'='{tournament_title}']."
    )
    return True


async def disqualify_participant_main(
    interaction: Interaction, user_mention: str, tournament_title: str = ""
):
    """Destroys an participant from a tournament or DQs them if the tournament has already started from a command.
    Main function.

    If the tournament title is not provided, defaults to the guild's current active tournament,
    or the most recently created tournament.

    Args:
        interaction (Interaction): The Discord command interaction.
        user_mention (str): A Discord user mention. [<@user_id>]
        tournament_title (str, optional): The title of the target tournament. Defaults to "".

    Returns:
        bool: True if successful. Otherwise, False.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)

    # Validate arguments
    try:
        (
            db_tournament,
            tournament_title,
            tournament_thread,
            tournament_channel,
        ) = await _tournament.validate_arguments_tournament(
            interaction, db_guild, tournament_title
        )
    except ValueError:
        return False

    # Check if valid participant mention
    participant: Member = parse_user_mention(interaction, user_mention)
    if not participant:
        await interaction.followup.send(
            f"Invalid user mention for `user_mention`. ex. <@{interaction.client.user.id}>",
            ephemeral=True,
        )
        return False
    tournament_title = db_tournament["title"]

    # Check if participant exists
    db_participant = await validate_participant(interaction, db_tournament, participant)
    if not db_participant:
        return False

    # If tournament still has not started, just remove from tournament
    if not db_tournament["in_progress"]:
        participant: Member = await interaction.guild.fetch_member(db_participant["id"])
        await remove_participant(interaction, db_tournament, participant, respond=False)
        await interaction.followup.send(
            f"Successfully removed participant from '***{tournament_title}***'.",
            ephemeral=True,
        )
        print(f"User ['name'='{user.name}'] manually removed participant.")
        return True

    # Call dq helper function
    await disqualify_participant(
        interaction.client, tournament_thread, db_guild, db_tournament, db_participant
    )
    await interaction.followup.send(
        f"'{db_participant['name']}' was disqualified from '***{tournament_title}***'."
    )
    print(f"User ['name'='{user.name}'] manually disqualified participant.")
    return True


async def disqualify_participant(
    client: Client,
    tournament_thread: Thread,
    db_guild: dict,
    db_tournament: dict,
    db_participant: dict,
) -> bool:
    """Function to dq an participant in the database and challonge. Updates messages.

    Args:
        tournament_thread (Thread): The tournament Discord thread.
        db_guild (dict): The guild database document.
        db_tournament (dict): The tournament databse document.
        db_participant (dict): The target participant document.

    Returns:
        bool: True if successfully disqualified. Otherwise, False.
    """
    tournament_title = db_tournament["title"]
    challonge_id = db_tournament["challonge"]["id"]
    participant_name = db_participant["name"]
    db_participant["active"] = False
    participant_index = _tournament.find_index_in_tournament(
        db_tournament, "participants", "id", db_participant["id"]
    )
    db_tournament["participants"][participant_index] = db_participant
    # Update participant in database
    try:
        await _tournament.set_tournament(
            db_guild["guild_id"], tournament_title, db_tournament
        )
    except:
        print("Failed to DQ participant in database.")
        return False
    # Disqualify participant on challonge
    try:
        challonge.participants.destroy(challonge_id, db_participant["challonge_id"])
    except Exception as e:
        printlog(
            f"Failed to DQ participant ['name'='{participant_name}'] from tournament ['title'='{tournament_title}']",
            e,
        )
        return False
    # Update all open matches
    winner_emote = None
    for tournament_match in db_tournament["matches"]:
        # Get match document
        db_match = _match.find_match(db_tournament, tournament_match["id"])
        # Check if match is open
        if db_match["completed"]:
            continue
        # Check the players; Other player wins
        if db_match["player1"]["id"] == db_participant["id"]:
            winner_emote = "2️⃣"
            break
        elif db_match["player2"]["id"] == db_participant["id"]:
            winner_emote = "1️⃣"
            break
    if winner_emote:
        # Report match
        match_message = await tournament_thread.fetch_message(db_match["id"])
        await _match.report_match(
            client, match_message, db_guild, db_tournament, db_match, winner_emote, is_dq=True
        )
    return True


######################
## HELPER FUNCTIONS ##
######################


def parse_user_mention(interaction: Interaction, user_mention: str):
    """Parses a channel mention argument.

    Args:
        interaction (Interaction): The Discord command interaction.
        user_mention (str): A Discord user mention. [<@user_id>]

    Returns:
        The Discord user instance if successful. Otherwise, None.
    """
    if user_mention is not None and len(user_mention.strip()) > 0:
        matched_user_id = user_match.search(user_mention)
        if matched_user_id:
            return interaction.guild.get_member(int(user_mention[2:-1])) or None
        else:
            return None
    else:
        return interaction.user


async def sync_seeding(db_guild: dict, db_tournament: dict):
    """Updates tournament participants in database to have the same seeding as listed on challonge.

    Args:
        db_guild (dict): The guild database document.
        db_tournament (dict): The tournament databse document.

    Returns:
        True if successful. Otherwise, False.
    """
    tournament_challonge_id = db_tournament["challonge"]["id"]
    try:
        # Update seeding in db
        result = challonge.participants.index(tournament_challonge_id)
        for ch_participant in result:
            p_index = _tournament.find_index_in_tournament(
                db_tournament, "participants", "challonge_id", ch_participant["id"]
            )
            if p_index >= 0:
                db_tournament["participants"][p_index].update(
                    {"seed": ch_participant["seed"]}
                )
        await _tournament.set_tournament(
            db_guild["guild_id"], db_tournament["title"], db_tournament
        )
        print(
            f"Synchronized seeding of tournament ['title'='{db_tournament['title']}']."
        )
        return True
    except Exception:
        print(
            f"Failed to synchronize seeding of tournament ['title'='{db_tournament['title']}']."
        )
        return False


async def validate_participant(
    interaction: Interaction, db_tournament: dict, member: Member
):
    """Checks whether a user is a participant in a tournament.

    Args:
        interaction (Interaction): The Discord command interaction.
        db_tournament (dict): The target tournament database document.
        member (Member): The Discord member to validate.

    Returns:
        The participant database document if successful. Otherwise, false.
    """
    db_participant = None
    for elem in db_tournament["participants"]:
        if elem["id"] == member.id:
            db_participant = elem
            break
    if not db_participant:
        await interaction.followup.send(
            f"<@{member.id}> is not a participant in '***{db_tournament['title']}***'."
        )
        return None
    elif not db_participant["active"]:
        await interaction.followup.send(
            f"<@{member.id}> was previously disqualified from '***{db_tournament['title']}***'.",
            ephemeral=True,
        )
        return None
    return db_participant


async def validate_arguments_seeding(
    interaction: Interaction, db_guild: dict, tournament_title: str = ""
):
    """Validate general arguments passed for seeding commands.

    Args:
        interaction (Interaction): The Discord command interaction.
        db_guild (dict): The guild database document.
        tournament_title (str, optional): The title of the target tournament. Defaults to "".

    Raises:
        ValueError: The tournament has already been started.
        ValueError: The tournament has already been completed.

    Returns:
        A tuple of the database tournament document, the tournament title, the tournament thread, and the tournament channel.
    """
    # Validate arguments
    (
        db_tournament,
        tournament_title,
        tournament_thread,
        tournament_channel,
    ) = await _tournament.validate_arguments_tournament(
        interaction, db_guild, tournament_title
    )
    # Check if tournament has already been started.
    # Only allow updating if the tournament has not been started or completed
    if db_tournament["in_progress"]:
        await interaction.followup.send(
            f"This tournament has been started; Unable to update seeding.",
            ephemeral=True,
        )
        raise ValueError("Tournament has already been started.")
    if db_tournament["completed"]:
        await interaction.followup.send(
            f"This tournament has been completed; Unable to update seeding.",
            ephemeral=True,
        )
        raise ValueError("Tournament has already been completed.")
    return db_tournament, tournament_title, tournament_thread, tournament_channel
