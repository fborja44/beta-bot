import os
import re
from cgi import print_exception
from datetime import date, datetime, timedelta, timezone
from pprint import pprint
from traceback import print_exception

import challonge
import discord
import pytz
import requests
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

# from discord.ext import tasks
from dotenv import load_dotenv

from guilds import channel as _channel
from guilds import guild as _guild
from modules import match as _match
from modules import participant as _participant
from db import mdb
from utils.color import GOLD, WOOP_PURPLE
from utils.common import full_command
from utils.constants import (
    GUILDS,
    ICON,
    IMGUR_CLIENT_ID,
    IMGUR_URL,
    MAX_ENTRANTS,
    TOURNAMENTS,
)
from utils.log import printlog

from cairosvg import svg2png

from views.registration_view import RegistrationView  # SVG to PNG

# tournament.py
# User created tournaments

load_dotenv()

MIN_ENTRANTS = 2
EASTERN_ZONE = pytz.timezone("US/Eastern")

time_re_long = re.compile(
    r"([1-9]|0[1-9]|1[0-2]):[0-5][0-9]\s*([AaPp][Mm])$"
)  # ex. 10:00 AM
time_re_short = re.compile(r"([1-9]|0[1-9]|1[0-2])\s*([AaPp][Mm])$")  # ex. 10 PM


def find_tournament(db_guild: dict, tournament_title: str):
    """Retrieves and returns a tournament document from the database (if it exists).

    Args:
        db_guild (dict): The guild database document.
        tournament_title (str): The title of the target tournament.

    Returns:
        The tournament database document if found. Otherwise, None.
    """
    guild_tournaments = db_guild["tournaments"]
    result = [
        tournament
        for tournament in guild_tournaments
        if tournament["title"] == tournament_title
    ]
    if result:
        return result[0]
    return None


def find_tournament_by_id(db_guild: dict, tournament_id: int):
    """Retrieves and returns a tournament document from the database (if it exists).

    Args:
        db_guild (dict): The guild database document.
        tournament_id (int): The id of the target tournament.

    Returns:
        The tournament database document if found. Otherwise, None.
    """
    result = [
        tournament
        for tournament in db_guild["tournaments"]
        if tournament["id"] == tournament_id
    ]
    if result:
        return result[0]
    return None


def find_active_tournament(db_guild: dict):
    """Returns the current active tournament in a guild.
    Active means the tournament is in progress, but has not been completed.

    Args:
        db_guild (dict): The guild database document.

    Returns:
        The tournament database document of the active tournament if found. Otherwise, None.
    """
    try:
        return list(
            filter(
                lambda tournament: tournament["in_progress"]
                and not tournament["completed"],
                db_guild["tournaments"],
            )
        )[0]
    except:
        return None


def find_most_recent_tournament(db_guild: dict, completed: bool):
    """Returns the most recently created tournament in a guild that has not yet been completed.

    Args:
        db_guild (dict): The guild database document.
        completed (bool): Flag to include completed tournaments.

    Returns:
        The tournament database document of the most recently created tournament if found. Otherwise, None.
    """
    guild_tournaments = db_guild["tournaments"]

    if completed:
        return max(
            (t for t in guild_tournaments if t["completed"]),
            key=lambda t: t["completed"],
            default=None,
        )
    else:
        return max(
            (t for t in guild_tournaments if not t["completed"]),
            key=lambda t: t["created_at"],
            default=None,
        )


def find_incomplete_tournaments(db_guild: dict):
    """Returns all tournaments that have not been completed.

    Args:
        db_guild (dict): The guild database document.

    Returns:
        A list of all incomplete tournament documents if found. Otherwise, None.
    """
    guild_tournaments = db_guild["tournaments"]
    try:
        guild_tournaments = list(
            filter(lambda tournament: not tournament["completed"], guild_tournaments)
        )
        return guild_tournaments
    except Exception as e:
        print(e)
        return None


def find_registration_tournaments(db_guild: dict):
    """Returns all tournaments that are in the registration phase.

    Args:
        db_guild (dict): The guild database document.

    Returns:
        A list of all tournaments in the registration phase if found. Otherwise, None.
    """
    guild_tournaments = db_guild["tournaments"]
    try:
        guild_tournaments = list(
            filter(
                lambda tournament: not tournament["completed"]
                and not tournament["in_progress"],
                guild_tournaments,
            )
        )
        return guild_tournaments
    except Exception as e:
        print(e)
        return None


