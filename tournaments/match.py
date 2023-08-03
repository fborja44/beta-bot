from datetime import datetime
from pprint import pprint

import challonge
import discord
import pytz
from discord import (
    Button,
    Client,
    Embed,
    Guild,
    Interaction,
    Member,
    Message,
    NotFound,
    TextChannel,
    Thread,
    User,
)

from guilds import guild as _guild
from tournaments import challenge as _challenge
from tournaments import participant as _participant
from tournaments import tournament as _tournament
from utils.color import BLACK, GREEN, RED, WOOP_PURPLE
from utils.common import full_command
from utils.constants import ICON, MATCHES
from utils.log import printlog
from views.voting_buttons import create_voting_view

# match.py
# Tournament matches


def find_match(db_tournament: dict, match_id: int):
    """
    Retrieves and returns a match document from the database (if it exists).
    """
    tournament_matches = db_tournament["matches"]
    result = [match for match in tournament_matches if match["id"] == match_id]
    if result:
        return result[0]
    return None


def find_match_by_challonge_id(db_tournament: dict, challonge_id: int):
    """
    Retrieves and returns a match document from the database (if it exists).
    """
    tournament_matches = db_tournament["matches"]
    result = [
        match for match in tournament_matches if match["challonge_id"] == challonge_id
    ]
    if result:
        return result[0]
    return None


async def create_match(
    self: Client,
    tournament_thread: Thread,
    db_guild: dict,
    db_tournament: dict,
    challonge_match,
    db: bool = True,
):
    """
    Creates a new match in a tournament.
    """
    tournament_title = db_tournament["title"]
    # Create match message and embed
    # Get player names
    player1 = _participant.find_participant_by_challonge_id(db_tournament, challonge_match["player1_id"])
    player2 = _participant.find_participant_by_challonge_id(db_tournament, challonge_match["player2_id"])

    new_match = {
        "id": None,
        "challonge_id": challonge_match["id"],
        "player1": {"id": player1["id"], "vote": None},
        "player2": {"id": player2["id"], "vote": None},
        "round": challonge_match["round"],
        "opened_at": datetime.now(tz=pytz.timezone("US/Eastern")),
        "completed": False,
        "winner_emote": None,
        "next_matches": [],
    }

    # Generate interactive buttons view
    button_view = create_voting_view(new_match, player1, player2)

    # Send embed message
    embed = create_match_embed(db_tournament, new_match)
    match_message = await tournament_thread.send(
        f"<@{player1['id']}> vs <@{player2['id']}>", embed=embed, view=button_view
    )

    self.add_view(button_view, message_id=match_message.id)

    # Add match document to database
    new_match["id"] = match_message.id
    if db:
        try:
            db_guild, db_tournament = await _tournament.add_to_tournament(
                db_guild["guild_id"], tournament_title, MATCHES, new_match
            )
            print(
                f"Added new match ['id'='{match_message.id}'] to tournament ['name'='{tournament_title}']."
            )
        except Exception as e:
            printlog(
                f"Failed to add match ['id'={new_match['id']}] to tournament ['name'='{tournament_title}'].",
                e,
            )
            return None
    return new_match


async def delete_match(
    tournament_thread: Thread, db_guild: dict, db_tournament: dict, match_id: int
):
    """
    Deletes a match, and recursively deletes all dependent matches.
    """
    guild: Guild = tournament_thread.guild
    guild_id = guild.id
    tournament_title = db_tournament["title"]

    # Check if match is in database
    try:
        db_match = find_match(db_tournament, match_id)
    except:
        print(
            "Something went wrong when checking database for match ['id'='{match_id}']."
        )

    if db_match:
        # Recursively delete matches that come after this one
        for next_match_id in db_match["next_matches"]:
            db_guild, db_tournament = await delete_match(
                tournament_thread, db_guild, db_tournament, next_match_id
            )

        # Delete from matches
        try:
            db_guild, db_tournament = await _tournament.remove_from_tournament(
                guild_id, tournament_title, MATCHES, match_id
            )
            print(
                f"Deleted match ['id'='{db_match['id']}'] from tournament ['name'='{tournament_title}']."
            )
        except:
            print(
                f"Failed to delete match [id='{match_id}'] from database for tournament ['name'='{tournament_title}']."
            )
            return (None, None)

        # Delete match message
        try:
            match_message = await tournament_thread.fetch_message(db_match["id"])
            await match_message.delete()  # delete message from channel
        except NotFound:
            printlog(
                f"Failed to delete message for match [id='{match_id}']; Not found."
            )
        except discord.Forbidden:
            printlog(
                f"Failed to delete message for match [id='{match_id}']; Bot does not have proper permissions."
            )
            return (None, None)
    return (db_guild, db_tournament)


