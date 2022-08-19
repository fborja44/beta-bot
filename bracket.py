from cgi import print_exception
from datetime import datetime, timedelta, date
from discord import Client, Embed, Message, Member, RawReactionActionEvent, TextChannel
from gridfs import Database
from logger import printlog, printlog_message
from pprint import pprint
from traceback import print_exception
import challonge
import match as _match
import mdb
import re

# bracket.py
# User created brackets

# Challonge API: https://api.challonge.com/v1

BRACKETS = 'brackets'
BASE_URL = 'https://api.challonge.com/v2'

time_re_long = re.compile(r'([1-9]|0[1-9]|1[0-2]):[0-5][0-9] ([AaPp][Mm])$') # ex. 10:00 AM
time_re_short = re.compile(r'([1-9]|0[1-9]|1[0-2]) ([AaPp][Mm])$')           # ex. 10 PM

async def parse_args(self: Client, message: Message, db: Database, usage: str, argv: list, argc: int, f_argc: int = 2, send: bool = True):
    """"
    Parses arguments for bracket functions.
    """
    if argc < f_argc:
        return await message.channel.send(usage)
    # Get bracket from database
    if argc >= f_argc + 1:
        bracket_name = ' '.join(argv[2:]) # Get bracket name
        # Check if bracket exists
        bracket = await get_bracket(self, db, bracket_name)
        if not bracket:
            if send: await message.channel.send(f"Bracket with name '{bracket_name}' does not exist.")
            return (None, None)
    elif argc < f_argc + 1:
        # Get most recent bracket that has not yet been completed
        bracket = await mdb.find_most_recent_document(db, {'completed': False}, BRACKETS)
        if not bracket:
            if send: await message.channel.send(f"There are currently no open brackets.")
            return (None, None)
        bracket_name = bracket['name']
    return (bracket, bracket_name)

def create_bracket_embed(bracket_name: str, author, time: datetime, url: str, entrants: list=[], status: str="Open for Registration  🚨"):
    """
    Creates embed object to include in bracket message.
    """
    embed = Embed(title=f'🥊  {bracket_name}', description=f"Status:  {status}", color=0x6A0DAD)
    time_str = time.strftime("%A, %B %d, %Y %#I:%M %p") # time w/o ms
    embed.add_field(name='Starting At', value=time_str, inline=False)
    if len(entrants) > 0:
        entrants_content = ""
        for entrant in entrants:
            # To mention a user:
            # <@{user_id}>
            entrants_content += f"> <@{entrant['discord_id']}>\n"
    else:
        entrants_content = '> *None*'
    embed.add_field(name=f'Entrants ({len(entrants)})', value=entrants_content, inline=False)
    embed.add_field(name=f'Bracket Link', value=url, inline=False)
    embed.set_footer(text=f'React with ✅ to enter! | Created by {author}')
    return embed

def create_results_embed(bracket_name: str, url: str, entrants: list):
    """
    Creates embed object with final results to include after finalizing bracket.
    """
    embed = Embed(title=f'🏆  *{bracket_name}* Final Results')
    results_content = ""
    entrants.sort(key=(lambda entrant: entrant['participant']['final_rank']))
    for i in range (min(len(entrants), 8)):
        entrant = entrants[i]['participant']
        match entrant['final_rank']:
            case 1:
                results_content += f"> 🥇  {entrant['name']}\n"
            case 2:
                results_content += f"> 🥈  {entrant['name']}\n"
            case 3:
                results_content += f"> 🥉  {entrant['name']}\n"
            case _:
                results_content += f"{entrant['final_rank']}. {entrant['name']}"
    embed.add_field(name=f'Placements', value=results_content, inline=False)
    embed.add_field(name=f'Bracket Link', value=url, inline=False)
    time_str = datetime.now().strftime("%A, %B %d, %Y %#I:%M %p") # time w/o ms
    embed.set_footer(text=f'Completed: {time_str}')
    return embed