async def create_tournament(
    interaction: Interaction,
    tournament_title: str,
    time: str = "",
    single_elim: bool = False,
    max_participants: int = 24,
    respond: bool = True,
):
    """Creates a new tournament and adds it to the guild.
    Creates the tournament document, adds it to the databse, and creates a tournament on challonge.

    By default, the time is 1 hour from the time that the command was issued. Must be a valid time string.
    By default, the tournament is double elimination unless the single_elim flag is provided.
    By default, the max participants in a tourney is 24.

    Args:
        interaction (Interaction): The Discord command interaction.
        tournament_title (str): The title of the target tournament.
        time (str, optional): The time of the tournament. Defaults to "".
        single_elim (bool, optional): Flag to determine if the tournament is single elimination. Defaults to False.
        max_participants (int, optional): The number of maximum participants in a tournament. Defaults to 24.
        respond (bool, optional): Flag to determine if a Discord message should be sent in response. Defaults to True.

    Returns:
        A tuple of the new tournament document, the tournament Discord message, and the challonge object if successful.
        Otherwise, a tuple of None, None, None.
    """
    guild: Guild = interaction.guild

    # Check if in invalid channel type or thread
    if "thread" in str(interaction.channel.type):
        await interaction.followup.send(
            "Invalid tournament channel. Cannot create a tournament inside of a thread.",
            ephemeral=True,
        )
        return None, None, None

    channel: ForumChannel | TextChannel = interaction.channel
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)

    # Check if bot has thread permissions
    bot_user = guild.get_member(interaction.client.user.id)
    bot_permissions = channel.permissions_for(bot_user)
    if (
        not bot_permissions.create_private_threads
        or not bot_permissions.create_public_threads
    ):
        if respond:
            await interaction.followup.send(
                "The bot is needs permissions to post private/public threads to create tournaments."
            )
        return None, None, None

    # Parse time; Default is 1 hour from current time
    try:
        parsed_time = parse_time(time)
    except ValueError as e:
        if respond:
            await interaction.followup.send(
                "Invalid input for time. ex. `10am` or `10:30pm`"
            )
        return None, None, None

    # Max character length == 60
    if len(tournament_title.strip()) == 0:
        if respond:
            await interaction.followup.send(f"Tournament title cannot be empty.")
        return None, None, None
    if len(tournament_title.strip()) > 60:
        if respond:
            await interaction.followup.send(
                f"Tournament title can be no longer than 60 characters."
            )
        return None, None, None

    # Max participants limits
    if max_participants is not None and (
        max_participants < 4 or max_participants > MAX_ENTRANTS
    ):
        if respond:
            await interaction.followup.send(
                f"`max_participants` must be between 4 and {MAX_ENTRANTS}."
            )
        return None, None, None

    # Check if tournament already exists
    db_tournament = find_tournament(db_guild, tournament_title)
    if db_tournament:
        if respond:
            await interaction.followup.send(
                f"Tournament with title '{tournament_title}' already exists in this server."
            )
        return None, None, None
    try:
        # Create challonge tournament
        tournament_challonge = challonge.tournaments.create(
            name=tournament_title,
            url=None,
            tournament_type="single elimination"
            if single_elim
            else "double elimination",
            start_at=parsed_time,
            signup_cap=max_participants,
            show_rounds=True,
            private=True,
            quick_advance=True,
            open_signup=False,
        )
        new_tournament = {
            "id": None,  # Message ID and Thread ID; Initialized later
            "channel_id": channel.id,  # TextChannel/Thread that the create command was called in
            "title": tournament_title,
            "tournament_type": tournament_challonge["tournament_type"],
            "jump_url": None,  # Initialized later
            "result_url": None,
            "author": {
                "username": f"{user.name}#{user.discriminator}",
                "id": user.id,
                "avatar_url": user.display_avatar.url,
            },
            "challonge": {
                "id": tournament_challonge["id"],
                "url": tournament_challonge["full_challonge_url"],
            },
            "participants": [],
            "winner": None,
            "max_participants": max_participants,
            "matches": [],
            "created_at": datetime.now(tz=EASTERN_ZONE),
            "start_time": parsed_time,
            "end_time": None,
            "completed": False,
            "open": True,
            "in_progress": False,
            "num_rounds": None,
        }

        embed = create_tournament_embed(new_tournament, interaction.user)

        # Send tournament thread message
        thread_title = (
            f"🥊 {tournament_title} - {tournament_challonge['tournament_type'].title()}"
        )
        thread_content = "Open for Registration 🚨"
        if str(channel.type) == "forum":  # Creating as a forum channel thread
            tournament_thread, tournament_message = await channel.create_thread(
                name=thread_title,
                content=thread_content,
                embed=embed,
                view=RegistrationView(),
            )
        else:  # Creating as a text channel thread
            tournament_message = await channel.send(embed=embed)
            tournament_thread = await channel.create_thread(
                name=thread_title, message=tournament_message
            )
            await tournament_thread.starter_message.edit(view=RegistrationView())

        # Update tournament object
        new_tournament["id"] = tournament_message.id
        new_tournament["jump_url"] = tournament_message.jump_url

        # Add tournament to database
        result = await _guild.push_to_guild(guild, TOURNAMENTS, new_tournament)
        print(
            f"User '{user.name}#{user.discriminator}' [id={user.id}] created new tournament '{tournament_title}'."
        )

        if respond:
            await interaction.followup.send(
                f"Successfully created tournament '***{tournament_title}***'."
            )
        return (new_tournament, tournament_message, tournament_challonge)
    except Exception as e:
        printlog("Something went wrong when creating the tournament.", e)
        if respond:
            await interaction.followup.send(
                f"Something went wrong when creating tournament '***{tournament_title}***'."
            )

        # Delete challonge tournament
        try:
            challonge.tournaments.destroy(tournament_challonge["id"])
        except:
            pass

        # Delete tournament message
        try:
            if tournament_message:
                await tournament_message.delete()
        except:
            pass

        # Delete thread
        try:
            if tournament_thread:
                await tournament_thread.delete()
        except:
            pass

        # Delete tournament document
        try:
            if result:
                await _guild.pull_from_guild(guild, TOURNAMENTS, new_tournament)
        except:
            pass
        return None, None, None


async def send_seeding(interaction: Interaction, tournament_title: str) -> bool:
    """Sends an embed displaying the seeding of a tournament.

    Args:
        interaction (Interaction): The Discord command interaction.
        tournament_title (str): The title of the target tournament.

    Returns:
        bool: True if successful. Otherwise, false.
    """
    guild: Guild = interaction.guild
    db_guild = await _guild.find_guild(guild.id)

    # Fetch tournament
    db_tournament, tournament_title, _ = await find_valid_tournament(
        interaction, db_guild, tournament_title
    )
    if not db_tournament:
        return False

    # Create seeding message
    embed = create_seeding_embed(db_tournament)
    await interaction.followup.send(embed=embed)
    return True


async def delete_tournament(
    interaction: Interaction, tournament_title: str, respond: bool = True
) -> bool:
    """Deletes the specified tournament (if it exists).

    Args:
        interaction (Interaction): The Discord command interaction.
        tournament_title (str): The title of the target tournament.
        respond (bool, optional): Flag to determine if a Discord message should be sent in response. Defaults to True.

    Returns:
        bool: True if successful. Otherwise, False.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    retval = True

    # Validate arguments
    try:
        (
            db_tournament,
            tournament_title,
            tournament_thread,
            tournament_channel,
        ) = await validate_arguments_tournament(
            interaction, db_guild, tournament_title, respond=respond
        )
    except:
        return False

    # Delete tournament document
    try:
        result = await _guild.pull_from_guild(guild, TOURNAMENTS, db_tournament)
    except:
        print(f"Failed to delete tournament ['name'={tournament_title}].")
    if result:
        try:
            challonge.tournaments.destroy(
                db_tournament["challonge"]["id"]
            )  # delete tournament from challonge
        except Exception as e:
            printlog(
                f"Failed to delete tournament [id='{db_tournament['id']}] from challonge [id='{db_tournament['challonge']['id']}].",
                e,
            )
            retval = False
        print(
            f"User '{user.name}#{user.discriminator}' [id={user.id}] deleted tournament '{tournament_title}'."
        )
    else:
        if respond:
            await interaction.followup.send(
                f"Failed to delete tournament '***{tournament_title}***'.",
                ephemeral=True,
            )
        retval = False

    # Delete thread
    try:
        await tournament_thread.delete()
    except:
        print(
            f"Failed to delete thread for tournament '{tournament_title}' ['id'='{db_tournament['id']}']."
        )

    # Delete tournament message if tournament channel is Text Channel
    if str(tournament_channel.type) == "text":
        try:
            tournament_message: Message = await tournament_channel.fetch_message(
                db_tournament["id"]
            )
            await tournament_message.delete()  # delete message from channel
        except discord.NotFound:
            print(
                f"Failed to delete message for tournament '{tournament_title}' ['id'='{db_tournament['id']}']; Not found."
            )
        except discord.Forbidden:
            print(
                f"Failed to delete message for tournament '{tournament_title}' ['id'='{db_tournament['id']}']; Bot does not have proper permissions."
            )
            return False
    if respond and interaction.channel.id != tournament_thread.id:
        await interaction.followup.send(
            f"Successfully deleted tournament '***{tournament_title}***'."
        )
    return retval


async def update_tournament(
    interaction: Interaction,
    tournament_title: str,
    new_tournament_title: str | None = None,
    time: str | None = None,
    single_elim: bool | None = None,
    max_participants: int | None = None,
) -> bool:
    """Updates the specified tournament (if it exists).
    Update parameters are optional.

    Args:
        interaction (Interaction): The Discord command interaction.
        tournament_title (str): The title of the target tournament.
        new_tournament_title (str | None, optional): The new title of the tournament. Defaults to None.
        time (str | None, optional): The new time for the tournament. Defaults to None.
        single_elim (bool | None, optional): Flag to determine whether the tournament should be single elim. Defaults to None.
        max_participants (int | None, optional): The new number of maximum participants. Defaults to None.

    Returns:
       bool: True if successful. Otherwise, False.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)

    # Validate arguments
    try:
        (
            db_tournament,
            tournament_title,
            tournament_thread,
            tournament_channel,
        ) = await validate_arguments_tournament(interaction, db_guild, tournament_title)
    except ValueError:
        return False

    # Only allow updating if the tournament has not been started or completed
    if db_tournament["in_progress"]:
        await interaction.followup.send(
            f"This tournament has been started; Unable to update tournament.",
            ephemeral=True,
        )
        return False
    if db_tournament["completed"]:
        await interaction.followup.send(
            f"This tournament has been completed; Unable to update tournament.",
            ephemeral=True,
        )
        return False

    # Check if updating info
    if not (
        new_tournament_title is not None
        or time is not None
        or single_elim is not None
        or max_participants is not None
    ):
        await interaction.followup.send(
            f"Must include at least one field to update.", ephemeral=True
        )
        return False

    # Updating tournament_title
    if new_tournament_title is not None:
        if len(new_tournament_title.strip()) == 0:
            await interaction.followup.send(f"Tournament title cannot be empty.")
            return False
        if len(new_tournament_title.strip()) > 60:
            await interaction.followup.send(
                f"Tournament title can be no longer than 60 characters."
            )
            return False
        db_tournament["title"] = new_tournament_title.strip()

    # Updating time
    if time is not None:
        db_tournament["start_time"] = parse_time(time.strip())

    # Updating type
    if single_elim is not None:
        db_tournament["tournament_type"] = (
            "single elimination" if single_elim else "double elimination"
        )

    # Updating max_participants
    if max_participants is not None:
        if max_participants < 4 or max_participants > MAX_ENTRANTS:
            await interaction.followup.send(
                f"`max_participants` must be between 4 and {MAX_ENTRANTS}."
            )
            return False
        db_tournament["max_participants"] = max_participants

    # Update the tournament on challonge
    challonge.tournaments.update(
        db_tournament["challonge"]["id"],
        name=db_tournament["title"],
        tournament_type=db_tournament["tournament_type"],
        start_at=db_tournament["start_time"],
        signup_cap=max_participants,
    )

    # Update the tournament in database
    await set_tournament(guild.id, tournament_title, db_tournament)

    # Update tournament embed
    if _channel.in_forum(interaction):
        tournament_message: Message = await tournament_thread.fetch_message(
            db_tournament["id"]
        )
    else:
        tournament_message: Message = await tournament_channel.fetch_message(
            db_tournament["id"]
        )
    author: Member = (
        await guild.fetch_member(db_tournament["author"]["id"]) or interaction.user
    )
    new_tournament_embed = create_tournament_embed(db_tournament, author)
    await tournament_message.edit(embed=new_tournament_embed)
    if interaction.channel.id != tournament_thread.id:
        await tournament_thread.send(
            f"This tournament has been updated by <@{user.id}>."
        )
    await interaction.followup.send(f"Successfully updated tournament.")
    return True