async def vote_match_button(interaction: Interaction, button: Button):
    """
    Reports the winner for a tournament match using buttons.
    button_id is expected to be 1️⃣ or 2️⃣.
    """
    channel: TextChannel = interaction.channel
    guild: Guild = interaction.guild
    message: Message = interaction.message
    db_guild = await _guild.find_guild(guild.id)
    match_message: Message = await channel.fetch_message(message.id)
    emoji = button.emoji.name

    # Check args
    if emoji not in ["1️⃣", "2️⃣"]:
        await interaction.followup.send("Invalid vote.")
        return False

    # Get current active tournament, if any
    db_tournament = _tournament.find_active_tournament(db_guild)
    if not db_tournament:
        return False

    # Check if reaction was on a match message
    db_match = find_match(db_tournament, match_message.id)
    if not db_match:
        return False

    # Match is already completed
    if db_match["completed"]:
        await interaction.followup.send("This match has already been completed.")
        return False

    # Call main vote recording function
    return await record_vote(
        interaction, emoji, match_message, db_guild, db_match, db_tournament
    )


async def vote_match(interaction: Interaction, match_challonge_id: int, vote: str):
    """
    Vote for a match using a command.
    """
    guild: Guild = interaction.guild
    channel: TextChannel = interaction.channel
    db_guild = await _guild.find_guild(guild.id)
    vote_emote, db_tournament, db_match = await parse_vote(
        interaction, db_guild, match_challonge_id, vote
    )
    if not db_tournament or not db_match or not vote_emote:
        return False

    # Check if in valid channel
    if not await _tournament.valid_tournament_thread(db_tournament, interaction):
        return False
    if not vote_emote:
        return False

    # Match is already completed
    if db_match["completed"]:
        await interaction.followup.send("This match has already been completed.")
        return False
    match_message: Message = await channel.fetch_message(db_match["id"])

    # Call main vote recording function
    return await record_vote(
        interaction, vote_emote, match_message, db_guild, db_match, db_tournament
    )