async def get_bracket(self: Client, db: Database, bracket_name: str):
    """
    Retrieves and returns a bracket document from the database (if it exists).
    """
    return await mdb.find_document(db, {"name": bracket_name}, BRACKETS)

async def add_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Adds a new bracket document to the database.
    """
    usage = 'Usage: `$bracket create <name> [time]`'
    if argc < 3:
        return await message.channel.send(usage)

    # Parse time; Default is 1 hour from current time
    match1 = time_re_long.search(message.content.strip()) # Check for long time
    match2 = time_re_short.search(message.content.strip()) # Check for short time
    if not match1 and not match2:
        time = datetime.now() + timedelta(hours=1)
        match = None
    else:
        current_time = datetime.now()
        if match1:
            match = match1.span()
            time = datetime.strptime(f'{date.today()} {match1.group()}', '%Y-%m-%d %I:%M %p')
        elif match2:
            match = match2.span()
            time = datetime.strptime(f'{date.today()} {match2.group()}', '%Y-%m-%d %I %p')
        # Check if current time is before time on current date; If so, go to next day
        if current_time > time:
            time += timedelta(days=1)

    # Get bracket name
    if match:
        argv = message.content[:match[0]].split()
    bracket_name = ' '.join(argv[2:]) 
    # Max character length == 60
    if len(bracket_name.strip()) > 60:
        return await message.channel.send(f"Bracket name can be no longer than 60 characters.")
    # Check if bracket already exists
    bracket = await get_bracket(self, db, bracket_name)
    if bracket:
        return await message.channel.send(f"Bracket with name '{bracket_name}' already exists.")

    # Create challonge bracket
    bracket_challonge = challonge.tournaments.create(name="Test", url=None, tournament_type='double elimination', start_at=time, show_rounds=True, private=True, quick_advance=True, open_signup=False)
    # Send embed message
    embed = create_bracket_embed(bracket_name, message.author.name, time, bracket_challonge['full_challonge_url'])
    bracket_message = await message.channel.send(embed=embed)
    # Add checkmark reaction to message
    await bracket_message.add_reaction('✅')
    # Add bracket to DB
    bracket = {
        'name': bracket_name, 
        'message_id': bracket_message.id, 
        'jump_url': message.jump_url,
        'author': {'username': message.author.name, 'id': message.author.id},
        'challonge': {'id': bracket_challonge['id'], 'url': bracket_challonge['full_challonge_url']},
        'entrants': [], 
        'matches': [],
        'starttime': time, 
        'endtime': None, 
        'completed': False,
        'open': True,
        'num_rounds': None
    }
    if await mdb.add_document(db, bracket, BRACKETS):
        print(f"User '{message.author.name}' [id={message.author.id}] created new bracket '{bracket_name}'.")
    
    return (bracket, bracket_message, bracket_challonge)
    # TODO: Cleanup if anything fails (delete db entry, delete message, delete challonge bracket)

async def delete_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Deletes the specified bracket from the database (if it exists).
    """
    usage = 'Usage: `$bracket delete [name]`'
    bracket, bracket_name = await parse_args(self, message, db, usage, argv, argc)
    if not bracket: return
    # Only allow author to delete bracket
    if message.author.id != bracket['author']['id']:
        return await message.channel.send(f"Only the author can delete the bracket.")
    
    # Delete every match message and document associated with the bracket
    for match in bracket['matches']:
        match['match_id']
        await _match.delete_match(self, db, match['match_id'], match['message_id'], message.channel.id)

    result = await mdb.delete_document(db, {'name': bracket_name}, BRACKETS)
    try:
        bracket_message = await message.channel.fetch_message(bracket['message_id'])
        await bracket_message.delete() # delete message from channel
    except:
        print(f"Failed to delete message for bracket '{bracket_name}' [id='{bracket['message_id']}']")
    if result:
        try:
            challonge.tournaments.destroy(bracket['challonge']['id']) # delete bracket from challonge
        except:
            print(f"Failed to delete bracket [id='{bracket['message_id']}] from challonge [id='{bracket['challonge_id']}].")
        print(f"User '{message.author.name}' [id={message.author.id}] deleted bracket '{bracket_name}'.")
        await message.channel.send(f"Successfully deleted bracket '{bracket_name}'.")
    else:
        await message.channel.send(f"Failed to delete bracket '{bracket_name}'.")