async def start_tournament(interaction: Interaction, tournament_title: str) -> bool:
    """Starts a tournament created by the user.

    Args:
        interaction (Interaction): The Discord command interaction.
        tournament_title (str): The title of the target tournament.

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
        ) = await validate_arguments_tournament(interaction, db_guild, tournament_title)
    except ValueError:
        return False

    # Check if already started
    if db_tournament["in_progress"]:
        await interaction.followup.send(
            f"'***{tournament_title}***' is already in progress.", ephemeral=True
        )
        return False

    # Make sure there are sufficient number of participants
    if len(db_tournament["participants"]) < MIN_ENTRANTS:
        await interaction.followup.send(
            f"Tournament must have at least {MIN_ENTRANTS} participants before starting.",
            ephemeral=True,
        )
        return False

    # Only allow one tournament to be started at a time in a guild
    active_tournament = find_active_tournament(db_guild)
    if active_tournament and active_tournament["id"] != db_tournament["id"]:
        active_tournament_id = (
            active_tournament["channel_id"] or active_tournament["id"]
        )
        await interaction.followup.send(
            f"There may only be one active tournament per server.\nCurrent active tournament in: <#{active_tournament_id}>.",
            ephemeral=True,
        )
        return False

    # Start tournament on challonge
    try:
        challonge.tournaments.start(
            db_tournament["challonge"]["id"], include_participants=1, include_matches=1
        )
    except Exception as e:
        printlog(
            f"Failed to start tournament ['title'='{tournament_title}'] on challonge."
        )
        await interaction.followup.send(
            f"Something went wrong when starting '***{tournament_title}***' on challonge."
        )
        return False
    printlog(
        f"User ['name'='{user.name}#{user.discriminator}'] started tournament '{tournament_title}' [id={db_tournament['id']}]."
    )

    # Challonge API changed? Retrive matches.
    challonge_matches = challonge.matches.index(db_tournament["challonge"]["id"])

    # Get total number of rounds
    max_round = 0
    for match in challonge_matches:
        round = match["round"]
        if round > max_round:
            max_round = round

    # Set tournament to closed in database and set total number of rounds
    db_tournament.update({"open": False, "in_progress": True, "num_rounds": max_round})
    await set_tournament(guild.id, tournament_title, db_tournament)
    print(
        f"User ['name'='{user.name}#{user.discriminator}'] started tournament ['title'='{tournament_title}']."
    )

    # Send start message
    await tournament_thread.send(embed=create_start_embed(interaction, db_tournament))

    # Get each initial open matches
    matches = list(filter(lambda match: (match["state"] == "open"), challonge_matches))
    for match in matches:
        try:
            await _match.create_match(
                interaction.client, tournament_thread, db_guild, db_tournament, match
            )
        except Exception as e:
            printlog(
                f"Failed to add match ['match_id'='{match['id']}'] to tournament ['title'='{tournament_title}']",
                e,
            )

    # Update embed message
    await edit_tournament_message(db_tournament, tournament_channel, tournament_thread)
    await interaction.followup.send(
        f"Successfully started tournament '***{tournament_title}***'.", ephemeral=True
    )
    return True


async def reset_tournament(interaction: Interaction, tournament_title: str) -> bool:
    """Resets a tournament if it has been started.

    Args:
        interaction (Interaction): The Discord command interaction.
        tournament_title (str): The title of the target tournament.

    Returns:
        bool: True if successful. Otherwise, False.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)

    # Validate arguments
    try:
        (
            db_tournament,
            tournament_title,
            tournament_thread,
            tournament_channel,
        ) = await validate_arguments_tournament(interaction, db_guild, tournament_title)
    except ValueError:
        return False
    challonge_id = db_tournament["challonge"]["id"]

    # Check if it has been started
    if not db_tournament["in_progress"]:
        await interaction.followup.send(
            f"Cannot reset a tournament that is not in progress.", ephemeral=True
        )
        return False

    # Check if already completed
    if db_tournament["completed"]:
        await interaction.followup.send(
            f"Cannot reset a finalized tournament.", ephemeral=True
        )
        return False

    # Delete every match message and document associated with the tournament
    await delete_all_matches(tournament_thread, db_guild, db_tournament)

    # Set all participants back to active
    for i in range(len(db_tournament["participants"])):
        if not db_tournament["participants"][i]["active"]:
            db_tournament["participants"][i].update({"active": True})

    # Reset tournament on challonge
    try:
        challonge.tournaments.reset(challonge_id)
    except Exception as e:
        printlog(
            f"Something went wrong when resetting tournament ['title'='{tournament_title}'] on challonge.",
            e,
        )

    # Set open to true and reset number of rounds
    db_tournament.update(
        {"open": True, "in_progress": False, "num_rounds": None, "matches": []}
    )
    await set_tournament(guild.id, tournament_title, db_tournament)
    print(
        f"User ['name'='{user.name}#{user.discriminator}'] reset tournament ['title'='{tournament_title}']."
    )

    # Reset tournament message
    author: Member = (
        await guild.fetch_member(db_tournament["author"]["id"]) or interaction.user
    )
    new_tournament_embed = create_tournament_embed(db_tournament, author)

    # Check if forum channel before editing content
    if _channel.in_forum(interaction):
        tournament_message = await tournament_thread.fetch_message(
            db_tournament["id"]
        )  # CANNOT FETCH INITIAL MESSAGE IN THREAD
        await tournament_message.edit(
            content="Open for Registration 🚨",
            embed=new_tournament_embed,
            view=RegistrationView(),
        )
    else:
        tournament_message = await tournament_channel.fetch_message(
            db_tournament["id"]
        )  # CANNOT FETCH INITIAL MESSAGE IN THREAD
        await tournament_message.edit(
            embed=new_tournament_embed, view=RegistrationView()
        )
    await tournament_thread.send(embed=create_reset_embed(interaction, db_tournament))
    await interaction.followup.send(
        f"Successfully reset tournament '***{tournament_title}***'.", ephemeral=True
    )
    return True