async def record_vote(
    interaction: Interaction,
    vote_emoji: str,
    match_message: Message,
    db_guild: dict,
    db_match: dict,
    db_tournament: dict = None,
):
    """
    Main function for voting on match results by buttons.
    Used for matches or challenges.
    """
    match_type = "match" if db_tournament else "challenge"
    match_id = db_match["id"]
    match_embed: Embed = match_message.embeds[0]
    user: Member = interaction.user

    # Check if user was one of the players
    if user.id == db_match["player1"]["id"]:
        voter = db_match["player1"]
        opponent = db_match["player2"]
    elif user.id == db_match["player2"]["id"]:
        voter = db_match["player2"]
        opponent = db_match["player1"]
    else:
        await interaction.followup.send(
            f"You are not a player in this match.", ephemeral=True
        )
        return False

    # Check if match is open
    if db_match["completed"]:
        await interaction.followup.send(
            f"Vote failed. This match has already been completed.", ephemeral=True
        )
        return False

    # Check if switching vote
    switched = voter["vote"] is not None and voter["vote"] != vote_emoji

    # Record vote or remove vote
    if voter["vote"] != vote_emoji:
        vote = vote_emoji
        action = "Added" if not voter["vote"] else "Changed"
    else:
        if opponent["vote"] is not None:
            await interaction.followup.send(
                f"You cannot remove your vote if both players have voted. Either vote for the other player, or contact and admin.",
                ephemeral=True,
            )
            return False
        vote = None
        action = "Removed"

    # Update match player in database
    try:
        player1 = db_match["player1"]
        player2 = db_match["player2"]
        if voter == player1:
            player1["vote"] = vote
            if db_tournament:
                result = await update_player(
                    db_guild["guild_id"],
                    db_tournament,
                    match_id,
                    updated_player1=player1,
                )
            else:
                result = await _challenge.update_player(
                    db_guild, match_id, updated_player1=player1
                )
            db_match["player1"] = player1
        else:
            player2["vote"] = vote
            if db_tournament:
                result = await update_player(
                    db_guild["guild_id"],
                    db_tournament,
                    match_id,
                    updated_player2=player2,
                )
            else:
                result = await _challenge.update_player(
                    db_guild, match_id, updated_player2=player2
                )
            db_match["player2"] = player2
        print(
            f"{action} vote by user ['discord_id'='{user.id}'] for {match_type} ['id'={match_id}']"
        )

    except Exception as e:
        printlog(
            f"Failed to record vote by user ['discord_id'='{user.id}'] for {match_type} ['id'='{match_id}'].",
            e,
        )
        await interaction.followup.send(
            f"Something went wrong while voting for {vote}.", ephemeral=True
        )
        return False

    if not result:
        print(
            f"Failed to update player while changing vote in {match_type} ['id'='{match_id}']"
        )
        await interaction.followup.send(
            f"Something went wrong while voting for {vote}.", ephemeral=True
        )
        return False

    # Update embed with vote
    match_embed = edit_match_embed_report(match_embed, db_match)
    await match_message.edit(embed=match_embed)

    # Check if both players voted
    if player1["vote"] and player2["vote"]:
        # Check who they voted for
        if player1["vote"] == player2["vote"]:
            # Report match
            if db_tournament:
                await report_match(
                    interaction.client,
                    match_message,
                    db_guild,
                    db_tournament,
                    db_match,
                    vote,
                )
            else:
                await _challenge.report_challenge(
                    match_message, db_guild, db_match, vote
                )
        else:
            # Dispute has occurred
            printlog(f"Dispute detected in {match_type} ['id'='{match_id}'].")
            if db_tournament:
                dispute_embed = edit_match_embed_dispute(match_embed)
            else:
                dispute_embed = _challenge.edit_challenge_embed_dispute(match_embed)
            await match_message.edit(embed=dispute_embed)
    if vote:
        if switched:
            await interaction.followup.send(
                f"Successfully switched vote to {vote}.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"Successfully voted for {vote}.", ephemeral=True
            )
    else:
        await interaction.followup.send(f"Successfully removed vote.", ephemeral=True)
    return True