async def update_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Updates the specified bracket in the database (if it exists).

    TODO
    """
    usage = 'Usage: `$bracket update [name]`'
    bracket, bracket_name = await parse_args(self, message, db, usage, argv, argc, send=False)
    if not bracket: return

async def update_bracket_entrants(self: Client, payload: RawReactionActionEvent, db: Database):
    """
    Adds or removes an entrant from a bracket based on whether the reaction was added or removed.
    """
    # Check if message reacted to is in brackets and is open
    bracket = await mdb.find_document(db, {'message_id': payload.message_id}, BRACKETS)
    channel = self.get_channel(payload.channel_id)
    if not bracket or not bracket['open']:
        return # Do not respond
    if payload.event_type=='REACTION_ADD':
        await add_entrant(self, db, bracket, payload.message_id, payload.channel_id, payload.member)
    elif payload.event_type=='REACTION_REMOVE':
        await remove_entrant(self, db, bracket, payload.message_id, payload.user_id, payload.channel_id)
    
async def edit_bracket_message(self: Client, bracket, channel: TextChannel, status='🚨  Open for Registration 🚨'):
    """
    Edits bracket embed message in a channel.
    """
    message = await channel.fetch_message(bracket['message_id'])
    
    embed = create_bracket_embed(bracket['name'], bracket['author']['username'], bracket['starttime'], bracket['challonge']['url'], bracket['entrants'], status)
    await message.edit(embed=embed)

async def start_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Starts a bracket created by the user.
    """
    usage = 'Usage: `$bracket start [name]`'
    bracket, bracket_name = await parse_args(self, message, db, usage, argv, argc)
    if not bracket: return
    # Make sure there are sufficient number of entrants
    if len(bracket['entrants']) < 2:
        return await message.channel.send(f"Bracket must have at least 2 entrants before starting.")
    # Start bracket on challonge
    create_response = challonge.tournaments.start(bracket['challonge']['id'], include_participants=1, include_matches=1)
    print(f"Succesfully started bracket '{bracket_name}' [id={bracket['message_id']}].")

    # Get total number of rounds
    max_round = 0
    for match in create_response['matches']:
       round = match['match']['round']
       if round > max_round:
           max_round = round
    # Set bracket to closed in database and set total number of rounds
    updated_bracket = await mdb.update_single_field(db, {'message_id': bracket['message_id']}, {'$set': {'open': False, 'num_rounds': max_round }}, BRACKETS)
    # Send messages for each of the initial open matches
    matches = list(filter(lambda match: (match['match']['state'] == 'open'), create_response['matches']))
    for match in matches:
       await _match.add_match(self, message, db, updated_bracket, match['match'])
    # Update embed message
    await edit_bracket_message(self, updated_bracket, message.channel, status='Started 🟩')
    await message.channel.send(content=f"**{bracket_name}** has now started!", reference=message) # Reply to original bracket message
    return True