async def finalize_tournament(interaction: Interaction, tournament_title: str) -> bool:
    """Closes a tournament if it has been completed.

    Args:
        interaction (Interaction): The Discord command interaction.
        tournament_title (str): The title of the target tournament.

    Returns:
        bool: True if successful. Otherwise, False.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    completed_time = datetime.now(tz=EASTERN_ZONE)

    # Validate arguments
    try:
        (
            db_tournament,
            tournament_title,
            tournament_thread,
            tournament_channel,
        ) = await validate_arguments_tournament(interaction, db_guild, tournament_title)
    except ValueError:
        return False

    # Check if already finalized
    if db_tournament["completed"]:
        await interaction.followup.send(
            f"'***{tournament_title}***' has already been finalized.", ephemeral=True
        )
        return False
    challonge_id = db_tournament["challonge"]["id"]

    # Finalize tournament on challonge
    try:
        final_tournament = challonge.tournaments.finalize(
            challonge_id, include_participants=1, include_matches=1
        )
    except Exception as e:
        printlog(
            f"Failed to finalize tournament on challonge ['title'='{tournament_title}'].",
            e,
        )
        try:  # Try and retrive tournament information instead of finalizing
            final_tournament = challonge.tournaments.show(
                challonge_id, include_participants=1, include_matches=1
            )
        except:
            print(
                f"Could not find tournament on challonge ['challonge_id'='{challonge_id}']."
            )
            return False

    # Update participants in database with placement
    db_participants = db_tournament["participants"]
    ch_participants = final_tournament["participants"]
    for i in range(min(len(ch_participants), 8)):
        ch_participant = ch_participants[i]["participant"]
        p_index = find_index_in_tournament(
            db_tournament, "participants", "challonge_id", ch_participant["id"]
        )
        db_participants[p_index].update({"placement": ch_participant["final_rank"]})
    db_tournament["participants"] = db_participants
    # await set_tournament(guild.id, tournament_title, db_tournament)
    # await tournament_thread.send(embed=create_finalize_embed(interaction, db_tournament))

    # Create results message
    db_tournament["completed"] = completed_time  # update completed time
    results_embed = create_results_embed(db_tournament)
    result_message = await tournament_thread.send(embed=results_embed)

    # Set tournament to completed in database
    try:
        db_tournament.update(
            {"result_url": result_message.jump_url}
        )  # update result jump url
        await set_tournament(guild.id, tournament_title, db_tournament)
    except:
        print(f"Failed to update final tournament ['id'='{db_tournament['id']}'].")
        return False

    # Update embed message
    await edit_tournament_message(db_tournament, tournament_channel, tournament_thread)
    print(
        f"User ['name'='{user.name}#{user.discriminator}'] Finalized tournament '{tournament_title}' ['id'='{db_tournament['id']}']."
    )

    # Close thread
    try:
        await tournament_thread.edit(locked=True, pinned=False)
    except:
        print(
            f"Failed to edit thread for tournament '{tournament_title}' ['id'='{db_tournament['id']}']."
        )
    await interaction.followup.send(
        f"Successfully finalized tournament '***{tournament_title}***'.", ephemeral=True
    )
    return True


async def send_results(interaction: Interaction, tournament_title: str) -> bool:
    """Sends the results message of a tournament that has been completed.

    Args:
        interaction (Interaction): The Discord command interaction.
        tournament_title (str): The title of the target tournament.

    Returns:
        bool: True if successful. Otherwise, False.
    """
    guild: Guild = interaction.guild
    db_guild = await _guild.find_guild(guild.id)

    # Fetch tournament
    db_tournament, tournament_title, _ = await find_valid_tournament(
        interaction, db_guild, tournament_title
    )
    if not db_tournament:
        return False

    # Check if tournament is completed
    if not db_tournament["completed"]:
        await interaction.followup.send(
            f"'***{tournament_title}***' has not yet been finalized.", ephemeral=True
        )
        return False

    # Create results message
    results_embed = create_results_embed(db_tournament)
    await interaction.followup.send(embed=results_embed)
    return True


async def open_close_tournament(
    interaction: Interaction, tournament_title: str, open: bool = True
) -> bool:
    """Opens a tournament for registration, or closes it if it has already been opened.

    Args:
        interaction (Interaction): The Discord command interaction.
        tournament_title (str): The title of the target tournament.
        open (bool, optional): Flag to determine if opening or closing the tournament. Defaults to True.

    Returns:
        bool: True if successful. Otherwise, False.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    action = "opened" if open else "closed"

    # Validate arguments
    try:
        (
            db_tournament,
            tournament_title,
            tournament_thread,
            tournament_channel,
        ) = await validate_arguments_tournament(interaction, db_guild, tournament_title)
    except:
        return False

    # Only allow updating if the tournament has not been started or completed
    if db_tournament["in_progress"]:
        await interaction.followup.send(
            f"This tournament has been started; Unable to update registration status.",
            ephemeral=True,
        )
        return False
    if db_tournament["completed"]:
        await interaction.followup.send(
            f"This tournament has been completed; Unable to update registration status.",
            ephemeral=True,
        )
        return False

    # Check if actually updating the status
    if db_tournament["open"] == open:
        await interaction.followup.send(
            f"Registration is already {action} for '***{tournament_title}***'.",
            ephemeral=True,
        )
        return False

    # Update the tournament on challonge
    challonge.tournaments.update(
        db_tournament["challonge"]["id"],
        open_signup=open,
    )
    db_tournament["open"] = open

    # Update the tournament in database
    await set_tournament(guild.id, tournament_title, db_tournament)
    print(
        f"User '{user.name}#{user.discriminator}' {action} registration in tournament ['title'='{tournament_title}']."
    )

    # Update embed message
    await edit_tournament_message(db_tournament, tournament_channel, tournament_thread)
    await interaction.followup.send(
        f"Successfully {action} registration for '***{tournament_title}***'."
    )
    return True


######################
## HELPER FUNCTIONS ##
######################