async def report_match(
    self: Client,
    match_message: Message,
    db_guild: dict,
    db_tournament: dict,
    db_match: dict,
    winner_emote: str,
    is_dq: bool = False,
):
    """
    Reports a match winner and fetches the next matches that have not yet been called.
    """
    tournament_title = db_tournament["title"]
    tournament_challonge_id = db_tournament["challonge"]["id"]
    match_challonge_id = db_match["challonge_id"]
    match_id = db_match["id"]
    if winner_emote == "1️⃣":
        winner: dict = _participant.find_participant(
            db_tournament, db_match["player1"]["id"]
        )
        score = "1-0"
    elif winner_emote == "2️⃣":
        winner: dict = _participant.find_participant(
            db_tournament, db_match["player2"]["id"]
        )
        score = "0-1"
        
    # Update on challonge
    try:
        challonge.matches.update(
            tournament_challonge_id,
            match_challonge_id,
            scores_csv=score,
            winner_id=winner["challonge_id"],
        )
    except Exception as e:
        printlog(
            f"Something went wrong when reporting match ['challonge_id'={match_challonge_id}] on challonge.",
            e,
        )
        return None, None
    
    # Update status in db
    try:
        db_match.update(
            {
                "completed": datetime.now(tz=pytz.timezone("US/Eastern")),
                "winner_emote": winner_emote,
            }
        )
        await set_match(db_guild["guild_id"], db_tournament, db_match)
    except Exception as e:
        printlog(f"Failed to report match ['id'={match_id}] in database.", e)
        return None, None
    
    # Update match embed
    match_embed = match_message.embeds[0]
    participant1 = _participant.find_participant(
        db_tournament, db_match["player1"]["id"]
    )
    participant2 = _participant.find_participant(
        db_tournament, db_match["player2"]["id"]
    )
    confirm_embed = edit_match_embed_confirmed(
        match_embed, match_challonge_id, participant1, participant2, winner_emote, is_dq
    )
    confirm_embed.remove_field(1)  # Remove votes field
    await match_message.edit(embed=confirm_embed, view=None)
    print(
        "Succesfully reported match [id={0}]. Winner = '{1}'.".format(
            match_id, winner["name"]
        )
    )
    
    # Call new open matches
    count = await call_open_matches(
        self, match_message.channel, db_guild, db_tournament
    )
    
    # Check if was last match in the tournament
    if count == 0 and db_match["round"] == db_tournament["num_rounds"]:
        await match_message.channel.send(
            f"'***{db_tournament['title']}***' has been completed! Use `/t finalize {db_tournament['title']}` to finalize the results!"
        )
        
    # Update tournament embed
    try:
        tournament_channel = await match_message.guild.fetch_channel(
            db_tournament["channel_id"]
        )
        if str(tournament_channel.type) == "forum":
            tournament_message: Message = await match_message.channel.fetch_message(
                db_tournament["id"]
            )
        else:
            tournament_message: Message = await tournament_channel.fetch_message(
                db_tournament["id"]
            )
        updated_tournament_embed = _tournament.create_tournament_image(
            db_tournament, tournament_message.embeds[0]
        )
        await tournament_message.edit(embed=updated_tournament_embed)
    except Exception as e:
        printlog(
            f"Failed to create image for tournament ['title'='{tournament_title}'].", e
        )
    return db_match, winner


async def call_open_matches(
    self: Client, tournament_thread: Thread, db_guild: dict, db_tournament: dict
):
    """
    Calls newly opened matches from challonge.
    Returns the number of new open matches, or -1 if failed.
    """
    try:
        challonge_matches = challonge.matches.index(
            db_tournament["challonge"]["id"], state="open"
        )
    except Exception as e:
        printlog("Failed to get new matches.", e)
        return -1
    for challonge_match in challonge_matches:
        # Check if match has already been called (in database)
        try:
            check_match = find_match_by_challonge_id(
                db_tournament, challonge_match["id"]
            )
        except Exception as e:
            printlog("Failed to check match in database.", e)
            return -1
        # Get match message too
        if check_match:
            continue
        new_match = await create_match(
            self, tournament_thread, db_guild, db_tournament, challonge_match
        )
        db_tournament["matches"].append(new_match)
        # Add new match message_id to dependent matches' next_matches list
        try:
            db_match1 = find_match_by_challonge_id(
                db_tournament, challonge_match["player1_prereq_match_id"]
            )
            if db_match1:
                db_match1["next_matches"].append(new_match["id"])
                await set_match(db_guild["guild_id"], db_tournament, db_match1)
                print(
                    f"Added new match ['id'={new_match['id']}] to next_matches of match ['id'='{db_match1['id']}']."
                )
        except Exception as e:
            print(
                f"Failed to add new match ['id'='{new_match['id']}'] to next_matches of match ['id'='{db_match1['id']}']"
            )
            print(e)
        try:
            if (
                challonge_match["player1_prereq_match_id"]
                != challonge_match["player2_prereq_match_id"]
            ):
                db_match2 = find_match_by_challonge_id(
                    db_tournament, challonge_match["player2_prereq_match_id"]
                )
                if db_match2:
                    db_match2["next_matches"].append(new_match["id"])
                    await set_match(db_guild["guild_id"], db_tournament, db_match2)
                    print(
                        f"Added new match ['id'={new_match['id']}] to next_matches of match ['id'='{db_match2['id']}']."
                    )
        except Exception as e:
            print(
                f"Failed to add new match ['id'='{new_match['id']}'] to next_matches of match ['id'='{db_match2['id']}']"
            )
            print(e)
            return -1
    return len(challonge_matches)