async def finalize_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Closes a bracket if completed.
    """
    usage = 'Usage: `$bracket finalize [name]`'
    bracket, bracket_name = await parse_args(self, message, db, usage, argv, argc)
    if not bracket: return
    # Finalize bracket on challonge
    # TODO: Update function based on return value
    final_bracket = challonge.tournaments.finalize(bracket['challonge']['id'], include_participants=1, include_matches=1)
     # Set bracket to completed in database
    updated_bracket = await mdb.update_single_field(db, {'message_id': bracket['message_id']}, {'$set': {'completed': True}}, BRACKETS)
    # Update embed message
    await edit_bracket_message(self, updated_bracket, message.channel, status='Completed 🏁')
    print(f"Finalized bracket '{bracket_name}' [id={bracket['message_id']}].")

    message = await message.channel.fetch_message(bracket['message_id'])
    embed = create_results_embed(updated_bracket['name'], bracket['challonge']['url'], final_bracket['participants'])
    await message.channel.send(content=f"***{bracket_name}*** has been finalized. Here are the results!", reference=message, embed=embed) # Reply to original bracket message
    return True

async def reset_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Resets a bracket if opened.
    """
    usage = 'Usage: `$bracket reset [name]`'
    bracket, bracket_name = await parse_args(self, message, db, usage, argv, argc, send=False)
    if not bracket: return

async def create_test_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Testing function. Creates a test bracket and adds two entrants.
    """
    printlog("Creating test bracket...")
    bracket_name = "Test Bracket"
    bracket_db , bracket_message , bracket_challonge = None, None, None
    # Delete previous test bracket if it exists
    try:
        bracket = await get_bracket(self, db, bracket_name)
        if bracket:
            argv = ["$bracket", "delete", bracket_name]
            await delete_bracket(self, message, db, argv, len(argv))
        # Call add_bracket
        argv = ["$bracket", "create", bracket_name]
        bracket_db, bracket_message, bracket_challonge = await add_bracket(self, message, db, argv, len(argv))
        
        # Add first entrant
        member1 = message.guild.get_member_named('beta#3096')
        await add_entrant(self, db, bracket_db, message.id, message.channel, member1)
        # Add second entrant
        member2 = message.guild.get_member_named("pika!#3722")
        await add_entrant(self, db, bracket_db, message.id, message.channel, member2)
    except Exception as e:
        await printlog_message("Failed to create test bracket.", "Something went wrong when creating the bracket.", message)
        print_exception(e)
        if bracket_message:
            argv = ["$bracket", "delete", bracket_name]
            await delete_bracket(self, message, db, argv, len(argv))

async def add_entrant(self: Client, db: Database, bracket, message_id: int, channel: TextChannel, member: Member):
    """
    Adds an entrant to a bracket.
    """
    # TODO: Check if user is already in challonge bracket or in entrants list
    # Add user to challonge bracket
    response = challonge.participants.create(bracket['challonge']['id'], member.name)
    # Add user to entrants list
    entrant = {'name': member.name, 'discord_id': member.id, 'challonge_id': response['id']}
    updated_bracket = await mdb.update_single_field(db, {'name': bracket['name']}, {'$push': {'entrants': entrant}}, BRACKETS)
    if updated_bracket:
        print(f"Added entrant '{member.name}' [id='{member.id}'] to bracket [id='{message_id}'].")
        # Update message
        await edit_bracket_message(self, updated_bracket, channel)
    else:
        print(f"Failed to add entrant '{member.name}' [id='{member.id}'] to bracket [id='{message_id}'].")

async def remove_entrant(self: Client, db: Database, bracket, message_id: int, member_id: int, channel: TextChannel):
    """
    Destroys an entrant from a tournament or DQs them if the tournament has already started.
    """
    # TODO: Check if user is in challonge bracket and in entrants list
    # Remove user from challonge bracket
    entrant = list(filter(lambda entrant: (entrant['discord_id'] == member_id), bracket['entrants']))[0]
    response = challonge.participants.destroy(bracket['challonge']['id'], entrant['challonge_id'])
    # Remove user from entrants list
    updated_bracket = await mdb.update_single_field(db, {'message_id': message_id}, {'$pull': {'entrants': {'discord_id': member_id }}}, BRACKETS)
    if updated_bracket:
        print(f"Removed entrant [id='{member_id}'] from bracket [id='{message_id}'].")
        # Update message
        await edit_bracket_message(self, updated_bracket, channel)
    else:
        print(f"Failed to remove entrant [id='{member_id}'] from bracket [id='{message_id}'].")