async def validate_arguments_tournament(
    interaction: Interaction,
    db_guild: dict,
    tournament_title: str = "",
    admin=True,
    respond=True,
):
    """Validate general arguments passed for tournament admin commands.
    
    If the tournament title is not provided, defaults to the guild's current active tournament, 
    or the most recently created tournament.

    Args:
        interaction (Interaction): The Discord command interaction.
        db_guild (dict): The guild database document.
        tournament_title (str, optional): The title of the target tournament. Defaults to "".
        admin (bool, optional): Flag to determine if the user who issued the command needs admin privileges. Defaults to True.
        respond (bool, optional): Flag to determine if a Discord message should be sent in response. Defaults to True.

    Raises:
        ValueError: Invalid tournament title was provided.
        ValueError: User does not have valid permissions in the guild.

    Returns:
        A tuple of the tournament database document, the tournament title, the tournament thread, and the tournament channel.
    """
    guild: Guild = interaction.guild
    user: Member = interaction.user

    # Fetch tournament
    db_tournament, tournament_title, tournament_thread = await find_valid_tournament(
        interaction, db_guild, tournament_title
    )
    if not db_tournament:
        raise ValueError(f"Invalid tournament title. title='{tournament_title}'")

    # Get tournament channel
    tournament_channel = guild.get_channel(db_tournament["channel_id"])

    # Only allow author or guild admins to delete tournament
    if (
        admin
        and user != db_tournament["author"]["id"]
        and not user.guild_permissions.administrator
    ):
        if respond:
            await interaction.followup.send(
                f"Only available to server admins or the tournament author.",
                ephemeral=True,
            )
        raise ValueError(f"User does not have tournament admin permissions.")
    return (db_tournament, tournament_title, tournament_thread, tournament_channel)


async def valid_tournament_channel(
    db_tournament: dict, interaction: Interaction, respond: bool = True
):
    """Checks if performing command in valid channel.
    i.e. Channel that tournament was created in or the tournament thread.
    Returns the tournament channel (TextChannel or ForumChannel).

    Args:
        db_tournament (dict): The target tournament database document.
        interaction (Interaction): The Discord command interaction.
        respond (bool, optional): Flag to determine if a Discord message should be sent in response. Defaults to True.

    Returns:
        The channel of the tournament if valid. Otherwise, None.
    """
    channel_id = (
        interaction.channel_id
        if "thread" not in str(interaction.channel.type)
        else interaction.channel.parent_id
    )
    if db_tournament["id"] != channel_id and channel_id != db_tournament["channel_id"]:
        if respond:
            await interaction.followup.send(
                f"Command only available in <#{db_tournament['id']}> or <#{db_tournament['channel_id']}>.",
                ephemeral=True,
            )
        return None
    return interaction.guild.get_channel_or_thread(
        db_tournament["channel_id"]
    )  # Returns the tournament channel not the tournament thread


async def valid_tournament_thread(
    db_tournament: dict, interaction: Interaction, respond: bool = True
) -> Thread:  # TODO: fix args
    """Checks if performing command in the tournament thread.

    Args:
        db_tournament (dict): The target tournament database document.
        interaction (Interaction): The Discord command interaction.
        respond (bool, optional): Flag to determine if a Discord message should be sent in response. Defaults to True.

    Returns:
        Thread: The tournament Discord thread of the tournament if valid. Otherwise, None.
    """
    channel_id = interaction.channel_id  # Should be a thread ID
    if db_tournament["id"] != channel_id:
        if respond:
            await interaction.followup.send(
                f"Command only available in <#{db_tournament['id']}>.", ephemeral=True
            )
        return None
    return interaction.guild.get_channel_or_thread(db_tournament["id"])


async def find_valid_tournament(
    interaction: Interaction, db_guild: dict, tournament_title: str = ""
):
    """Checks if there is a valid tournament.
    
    If the tournament title is not provided, defaults to the guild's current active tournament, 
    or the most recently created tournament.

    Args:
        interaction (Interaction): The Discord command interaction.
        db_guild (dict): The guild database document.
        tournament_title (str, optional): The title of the target tournament. Defaults to "".

    Returns:
        A tuple of the tournament database document, the tournament title, and the tournament Discord thread.
        Otherwise, a tuple of None, None, None.
    """
    # Get tournament from database
    if len(tournament_title.strip()) > 0:
        # Check if tournament exists
        db_tournament = find_tournament(db_guild, tournament_title)
        if not db_tournament:
            await interaction.followup.send(
                f"Tournament with `title` '***{tournament_title}***' does not exist.",
                ephemeral=True,
            )
            return (None, None, None)
    else:
        # Check if in thread
        if "thread" in str(interaction.channel.type):
            db_tournament = find_tournament_by_id(db_guild, interaction.channel_id)
            if not db_tournament:
                await interaction.followup.send(
                    f"Invalid channel. Either provide the `title` if available or use this command in the tournament thread.",
                    ephemeral=True,
                )
                return (None, None, None)
        else:
            await interaction.followup.send(
                f"Invalid channel. Either provide the `title` if available or use this command in the tournament thread.",
                ephemeral=True,
            )
            return (None, None, None)

    # Get tournament thread
    tournament_thread = interaction.guild.get_thread(db_tournament["id"])
    return (db_tournament, db_tournament["title"], tournament_thread)


def find_index_in_tournament(
    db_tournament: dict, target_field: str, target_key: str, target_value
) -> int:
    """Finds the index of a document in a tournament subdocument list.

    Args:
        db_tournament (dict): The target tournament database document.
        target_field (str): The target document field.
        target_key (str): The target document key.
        target_value (any): The target document value.

    Returns:
        int: The index of the target document if found. Otherwise, -1.
    """
    for i, dic in enumerate(db_tournament[target_field]):
        if dic[target_key] == target_value:
            return i
    return -1


async def set_tournament(guild_id: int, tournament_title: str, new_tournament: dict):
    """Sets a tournament in a guild to the specified document.

    Args:
        guild_id (int): The guild database document.
        tournament_title (str): The title of the target tournament.
        new_tournament (dict): The new tournament document.

    Returns:
        A tuple of the updated guild document and the updated tournament document.
    """
    updated_guild = await mdb.update_single_document(
        {
            "guild_id": guild_id,
            "tournaments.title": tournament_title,
            "tournaments.id": new_tournament["id"],
        },
        {"$set": {f"tournaments.$": new_tournament}},
        GUILDS,
    )
    return updated_guild, find_tournament(updated_guild, tournament_title)


async def add_to_tournament(
    guild_id: int, tournament_title: str, target_field: str, document: dict
):
    """Pushes a document to a tournament subarray.

    Args:
        guild_id (int): The guild database document.
        tournament_title (str): The title of the target tournament.
        target_field (str): The target document field.
        document (dict): The document to add.

    Returns:
        A tuple of the updated guild document and the updated tournament document.
    """
    updated_guild = await mdb.update_single_document(
        {"guild_id": guild_id, "tournaments.title": tournament_title},
        {"$push": {f"tournaments.$.{target_field}": document}},
        GUILDS,
    )
    return updated_guild, find_tournament(updated_guild, tournament_title)