async def override_match_result(
    interaction: Interaction, match_challonge_id: int, winner: str
):
    """
    Overrides the results of a match. The status of the match does not matter.
    Only usable by tournament creator or tournament manager
    """
    guild: Guild = interaction.guild
    channel: TextChannel = interaction.channel
    user: Member = interaction.user
    db_guild = await _guild.find_guild(guild.id)
    winner_emote, db_tournament, db_match = await parse_vote(
        interaction, db_guild, match_challonge_id, winner
    )
    if not db_tournament or not winner_emote or not db_match:
        return False
    # Check if in valid channel
    tournament_thread = await _tournament.valid_tournament_thread(
        db_tournament, interaction
    )
    if not tournament_thread:
        return False
    # Check if actually changing the winner
    if (
        db_match["winner_emote"] is not None
        and winner_emote == db_match["winner_emote"]
    ):
        await interaction.followup.send(
            "Match report failed; Winner is the same.", ephemeral=True
        )
        return False
    # Delete newly created matches
    next_matches = db_match["next_matches"]
    if len(next_matches) > 0:
        for next_match_id in next_matches:
            db_guild, db_tournament = await delete_match(
                tournament_thread, db_guild, db_tournament, next_match_id
            )
    # Report match
    match_message = await channel.fetch_message(db_match["id"])
    try:
        _, db_winner = await report_match(
            interaction.client,
            match_message,
            db_guild,
            db_tournament,
            db_match,
            winner_emote,
        )
    except Exception as e:
        printlog(f"Failed to report match ['id'='{db_match['id']}']", e)
        return False
    printlog(
        f"User ['name'='{user.name}#{user.discriminator}'] overwrote result for match ['id'='{db_match['id']}']. Winner: {db_winner['name']} {winner_emote}."
    )
    await tournament_thread.send(
        embed=create_report_embed(interaction, db_match, db_winner)
    )
    await interaction.followup.send(
        content=f"Match report successful. Winner: {db_winner['name']} {winner_emote}",
        ephemeral=True,
    )
    return True


async def repair_match(interaction: Interaction, tournament_title: str = ""):
    """
    Recalls all incomplete matches whose messages are missing (i.e. have been deleted).
    Only works if the match exists in the database (i.e. has been called previously).
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
            _,
        ) = await _tournament.validate_arguments_tournament(
            interaction, db_guild, tournament_title
        )
    except ValueError:
        return False
    # Go through all matches and check if they need to be recalled
    printlog(
        f"User '{user.name}#{user.discriminator}' called match medic for tournament '{db_tournament['title']}'"
    )
    count = 0
    for db_match in db_tournament["matches"]:
        # Check if match has already been completed
        if db_match["completed"]:
            continue
        # Check if match message exists
        try:
            await tournament_thread.fetch_message(db_match["id"])
        except NotFound:
            ch_match = challonge.matches.show(
                db_tournament["challonge"]["id"], db_match["challonge_id"]
            )
            # Re-call the match in discord
            new_match = await create_match(
                interaction.client,
                tournament_thread,
                db_guild,
                db_tournament,
                ch_match,
                db=False,
            )
            # Update match id in database
            await set_match(guild.id, db_tournament, new_match)
            print(f"Repaired match ['id'='{db_match['id']}'].")
            count += 1
    await tournament_thread.send(embed=create_repair_embed(interaction, count))
    await interaction.followup.send(
        f"Successfully repaired {count} matches.", ephemeral=True
    )
    return True


async def reset_match(interaction: Interaction, match_challonge_id: int):
    """
    Resets a match and recalls the message.
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
            _,
        ) = await _tournament.validate_arguments_tournament(interaction, db_guild)
    except ValueError:
        return False
    # Fetch match
    db_match = find_match_by_challonge_id(db_tournament, match_challonge_id)
    if not db_match:
        await interaction.followup.send(f"`match_id` is invalid.", ephemeral=True)
        return False
    # Check if valid match
    if not db_match["completed"]:
        await interaction.followup.send(f"This match has not been completed.")
        return False
    # Reset match on challonge
    try:
        challonge.matches.reopen(
            db_tournament["challonge"]["id"], match_challonge_id
        )  # does not return anything
        ch_match = challonge.matches.show(
            db_tournament["challonge"]["id"], match_challonge_id
        )
    except Exception as e:
        printlog(
            f"Failed to reset match ['id'='{match_challonge_id}'] on challonge in tournament '{tournament_title}'.",
            e,
        )
        await interaction.followup.send("Failed to reset match on Challonge.")
        return False
    # Delete match (and others that come out of it)
    db_guild, db_tournament = await delete_match(
        tournament_thread, db_guild, db_tournament, db_match["id"]
    )
    # Recreate match
    await create_match(
        interaction.client, tournament_thread, db_guild, db_tournament, ch_match
    )
    printlog(
        f"User '{user.name}#{user.discriminator}' reset match ['id'='{db_match['id']}'] in tournament '{tournament_title}'."
    )
    await tournament_thread.send(embed=create_reset_embed(interaction, db_match))
    # Update tournament embed
    try:
        tournament_channel = await tournament_thread.guild.fetch_channel(
            db_tournament["channel_id"]
        )
        if str(tournament_channel.type) == "forum":
            tournament_message: Message = await tournament_thread.fetch_message(
                db_tournament["id"]
            )
        else:
            tournament_message: Message = await tournament_channel.fetch_message(
                db_tournament["id"]
            )
        updated_tournament_embed = _tournament.create_tournament_image(
            db_tournament, tournament_message.embeds[0]
        )
        await tournament_message.edit(embed=updated_tournament_embed)
    except Exception as e:
        printlog(
            f"Failed to create image for tournament ['title'='{tournament_title}'].", e
        )
    await interaction.followup.send(
        f"Match has been successfully reset.", ephemeral=True
    )
    return True


######################
## HELPER FUNCTIONS ##
######################


async def update_player(
    guild_id: int,
    db_tournament: dict,
    match_id: int,
    updated_player1=None,
    updated_player2=None,
):
    """
    Updates the players in a match.
    """
    tournament_title = db_tournament["title"]
    match_index = _tournament.find_index_in_tournament(
        db_tournament, MATCHES, "id", match_id
    )
    if updated_player1:
        db_tournament["matches"][match_index]["player1"] = updated_player1
    if updated_player2:
        db_tournament["matches"][match_index]["player2"] = updated_player2
    if not (updated_player1 or updated_player2):
        return None
    return await _tournament.set_tournament(guild_id, tournament_title, db_tournament)


async def set_match(guild_id: int, db_tournament: dict, db_match: dict):
    """
    Updates a match document in the database.
    """
    tournament_title = db_tournament["title"]
    match_index = _tournament.find_index_in_tournament(
        db_tournament, MATCHES, "id", db_match["id"]
    )
    db_tournament["matches"][match_index] = db_match
    return await _tournament.set_tournament(guild_id, tournament_title, db_tournament)


async def fetch_tournament_and_match(
    interaction: Interaction, db_guild: dict, match_challonge_id: int
):
    """
    Returns the current active tournament and targeted match if they exist.
    """
    # Fetch active tournament
    db_tournament = _tournament.find_active_tournament(db_guild)
    if not db_tournament:
        await interaction.followup.send(
            f"There are currently no active tournaments.", ephemeral=True
        )
        return (None, None)
    # Get match
    db_match = find_match_by_challonge_id(db_tournament, match_challonge_id)
    if not db_match:
        await interaction.followup.send(f"`match_id` is invalid.", ephemeral=True)
        return (None, None)
    return (db_tournament, db_match)