async def remove_from_tournament(
    guild_id: int, tournament_title: str, target_field: str, target_id: int
):
    """Pulls a document from a tournament subarray.

    Args:
        guild_id (int): The guild database document.
        tournament_title (str): The title of the target tournament.
        target_field (str): The target document field.
        target_id (int): The id of the target document to remove.

    Returns:
        A tuple of the updated guild document and the updated tournament document.
    """
    updated_guild = await mdb.update_single_document(
        {"guild_id": guild_id, "tournaments.title": tournament_title},
        {"$pull": {f"tournaments.$.{target_field}": {"id": target_id}}},
        GUILDS,
    )
    return updated_guild, find_tournament(updated_guild, tournament_title)


async def delete_all_matches(
    tournament_thread: Thread, db_guild: dict, db_tournament: dict
):
    """Deletes all matches in the specified tournament.

    Args:
        tournament_thread (Thread): The tournament Discord thread.
        db_guild (dict): The guild database document.
        db_tournament (dict): The target tournament database document.

    Returns:
        A tuple of the updated guild document and tournament document if successful. 
        Otherwise, a tuple of None, None.
    """
    tournament_title = db_tournament["title"]
    for match in db_tournament["matches"]:
        match_id = match["id"]
        try:
            db_guild, db_tournament = await _match.delete_match(
                tournament_thread, db_guild, db_tournament, match_id
            )
        except Exception as e:
            printlog(
                f"Failed to delete match ['id'={match_id}] in tournament ['title'='{tournament_title}'].",
                e,
            )
            return (None, None)
    return (db_guild, db_tournament)


def parse_time(string: str) -> datetime:
    """Helper function to parse a time string in the format XX:XX AM/PM or XX AM/PM.
    Returns the date string and the index of the matched time string.
    If the string is empty, returns the current time + 1 hour.

    Args:
        string (str): The string to parse.

    Raises:
        ValueError: An invalid string was provided.

    Returns:
        datetime: The parsed time as a datetime object.
    """
    if len(string.strip()) == 0:
        return datetime.now(tz=EASTERN_ZONE) + timedelta(hours=1)
    text_match1 = time_re_long.search(string.strip())  # Check for long time
    text_match2 = time_re_short.search(string.strip())  # Check for short time
    if not text_match1 and not text_match2:
        raise ValueError(f"Received invalid input '{string}' for time string.")
    else:
        current_time = datetime.now(tz=EASTERN_ZONE)
        if text_match1:
            try:
                time = datetime.strptime(
                    f"{date.today()} {text_match1.group()}", "%Y-%m-%d %I:%M %p"
                )  # w/ space
            except ValueError:
                time = datetime.strptime(
                    f"{date.today()} {text_match1.group()}", "%Y-%m-%d %I:%M%p"
                )  # no space
        elif text_match2:
            try:
                time = datetime.strptime(
                    f"{date.today()} {text_match2.group()}", "%Y-%m-%d %I %p"
                )  # w/ space
            except ValueError:
                time = datetime.strptime(
                    f"{date.today()} {text_match2.group()}", "%Y-%m-%d %I%p"
                )  # no space
        # Check if current time is before time on current date; If so, go to next day
        time = EASTERN_ZONE.localize(time)  # set time to offset-aware datetime
        if current_time > time:
            time += timedelta(days=1)
    return time


#######################
## MESSAGE FUNCTIONS ##
#######################


def str_status(db_tournament: dict) -> str:
    """Returns the string representation of a tournament's status.

    Args:
        db_tournament (dict): The target tournament database document.

    Returns:
        str: A string representation of the tournament status.
    """
    # Check the status
    if db_tournament["completed"]:
        status = "Completed 🏁"
    elif db_tournament["open"]:
        status = "Open for Registration! 🚨"
    else:
        if db_tournament["in_progress"]:
            status = "Started ⚔️ \n\n See thread for matches."
        else:
            status = "Registration Closed 🔒"
    return status


def create_tournament_embed(db_tournament: dict, author: Member) -> Embed:
    """Creates embed object to include in tournament message.

    Args:
        db_tournament (dict): The target tournament database document.
        author (Member): The user who created the tournament.

    Returns:
        Embed: The created tournament embed.
    """
    tournament_title = db_tournament["title"]
    challonge_url = db_tournament["challonge"]["url"]
    time = db_tournament["start_time"]

    # Check the status
    status = str_status(db_tournament)

    # Main embed
    embed = Embed(
        title=f"🥊  {tournament_title}",
        description=f"Status: {status}",
        color=WOOP_PURPLE,
    )

    # Author field
    embed.set_author(
        name="beta-bot | GitHub 🤖",
        url="https://github.com/fborja44/beta-bot",
        icon_url=ICON,
    )

    # Tournament description fields
    embed.add_field(
        name="Tournament Type", value=db_tournament["tournament_type"].title()
    )
    time_str = time.strftime("%A, %B %d, %Y %#I:%M %p %Z")  # time w/o ms
    embed.add_field(name="Starting At", value=time_str)

    # Entrants list
    if db_tournament["max_participants"]:
        embed.add_field(name="Entrants (0)", value="> *None*", inline=False)
    else:
        max_participants = db_tournament["max_participants"]
        embed.add_field(
            name=f"Entrants (0/{max_participants})", value="> *None*", inline=False
        )
    embed = update_embed_participants(db_tournament, embed)

    # Bracket link
    embed.add_field(name=f"Bracket Link", value=challonge_url, inline=False)

    # Set footer
    embed.set_footer(
        text=f"Created by {author.display_name} | {author.name}#{author.discriminator}.",
        icon_url=db_tournament["author"]["avatar_url"],
    )
    return embed


async def edit_tournament_message(
    db_tournament: dict,
    tournament_channel: TextChannel | ForumChannel,
    tournament_thread: Thread,
) -> bool:
    """Edits tournament embed message in a channel.

    Args:
        db_tournament (dict): The target tournament database document.
        tournament_channel (TextChannel | ForumChannel): _description_
        tournament_thread (Thread): The tournament Discord thread.

    Returns:
        bool: True if successful. Otherwise, False.
    """
    tournament_title = db_tournament["title"]
    if str(tournament_channel.type) == "forum":
        tournament_message = await tournament_thread.fetch_message(db_tournament["id"])
    else:
        tournament_message = await tournament_channel.fetch_message(db_tournament["id"])
    embed = tournament_message.embeds[0]
    embed = update_embed_participants(db_tournament, embed)

    # Update the status
    status = str_status(db_tournament)
    if db_tournament["in_progress"]:
        await tournament_message.edit(view=None)
    else:
        await tournament_message.edit(view=RegistrationView())
    embed.description = f"Status: {status}"

    # Add bracket image.
    if db_tournament["in_progress"]:
        image_embed = None
        try:
            image_embed = create_tournament_image(db_tournament, embed)
            if not image_embed:
                printlog(
                    f"Error when creating image for tournament ['title'='{tournament_title}']."
                )
            else:
                embed = image_embed
        except Exception as e:
            printlog(
                f"Failed to create image for tournament ['title'='{tournament_title}']."
            )
            print(e)
    if db_tournament["completed"]:
        time_str = db_tournament["completed"].strftime(
            "%A, %B %d, %Y %#I:%M %p %Z"
        )  # time w/o ms
        embed.add_field(
            name=f"Completed At",
            value=f"{time_str}\nUse `/bracket results`",
            inline=False,
        )
    content = status if tournament_channel.type == "forum" else ""
    await tournament_message.edit(content=content, embed=embed)
    return True