async def parse_vote(
    interaction: Interaction, db_guild: dict, match_challonge_id: int, vote: str
):
    """
    Parses a vote argument that can either be an emote (1 or 2) or a player name.
    """
    # Fetch active tournament and targeted match
    db_tournament, db_match = await fetch_tournament_and_match(
        interaction, db_guild, match_challonge_id
    )
    if not db_tournament or not db_match:
        return (None, None, None)
    # Check vote emote
    vote_emote = valid_vote_emote(vote)
    # Find by name if applicable
    if not vote_emote:
        player1_id = db_match["player1"]["id"]
        player2_id = db_match["player2"]["id"]
        participant: Member = _participant.parse_user_mention(interaction, vote)
        if not participant:
            await interaction.followup.send(
                f"Invalid vote. ex. 1️⃣, 2️⃣, or <@{interaction.client.user.id}>",
                ephemeral=True,
            )
            return (None, None, None)
        if player1_id == participant.id:
            vote_emote = "1️⃣"
        elif player2_id == participant.id:
            vote_emote = "2️⃣"
        else:
            await interaction.followup.send(
                f"User <@{participant.id}> is not a participant in this match.",
                ephemeral=True,
            )
            return (None, None, None)
    return (vote_emote, db_tournament, db_match)


def valid_vote_emote(vote: str):
    """
    Checks if a vote string can be validated into an emote. Returns '1️⃣', '2️⃣' if valid, None otherwise.
    """
    valid1 = ["1", "1️⃣"]
    valid2 = ["2", "2️⃣"]
    if vote in valid1:
        return "1️⃣"
    elif vote in valid2:
        return "2️⃣"
    else:
        return None


#######################
## MESSAGE FUNCTIONS ##
#######################


def create_match_embed(db_tournament: dict, db_match: dict):
    """
    Creates embed object to include in match message.
    """
    tournament_title = db_tournament["title"]
    match_challonge_id = db_match["challonge_id"]
    jump_url = db_tournament["jump_url"]
    round = db_match["round"]
    player1_id = db_match["player1"]["id"]
    player2_id = db_match["player2"]["id"]
    player1_vote = db_match["player1"]["vote"]
    player2_vote = db_match["player2"]["vote"]
    time = datetime.now(tz=pytz.timezone("US/Eastern")).strftime("%#I:%M %p %Z")
    round_name = get_round_name(db_tournament, match_challonge_id, round)
    # Main embed
    embed = Embed(
        title=f"⚔️ {round_name}",
        description=f"Awaiting result...\nOpened at {time}",
        color=GREEN,
    )
    # Author field
    # embed.set_author(name=tournament_title, url=jump_url, icon_url=ICON)
    # Match info field
    if round_name == "Grand Finals Set 1" and len(db_tournament["participants"]) > 2:
        embed.add_field(
            name=f"Players",
            value=f"1️⃣ [W] <@{player1_id}> vs <@{player2_id}> [L] 2️⃣",
            inline=False,
        )
    elif round_name == "Grand Finals Set 2" and len(db_tournament["participants"]) > 2:
        embed.add_field(
            name=f"Players",
            value=f"1️⃣ [L] <@{player1_id}> vs <@{player2_id}> [L] 2️⃣",
            inline=False,
        )
    else:
        embed.add_field(
            name=f"Players",
            value=f"1️⃣ <@{player1_id}> vs <@{player2_id}> 2️⃣",
            inline=False,
        )
    # Match votes
    embed.add_field(
        name=f"Results Reporting",
        value=f"<@{player1_id}>: *{player1_vote}*\n<@{player2_id}>: *{player2_vote}*",
        inline=False,
    )
    # Match footer
    embed.set_footer(
        text=f"Players vote with 1️⃣ or 2️⃣ to report the winner.\nmatch_id: {match_challonge_id}\nOr use `/match vote`."
    )
    return embed


def edit_match_embed_report(embed: Embed, db_match: dict):
    """
    Updates embed object for disputes.
    """
    player1_id = db_match["player1"]["id"]
    player2_id = db_match["player2"]["id"]
    player1_vote = db_match["player1"]["vote"]
    player2_vote = db_match["player2"]["vote"]
    embed.set_field_at(
        1,
        name=f"Results Reporting",
        value=f"<@{player1_id}>: *{player1_vote}*\n<@{player2_id}>: *{player2_vote}*",
        inline=False,
    )
    return embed


def edit_match_embed_dispute(embed: Embed):
    """
    Updates embed object for disputes.
    """
    embed.add_field(
        name="🛑 Result Dispute 🛑",
        value="Contact a tournament manager or change vote to resolve.",
    )
    embed.color = RED
    return embed


def edit_match_embed_confirmed(
    embed: Embed,
    match_id: int,
    player1: dict,
    player2: dict,
    winner_emote: str,
    is_dq: bool = False,
):
    """
    Updates embed object for confirmed match.
    For tournament tournament matches, match_id is the challonge_id.
    For 1v1 challenge matches, match_id is the id (message_id).
    """
    time = datetime.now(tz=pytz.timezone("US/Eastern")).strftime("%#I:%M %p %Z")
    player1_id = player1["id"]
    player2_id = player2["id"]

    if winner_emote == "1️⃣":
        winner = player1
        player1_emote = "⭐"
        player2_emote = "❌" if not is_dq else "🇩🇶"
    else:
        winner = player2
        player2_emote = "⭐"
        player1_emote = "❌" if not is_dq else "🇩🇶"
    embed.description = f"Winner: <@{winner['id']}>\nFinished at {time}"
    embed.set_field_at(
        index=0,
        name=f"Players",
        value=f"{player1_emote} <@{player1_id}> vs <@{player2_id}> {player2_emote}",
        inline=False,
    )
    if len(embed.fields) > 1:
        # Remove dispute field
        embed.remove_field(2)
    embed.set_footer(
        text=f"Result finalized. To change result, contact a tournament manager.\nmatch_id: {match_id}"
    )
    embed.color = BLACK
    return embed


def create_repair_embed(interaction: Interaction, num_matches: int):
    user = interaction.user
    embed = Embed(
        title=f"👨‍⚕️ Match Medic! Fixed {num_matches} matches.", color=WOOP_PURPLE
    )
    embed.set_footer(
        text=f"{user.name}#{user.discriminator} used {full_command(interaction.command)}"
    )
    return embed


def create_reset_embed(interaction: Interaction, db_match: dict):
    match_id = db_match["id"]
    user = interaction.user
    embed = Embed(title=f"Match {match_id} has been reset.", color=WOOP_PURPLE)
    embed.set_footer(
        text=f"{user.name}#{user.discriminator} used {full_command(interaction.command)}"
    )
    return embed


def create_report_embed(interaction: Interaction, db_match: dict, db_winner: dict):
    match_id = db_match["id"]
    winner_id = db_winner["id"]
    winner_emote = db_match["winner_emote"]
    user = interaction.user
    embed = Embed(title=f"Match was overwritten.", color=WOOP_PURPLE)
    embed.add_field(name="Match ID", value=str(match_id))
    embed.add_field(name="Reported Winner", value=f"{winner_emote} <@{winner_id}>")
    embed.set_footer(
        text=f"{user.name}#{user.discriminator} used {full_command(interaction.command)}"
    )
    return embed


def get_round_name(db_tournament: dict, match_id: int, round: int):
    """
    Returns string value of round number based on number of rounds in a tournament.
    """
    num_rounds = db_tournament["num_rounds"]
    if round > 0:
        # Winners Bracket
        match num_rounds - round:
            case 0:
                if db_tournament["tournament_type"] == "double elimination":
                    try:
                        matches = challonge.matches.index(
                            db_tournament["challonge"]["id"]
                        )
                        matches.sort(reverse=True, key=(lambda match: match["id"]))
                        if match_id != matches[0]["id"]:
                            return "Grand Finals Set 1"
                        else:
                            return "Grand Finals Set 2"
                    except:
                        return "Grand Finals"
                else:
                    return "Grand Finals"
            case 1:
                return "Winners Finals"
            case 2:
                return "Winners Semifinals"
            case 3:
                return "Winners Quarterfinals"
            case _:
                return f"Winners Round {round}"
    else:
        # Losers Bracket
        match abs(num_rounds - round):
            case 0:
                return "Losers Finals"
            case 1:
                return "Losers Semiinals"
            case 2:
                return "Losers Quarterfinals"
            case _:
                return f"Losers Round {abs(round)}"