def update_embed_participants(db_tournament: dict, embed: Embed) -> Embed:
    """Updates the participants list in a tournament embed.

    Args:
        db_tournament (dict): The target tournament database document.
        embed (Embed): The tournament embed to update.

    Returns:
        Embed: The updated tournament embed.
    """
    participants = db_tournament["participants"]
    if len(participants) > 0:
        participants_content = ""
        for participant in participants:
            participants_content += f"> <@{participant['id']}>\n"
    else:
        participants_content = "> *None*"
    max_participants = db_tournament["max_participants"]
    name = (
        f"Entrants ({len(participants)}/{max_participants})"
        if max_participants
        else f"Entrants ({len(participants)})"
    )
    embed.set_field_at(2, name=name, value=participants_content, inline=False)
    return embed


def create_tournament_image(db_tournament: dict, embed: Embed):
    """Creates an image of the tournament.
    Converts the generated svg challonge image to png and uploads it to imgur.
    Discord does not support svg images in preview.
    
    TODO: Fix image functionality

    Args:
        db_tournament (dict): The target tournament database document.
        embed (Embed): The tournament embed to update.

    Returns:
        Embed: The updated tournament embed.
    """
    if len(db_tournament["participants"]) < 2:
        return None
    tournament_title = db_tournament["title"]
    challonge_url = db_tournament["challonge"]["url"]
    svg_url = f"{challonge_url}.svg"
    png_data = svg2png(url=svg_url)  # Convert svg to png
    payload = {"image": png_data}
    headers = {"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}
    response = requests.request(
        "POST", f"{IMGUR_URL}/image", headers=headers, data=payload, files=[]
    )
    if response.status_code == requests.codes.ok:
        data = response.json()["data"]
        image_link = data["link"]
        embed.set_image(url=image_link)
        return embed
    else:
        printlog(
            f"Failed to create image for tournament ['title'='{tournament_title}']."
        )
        return None


def create_seeding_embed(db_tournament: dict) -> Embed:
    """Creates an embed object with the seeding of the tournament.

    Args:
        db_tournament (dict): The target tournament database document.

    Returns:
        Embed: The created seeding embed.
    """
    tournament_title = db_tournament["title"]
    challonge_url = db_tournament["challonge"]["url"]

    # Main embed
    embed = Embed(
        title=f"Seeding for '{tournament_title}'", description="", color=WOOP_PURPLE
    )

    # Author field
    embed.set_author(
        name="beta-bot | GitHub 🤖",
        url="https://github.com/fborja44/beta-bot",
        icon_url=ICON,
    )
    db_participants = db_tournament["participants"]
    db_participants.sort(key=(lambda participant: participant["seed"]))

    # List placements
    for i in range(min(len(db_participants), 8)):
        db_participant = db_participants[i]
        mention = f"<@{db_participant['id']}>"
        embed.description += f"> **{db_participant['seed']}.** {mention}\n"

    # Other info fields
    embed.add_field(name=f"Bracket Link", value=challonge_url, inline=False)
    embed.set_footer(text=f'To update seeding, use `/bracket seed` (Bracket manager only)')
    return embed


def create_results_embed(db_tournament: dict) -> Embed:
    """Creates an embed object with final results to include after finalizing tournament.

    Args:
        db_tournament (dict): The target tournament database document.

    Returns:
        Embed: The created results embed.
    """
    tournament_title = db_tournament["title"]
    challonge_url = db_tournament["challonge"]["url"]
    # Main embed
    embed = Embed(title=f"🏆  Final Results for '{tournament_title}'", color=GOLD)

    # Author field
    embed.set_author(
        name="beta-bot | GitHub 🤖",
        url="https://github.com/fborja44/beta-bot",
        icon_url=ICON,
    )
    results_content = ""
    db_participants = db_tournament["participants"]
    db_participants.sort(key=(lambda participant: participant["placement"]))

    # List placements
    for i in range(min(len(db_participants), 8)):
        db_participant = db_participants[i]
        mention = f"<@{db_participant['id']}>"
        match db_participant["placement"]:
            case 1:
                results_content += f"> 🥇 {mention}\n"
            case 2:
                results_content += f"> 🥈 {mention}\n"
            case 3:
                results_content += f"> 🥉 {mention}\n"
            case _:
                results_content += f"> **{db_participant['placement']}.** {mention}\n"
    embed.add_field(name=f"Placements", value=results_content, inline=False)

    # Other info fields
    embed.add_field(name=f"Bracket Link", value=challonge_url, inline=False)
    time_str = db_tournament["completed"].strftime(
        "%A, %B %d, %Y %#I:%M %p %Z"
    )  # time w/o ms
    embed.set_footer(text=f"Completed: {time_str}")
    return embed


def create_info_embed(db_tournament: dict):
    """Creates a tournament alert embed.

    Args:
        db_tournament (dict): The target tournament database document.

    Returns:
        Embed: The created info embed.
    """
    author_name = db_tournament["author"]["username"]
    thread_id = db_tournament["id"]
    tournament_link = f"<#{thread_id}>"
    time = db_tournament["start_time"]
    embed = Embed(
        title=f"💥 {author_name} has created a new tournament!", color=WOOP_PURPLE
    )
    embed.set_author(
        name="beta-bot | GitHub 🤖",
        url="https://github.com/fborja44/beta-bot",
        icon_url=ICON,
    )

    # Tournament description fields
    embed.add_field(
        name=db_tournament["title"],
        value=f"Register at: {tournament_link}",
        inline=False,
    )
    embed.add_field(
        name="Tournament Type", value=db_tournament["tournament_type"].title()
    )
    time_str = time.strftime("%A, %B %d, %Y %#I:%M %p %Z")  # time w/o ms
    embed.add_field(name="Starting At", value=time_str)
    embed.set_footer(text="Visit the tournament thread to view more details and join.")
    return embed


def create_start_embed(interaction: Interaction, db_tournament: dict):
    """Creates the embed to mark that a tournament has been started.

    Args:
        interaction (Interaction): The Discord command interaction.
        db_tournament (dict): The target tournament database document.

    Returns:
        Embed: The created start embed.
    """
    tournament_title = db_tournament["title"]
    user = interaction.user
    embed = Embed(title=f"🚦 {tournament_title} has been started!", color=WOOP_PURPLE)
    embed.set_author(
        name="beta-bot | GitHub 🤖",
        url="https://github.com/fborja44/beta-bot",
        icon_url=ICON,
    )
    if str(interaction.type) == "application_command":
        embed.set_footer(
            text=f"{user.name}#{user.discriminator} used {full_command(interaction.command)}"
        )
    else:
        embed.set_footer(text=f"{user.name}#{user.discriminator} started the bracket.")
    return embed


def create_reset_embed(interaction: Interaction, db_tournament: dict):
    """Creates an embed to mark that a tournament has been reset.

    Args:
        interaction (Interaction): The Discord command interaction.
        db_tournament (dict): The target tournament database document.

    Returns:
        Embed: The created reset embed.
    """
    tournament_title = db_tournament["title"]
    user = interaction.user
    embed = Embed(title=f"{tournament_title} has been reset.", color=WOOP_PURPLE)
    embed.set_footer(
        text=f"{user.name}#{user.discriminator} used {full_command(interaction.command)}"
    )
    return embed


def create_finalize_embed(interaction: Interaction, db_tournament: dict):
    """Creates an embed to mark that a tournament has been finalized.

    Args:
        interaction (Interaction): The Discord command interaction.
        db_tournament (dict): The target tournament database document.

    Returns:
        Embed: The created embed.
    """
    tournament_title = db_tournament["title"]
    user = interaction.user
    embed = Embed(title=f"🏁 {tournament_title} have been finalized.", color=WOOP_PURPLE)
    embed.set_footer(
        text=f"{user.name}#{user.discriminator} used {full_command(interaction.command)}"
    )
    return embed


def create_help_embed(interaction: Interaction) -> Embed:
    """Creates the help embed for tournaments nad matches.

    Args:
        interaction (Interaction): The Discord command interaction.

    Returns:
        Embed: The created help embed.
    """
    embed = Embed(title=f"📖 Tournament Help", color=WOOP_PURPLE)
    embed.description = "Tournaments can be created in any regular text channel. Tournaments cannot be created in threads or forum channels.\nTournaments can only be managed by the author or server admins."
    # Create
    create_value = """Create a tournament using Discord.
                    `/bracket create title: GENESIS 9`
                    `/bracket create title: The Big House 10 time: 10:00 PM`
                    `/bracket create title: Low Tier City single_elim: True max_participants: 12`"""
    embed.add_field(name="/bracket create", value=create_value, inline=False)
    # Join
    join_value = """Join a tournament in registration phase.
                    `/bracket join`
                    `/bracket join title: GENESIS 9`"""
    embed.add_field(name="/bracket join", value=join_value, inline=False)
    # Leave
    leave_value = """Leave a tournament in registration phase.
                    `/bracket leave`
                    `/bracket leave title: GENESIS 9`"""
    embed.add_field(name="/bracket leave", value=leave_value, inline=False)
    # Seeding
    seeding_value = """Displays the seeding for a tournament.
                    `/bracket seeding`
                    `/bracket seeding title: GENESIS 9`"""
    embed.add_field(name="/bracket seeding", value=seeding_value, inline=False)
    # Set Seed
    set_seed_value = f"""Sets the seed for a participant in a tournament.
                    `/bracket seed user_mention: `<@{interaction.client.user.id}> `seed: 1`
                    `/bracket seed user_mention: `<@{interaction.client.user.id}> `seed: 1 title: GENESIS 9`"""
    embed.add_field(name="/bracket seed", value=set_seed_value, inline=False)
    # Randomize Seeding
    randomize_value = """Randomizes the seeding for a tournament.
                    `/bracket randomize`
                    `/bracket randomize title: GENESIS 9`"""
    embed.add_field(name="/bracket randomize", value=randomize_value, inline=False)
    # Delete
    delete_value = """Delete a tournament.
                    `/bracket delete`
                    `/bracket delete title: GENESIS 9`"""
    embed.add_field(name="/bracket delete", value=delete_value, inline=False)
    # Update
    update_value = """Updates a tournament according to specified fields.
                    `/bracket update title: GENESIS 9 new_title: GENESIS 10`
                    `/bracket update title: The Big House 10 time: 9:30 PM`
                    `/bracket update title: Low Tier city single_elim: False max_participants: 16`"""
    embed.add_field(name="/bracket update", value=update_value, inline=False)
    # Start
    start_value = """Starts a tournament with at least 2 participants.
                    `/bracket start`
                    `/bracket start title: GENESIS 9`"""
    embed.add_field(name="/bracket start", value=start_value, inline=False)
    # Reset
    reset_value = """Resets a tournament back to registration phase.
                    `/bracket reset`
                    `/bracket reset title: GENESIS 9`"""
    embed.add_field(name="/bracket reset", value=reset_value, inline=False)
    # Finalize
    finalize_value = """Finalizes the results of a tournament if available.
                    `/bracket finalize`
                    `/bracket finalize title: GENESIS 9`"""
    embed.add_field(name="/bracket finalize", value=finalize_value, inline=False)
    # Results
    results_value = """Displays the results of a finalized tournament if available.
                    `/bracket results`
                    `/bracket results title: GENESIS 9`"""
    embed.add_field(name="/bracket results", value=results_value, inline=False)
    # Disqualify
    disqualify_value = f"""Disqualifies a user from a tournament.
                        `/bracket disqualify user_mention:` <@{interaction.client.user.id}>"""
    embed.add_field(name="/bracket disqualify", value=disqualify_value, inline=False)
    # Vote
    vote_value = f"""Vote for a winner in a tournament match.
                    `/match vote match_id: 1034908912 vote: ` <@{interaction.client.user.id}>
                    `/match vote match_id: 1034908912 vote: 1️⃣`
                    `/match vote match_id: 1034908912 vote: 1`"""
    embed.add_field(name="/match vote", value=vote_value, inline=False)
    # Report
    report_value = f"""Manually report the result of a tournament match.
                    `/match report match_id: 1034908912 winner: ` <@{interaction.client.user.id}>
                    `/match report match_id: 1034908912 winner: 1️⃣`
                    `/match report match_id: 1034908912 winner: 1`"""
    embed.add_field(name="/match report", value=report_value, inline=False)
    # Medic
    report_value = f"""Re-calls any missing matches in discord.
                    `/match medic`"""
    embed.add_field(name="/match medic", value=report_value, inline=False)
    # Footer
    embed.set_footer(text=f"For more detailed docs, see the README on GitHub.")
    return embed


#######################
## TESTING FUNCTIONS ##
#######################


async def create_test_tournament(
    interaction: Interaction, num_participants: int = 4
) -> bool:
    """Testing function. Creates a test tournament and adds participants.

    Args:
        interaction (Interaction): The Discord command interaction.
        num_participants (int, optional): The number of participants to add in the test tournament. Max of 4. Defaults to 4.

    Returns:
        bool: True if successful. Otherwise, False.
    """
    # Check number of participants
    if num_participants > 4:
        return await interaction.followup.send(
            f"There is a maxmimum of 4 participants in the test tournament."
        )
    
    printlog("Creating test tournament...")
    tournament_title = "Test Tournament"
    _, tournament_message, _ = None, None, None
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    user: Member = interaction.user
    db_guild = await _guild.find_add_guild(guild)
    # Only allow guild admins to create a test tournament
    if not user.guild_permissions.administrator:
        return await interaction.followup.send(
            f"Only admins can create a test tournament."
        )

    # Delete previous test tournament if it exists
    try:
        db_tournament = find_tournament(db_guild, tournament_title)
        if db_tournament:
            await delete_tournament(interaction, tournament_title, respond=False)
        # Call create_tournament
        db_tournament, tournament_message, _ = await create_tournament(
            interaction, tournament_title, respond=False
        )

        members = [
            guild.get_member_named("beta#3096"),
            guild.get_member_named("pika!#3722"),
            guild.get_member_named("Wooper#0478"),
            guild.get_member_named("WOOPBOT#4140"),
        ]
        for i in range(num_participants):
            try:
                await _participant.add_participant(
                    interaction, db_tournament, member=members[i], respond=False
                )
            except:
                pass
        await interaction.followup.send(
            f"Finished generating Test Tournament and participants."
        )
        return True
    except Exception as e:
        printlog("Failed to create test tournament.", channel)
        print_exception(e)
        await interaction.followup.send(
            f"Something went wrong when generating the test tournament.", ephemeral=True
        )
        if tournament_message:
            await delete_tournament(interaction, tournament_title, respond=False)
        return False
