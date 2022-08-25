from cgi import print_exception
from datetime import datetime, timedelta, date
from discord import Client, Embed, Guild, Message, Member, RawReactionActionEvent, TextChannel
from dotenv import load_dotenv
from gridfs import Database
from logger import printlog, printlog_msg
from pprint import pprint
from traceback import print_exception
import challonge
import match as _match
import mdb
import os
import re
import requests

os.environ['path'] += os.getenv('CAIRO_PATH')
from cairosvg import svg2png # SVG to PNG

# bracket.py
# User created brackets

load_dotenv()

BRACKETS = 'brackets'
MATCHES = 'matches'
ICON = 'https://static-cdn.jtvnw.net/jtv_user_pictures/638055be-8ceb-413e-8972-bd10359b8556-profile_image-70x70.png'
IMGUR_CLIENT_ID = os.getenv('IMGUR_ID')
IMGUR_URL = 'https://api.imgur.com/3'
os.environ['path'] += r';C:\Program Files\UniConvertor-2.0rc5\dlls'

time_re_long = re.compile(r'([1-9]|0[1-9]|1[0-2]):[0-5][0-9] ([AaPp][Mm])$') # ex. 10:00 AM
time_re_short = re.compile(r'([1-9]|0[1-9]|1[0-2]) ([AaPp][Mm])$')           # ex. 10 PM

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
    try:
        bracket_challonge = challonge.tournaments.create(name="Test", url=None, tournament_type='double elimination', start_at=time, show_rounds=True, private=True, quick_advance=True, open_signup=False)
    except Exception as e:
        printlog("Failed to create challonge bracket ['].", e)

    new_bracket = {
        'name': bracket_name, 
        'message_id': None, 
        'jump_url': message.jump_url,
        'result_url': None,
        'author': {
            'username': message.author.name, 
            'id': message.author.id },
        'challonge': {
            'id': bracket_challonge['id'], 
            'url': bracket_challonge['full_challonge_url'] },
        'entrants': [], 
        'matches': [],
        'starttime': time, 
        'endtime': None, 
        'completed': False,
        'open': True,
        'num_rounds': None
    }
    
    # Send embed message
    embed = create_bracket_embed(new_bracket)
    bracket_message = await message.channel.send(embed=embed)
    # Add checkmark reaction to message
    try:
        await bracket_message.add_reaction('✅')
    except:
        pass

    # Add bracket to database
    new_bracket['message_id'] = bracket_message.id
    try:
        await mdb.add_document(db, new_bracket, BRACKETS)
    except:
        print(f"User '{message.author.name}' [id={message.author.id}] created new bracket '{bracket_name}'.")
    return (new_bracket, bracket_message, bracket_challonge)

async def delete_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Deletes the specified bracket from the database (if it exists).
    """
    # Fetch bracket
    usage = 'Usage: `$bracket delete [name]`'
    bracket, bracket_name = await parse_args(self, message, db, usage, argv, argc)
    retval = True
    if not bracket:
        return False
    # Only allow author or guild admins to delete bracket
    if message.author.id != bracket['author']['id'] or not message.author.guild_permissions.administrator:
        await message.channel.send(f"Only the author or server admins can delete brackets.")
        return False
    # Delete every match message and document associated with the bracket
    await delete_all_matches(self, message, db, bracket)
    # Delete bracket document
    try:
        result = await mdb.delete_document(db, {'name': bracket_name}, BRACKETS)
    except:
        print(f"Failed to delete bracket ['name'={bracket_name}].")
    # Delete bracket message
    try:
        bracket_message: Message = await message.channel.fetch_message(bracket['message_id'])
        await bracket_message.delete() # delete message from channel
    except:
        print(f"Failed to delete message for bracket '{bracket_name}' [id='{bracket['message_id']}']")
    if result:
        try:
            challonge.tournaments.destroy(bracket['challonge']['id']) # delete bracket from challonge
        except Exception as e:
            printlog(f"Failed to delete bracket [id='{bracket['message_id']}] from challonge [id='{bracket['challonge']['id']}].", e)
            retval = False
        print(f"User '{message.author.name}' [id={message.author.id}] deleted bracket '{bracket_name}'.")
        await message.channel.send(f"Successfully deleted bracket '{bracket_name}'.")
    else:
        await message.channel.send(f"Failed to delete bracket '{bracket_name}'.")
        retval = False
    return retval

async def update_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Updates the specified bracket in the database (if it exists).
    TODO
    """
    usage = 'Usage: `$bracket update [name]`'
    bracket, bracket_name = await parse_args(self, message, db, usage, argv, argc, send=False)
    if not bracket: 
        return False
    # Only allow author or guild admins to update bracket
    if message.author.id != bracket['author']['id'] or not message.author.guild_permissions.administrator:
        await message.channel.send(f"Only the author or server admins can update the bracket.")
        return False

async def start_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Starts a bracket created by the user.
    """
    # Fetch bracket
    usage = 'Usage: `$bracket start [name]`'
    bracket, bracket_name = await parse_args(self, message, db, usage, argv, argc)
    if not bracket: 
        return False
    # Only allow author or guild admins to start bracket
    if message.author.id != bracket['author']['id'] or not message.author.guild_permissions.administrator:
        await message.channel.send(f"Only the author or server admins can start the bracket.")
        return False
    # Check if already started
    if not bracket['open']:
        await message.channel.send(f"'{bracket_name}' has already been started.")
        return False
    # Make sure there are sufficient number of entrants
    if len(bracket['entrants']) < 2:
        await message.channel.send(f"Bracket must have at least 2 entrants before starting.")
        return False
    # Start bracket on challonge
    start_response = challonge.tournaments.start(bracket['challonge']['id'], include_participants=1, include_matches=1)
    print(f"Succesfully started bracket '{bracket_name}' [id={bracket['message_id']}].")
    # Get total number of rounds
    max_round = 0
    for match in start_response['matches']:
       round = match['match']['round']
       if round > max_round:
           max_round = round
    # Set bracket to closed in database and set total number of rounds
    updated_bracket = await mdb.update_single_document(db, {'message_id': bracket['message_id']}, {'$set': {'open': False, 'num_rounds': max_round }}, BRACKETS)
    # Send start message
    await message.channel.send(content=f"***{bracket_name}*** has now started!", reference=message) # Reply to original bracket message
    # Get each initial open matches
    matches = list(filter(lambda match: (match['match']['state'] == 'open'), start_response['matches']))
    for match in matches:
        try:
            await _match.add_match(self, message, db, updated_bracket, match['match'])
        except:
            print(f"Failed to add match ['match_id'='{match['match']['id']}'] to bracket ['name'='{bracket_name}']")
    # Update embed message
    await edit_bracket_message(self, updated_bracket, message.channel)
    return True

async def finalize_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Closes a bracket if completed.
    """
    # Fetch bracket
    usage = 'Usage: `$bracket finalize [name]`'
    completed_time = datetime.now()
    (bracket, bracket_name) = await parse_args(self, message, db, usage, argv, argc)
    if not bracket:
        return False
    # Only allow author or guild admins to finalize bracket
    if message.author.id != bracket['author']['id'] or not message.author.guild_permissions.administrator:
        await message.channel.send(f"Only the author or server admins can finalize the bracket.")
        return False
    # Check if already finalized
    if bracket['completed']:
        await message.channel.send(f"***{bracket_name}*** has already been finalized.")
        return False
    challonge_id = bracket['challonge']['id']
    # Finalize bracket on challonge
    try:
        final_bracket = challonge.tournaments.finalize(challonge_id, include_participants=1, include_matches=1)
    except Exception as e:
        printlog(f"Failed to finalize bracket on challonge ['name'='{bracket_name}'].", e)
        try: # Try and retrive bracket information instead of finalizing
            final_bracket = challonge.tournaments.show(challonge_id, include_participants=1, include_matches=1)
        except:
            print(f"Could not find bracket on challonge ['challonge_id'='{challonge_id}'].")
            return False
    # Create results message
    bracket_message = await message.channel.fetch_message(bracket['message_id'])
    bracket['completed'] = completed_time
    embed = create_results_embed(bracket, final_bracket['participants'])
    result_message = await message.channel.send(content=f"***{bracket_name}*** has been finalized. Here are the results!", reference=bracket_message, embed=embed) # Reply to original bracket message
    # Set bracket to completed in database
    try: 
        updated_bracket = await mdb.update_single_document(db, {'message_id': bracket['message_id']}, {'$set': {'completed': completed_time, 'result_url': result_message.jump_url}}, BRACKETS)
    except:
        print(f"Failed to update final bracket ['message_id'='{bracket['message_id']}'].")
        return False
    # Update embed message
    await edit_bracket_message(self, updated_bracket, message.channel)
    print(f"Finalized bracket '{bracket_name}' ['message_id'='{bracket['message_id']}'].")
    return True

async def send_results(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Sends the results message of a bracket that has been completed.
    """
    usage = 'Usage: `$bracket results <name>`'
    bracket, bracket_name = await parse_args(self, message, db, usage, argv, argc, send=False, completed=True)
    bracket_message_id = bracket['message_id']
    challonge_id = bracket['challonge']['id']

    # Check if bracket is completed
    if not bracket['completed']:
        await message.channel.send(f"***{bracket_name}*** has not yet been finalized.")
        return False

    # Retrive challonge bracket information
    try: 
        final_bracket = challonge.tournaments.show(challonge_id, include_participants=1, include_matches=1)
    except:
        print(f"Could not find bracket on challonge ['challonge_id'='{challonge_id}'].")
        return False
    # Create results message
    bracket_message = await message.channel.fetch_message(bracket_message_id)
    embed = create_results_embed(bracket, final_bracket['participants'])
    result_message = await message.channel.send(reference=bracket_message, embed=embed) # Reply to original bracket message
    return True

async def reset_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Resets a bracket if opened.
    """
    # Fetch bracket
    usage = 'Usage: `$bracket reset [name]`'
    bracket, bracket_name = await parse_args(self, message, db, usage, argv, argc, send=False)
    bracket_message_id = bracket['message_id']
    challonge_id = bracket['challonge']['id']
    if not bracket:
        return False
    # Only allow author or guild admins to finalize bracket
    if message.author.id != bracket['author']['id'] or not message.author.guild_permissions.administrator:
        await message.channel.send(f"Only the author or server admins can finalize the bracket.")
        return False
    # Check if already completed
    if bracket['completed']: 
        message.channel.send("Cannot reset a finalized bracket.")
        return False
    # Delete every match message and document associated with the bracket
    await delete_all_matches(self, message, db, bracket)
    # Reset bracket on challonge
    try:
        reset_bracket = challonge.tournaments.reset(challonge_id)
    except Exception as e:
        printlog(f"Something went wrong when resetting bracket ['name'='{bracket_name}'] on challonge.", e)
    # Set open to true and reset number of rounds
    updated_bracket = await mdb.update_single_document(db, {'message_id': bracket_message_id}, {'$set': {'open': True, 'num_rounds': None }}, BRACKETS)
    # Reset bracket message
    bracket_message = await message.channel.fetch_message(bracket_message_id)
    new_bracket_embed = create_bracket_embed(bracket)
    await bracket_message.edit(embed=new_bracket_embed)
    await message.channel.send(f"Successfully reset bracket '{bracket_name}'.")
    return True

######################
## HELPER FUNCTIONS ##
######################

async def parse_args(self: Client, message: Message, db: Database, usage: str, argv: list, argc: int, f_argc: int=2, send: bool=True, completed: bool=False):
    """"
    Parses arguments for bracket functions. Checks if there is a valid bracket.
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
        # Get most recently created bracket
        if completed:
            bracket = await mdb.find_most_recent_document(db, {}, BRACKETS)
        else:
            # Not completed
            bracket = await mdb.find_most_recent_document(db, {'completed': False}, BRACKETS)
        if not bracket:
            if send: await message.channel.send(f"There are currently no open brackets.")
            return (None, None)
        bracket_name = bracket['name']
    return (bracket, bracket_name)

async def delete_all_matches(self: Client, message: Message, db: Database, bracket):
    """
    Deletes all matches in the specified bracket.
    """
    bracket_name = bracket['name']
    retval = True
    for match in bracket['matches']:
        match_id = match['match_id']
        try:
            await _match.delete_match(self, message, db, bracket, match_id)
        except:
            print(f"Failed to delete match ['match_id'={match_id}] while deleting bracket ['name'={bracket_name}].")
            retval = False
    return retval

#######################
## MESSAGE FUNCTIONS ##
#######################

async def edit_bracket_message(self: Client, bracket, channel: TextChannel):
    """
    Edits bracket embed message in a channel.
    """
    bracket_name = bracket['name']
    bracket_message: Message = await channel.fetch_message(bracket['message_id'])
    embed = bracket_message.embeds[0]
    embed = update_embed_entrants(bracket, embed)
    if not bracket['open']:
        try:
            embed = create_bracket_image(bracket, embed)
        except Exception as e:
            printlog(f"Failed to create image for bracket ['name'='{bracket_name}'].", e)
        if not embed:
            printlog(f"Error when creating image for bracket ['name'='{bracket_name}'].", e)
    if bracket['completed']:
        time_str = bracket['completed'].strftime("%A, %B %d, %Y %#I:%M %p") # time w/o ms
        embed.set_footer(text=f'Completed: {time_str}')
        embed.set_author(name="Click Here to See Results", url=bracket['result_url'], icon_url=ICON)
    await bracket_message.edit(embed=embed)

def update_embed_entrants(bracket, embed: Embed):
    """
    Updates the entrants list in a bracket embed.
    """
    entrants = bracket['entrants']
    if len(entrants) > 0:
        entrants_content = ""
        for entrant in entrants:
            # To mention a user:
            # <@{user_id}>
            entrants_content += f"> <@{entrant['discord_id']}>\n"
    else:
        entrants_content = '> *None*'
    embed.set_field_at(1, name=f'Entrants ({len(entrants)})', value=entrants_content, inline=False)
    return embed

def create_bracket_image(bracket, embed: Embed):
    """
    Creates an image of the bracket.
    Converts the generated svg challonge image to png and uploads it to imgur.
    Discord does not support svg images in preview.
    """
    bracket_name = bracket['name']
    challonge_url = bracket['challonge']['url']
    if len(bracket['entrants']) >= 2:
        svg_url = f"{challonge_url}.svg"
        png_data = svg2png(url=svg_url) # Convert svg to png
        payload = {
            'image': png_data
        }
        headers = {
            'Authorization': f'Client-ID {IMGUR_CLIENT_ID}'
        }
        response = requests.request("POST", f"{IMGUR_URL}/image", headers=headers, data=payload, files=[])
        if response.status_code == requests.codes.ok:
            data = response.json()['data']
            image_link = data['link']
            embed.set_image(url=image_link)
            return embed
        else:
            printlog(f"Failed to create image for bracket ['name'='{bracket_name}'].")
            return False
    else:
        printlog(f"Failed to create image for bracket ['name'='{bracket_name}'].")
        return False

def create_bracket_embed(bracket):
    """
    Creates embed object to include in bracket message.
    """
    author_name = bracket['author']['username']
    bracket_name = bracket['name']
    challonge_url = bracket['challonge']['url']
    time = bracket['starttime']
    
    # Check the status
    if bracket['completed']:
        status = "Completed 🏁"
    elif bracket['open']:
        status = "🚨 Open for Registration 🚨"
    else:
        status = "Started 🟩"

    embed = Embed(title=f'🥊  {bracket_name}', description=f"Status:  {status}", color=0x6A0DAD)
    embed.set_author(name="beta-bot | GitHub 🤖", url="https://github.com/fborja44/beta-bot", icon_url=ICON)
    time_str = time.strftime("%A, %B %d, %Y %#I:%M %p") # time w/o ms
    embed.add_field(name='Starting At', value=time_str, inline=False)
    # Entrants list
    embed.add_field(name='Entrants (0)', value="> *None*", inline=False)
    embed = update_embed_entrants(bracket, embed)
    embed.add_field(name=f'Bracket Link', value=challonge_url, inline=False)
    embed.set_footer(text=f'React with ✅ to enter! | Created by {author_name}')
    return embed

def create_results_embed(bracket, entrants: list):
    """
    Creates embed object with final results to include after finalizing bracket.
    """
    bracket_name = bracket['name']
    challonge_url = bracket['challonge']['url']
    jump_url = bracket['jump_url']
    embed = Embed(title='🏆  Final Results', color=0xFAD25A)
    embed.set_author(name=bracket_name, url=jump_url, icon_url=ICON)
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
                results_content += f"> **{entrant['final_rank']}.** {entrant['name']}"
    embed.add_field(name=f'Placements', value=results_content, inline=False)
    embed.add_field(name=f'Bracket Link', value=challonge_url, inline=False)
    time_str = bracket['completed'].strftime("%A, %B %d, %Y %#I:%M %p") # time w/o ms
    embed.set_footer(text=f'Completed: {time_str}')
    return embed

#######################
## ENTRANT FUNCTIONS ##
#######################

async def update_bracket_entrants(self: Client, payload: RawReactionActionEvent, db: Database):
    """
    Adds or removes an entrant from a bracket based on whether the reaction was added or removed.
    """
    # Check if message reacted to is in brackets and is open
    bracket = await mdb.find_document(db, {'message_id': payload.message_id}, BRACKETS)
    guild = self.get_guild(payload.guild_id)
    channel = await guild.get_channel(payload.channel_id)
    if not bracket or not bracket['open']:
        # Do not respond
        return False 
    if payload.event_type=='REACTION_ADD':
        await add_entrant(self, db, bracket, payload.member, channel)
    elif payload.event_type=='REACTION_REMOVE':
        guild: Guild = await self.get_guild(payload.guild_id)
        member = await guild.get_member(payload.user_id)
        await remove_entrant(self, db, bracket, member, channel)
    return True

async def add_entrant(self: Client, db: Database, bracket, member: Member, channel: TextChannel):
    """
    Adds an entrant to a bracket.
    """
    bracket_name = bracket['name']
    bracket_entrants = [] # list of entrant names
    map(lambda entrant: bracket_entrants.append(entrant['name']), bracket['entrants'])
    challonge_id = bracket['challonge']['id']
    # Add user to challonge bracket
    try:
        response = challonge.participants.create(challonge_id, member.name)
    except Exception as e:
        printlog(f"Failed to add user ['name'='{member.name}'] to challonge bracket. User may already exist.", e)
    # Check if already in entrants list
    if member.name in bracket_entrants:
        printlog(f"User ['name'='{member.name}']' is already registered as an entrant in bracket ['name'='{bracket_name}'].")
        return False
    # Add user to entrants list
    entrant = {
        'name': member.name, 
        'discord_id': member.id, 
        'challonge_id': response['id'],
        'placement': None,
        'active': True
        }
    try:
        updated_bracket = await mdb.update_single_document(db, {'name': bracket_name}, {'$push': {'entrants': entrant}}, BRACKETS)
    except:
        print(f"Failed to add user '{member.name}' to bracket ['name'='{bracket_name}'] entrants.")
        return False
    if updated_bracket:
        print(f"Added entrant '{member.name}' [id='{member.id}'] to bracket ['name'='{bracket_name}'].")
        # Update message
        await edit_bracket_message(self, updated_bracket, channel)
    else:
        print(f"Failed to add entrant '{member.name}' [id='{member.id}'] to bracket ['name'='{bracket_name}'].")
        return False
    return True

async def remove_entrant(self: Client, db: Database, bracket, member: Member, channel: TextChannel):
    """
    Destroys an entrant from a tournament or DQs them if the tournament has already started.
    """
    # Remove user from challonge bracket
    bracket_name = bracket['name']
    bracket_entrants = [] # list of entrant names
    map(lambda entrant: bracket_entrants.append(entrant['name']), bracket['entrants'])
    challonge_id = bracket['challonge']['id']
    entrant = list(filter(lambda entrant: (entrant['discord_id'] == member.id), bracket['entrants']))[0]
    message_id = bracket['message_id']
    try:
        response = challonge.participants.destroy(challonge_id, entrant['challonge_id'])
    except Exception as e:
        printlog(f"Failed to remove user ['name'='{member.name}'] from challonge bracket. User may not exist.", e)
    # Check if already in entrants list
    if member.name not in bracket_entrants:
        printlog(f"User ['name'='{member.name}']' is not registered as an entrant in bracket ['name'='{bracket_name}'].")
        return False
    # Remove user from entrants list
    try:
        updated_bracket = await mdb.update_single_document(db, {'message_id': message_id}, {'$pull': {'entrants': {'discord_id': member.id }}}, BRACKETS)
    except:
        print(f"Failed to remove user '{member.name}' from bracket ['name'='{bracket_name}'] entrants.")
        return False
    if updated_bracket:
        print(f"Removed entrant [id='{member.id}'] from bracket [id='{message_id}'].")
        # Update message
        await edit_bracket_message(self, updated_bracket, channel)
    else:
        print(f"Failed to remove entrant [id='{member.id}'] from bracket [id='{message_id}'].")

async def disqualify_entrant_main(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Destroys an entrant from a tournament or DQs them if the tournament has already started from a command.
    Main function.
    """
    usage = 'Usage: `$bracket dq <entrant name>`. Must be in a reply to a bracket or match.'
    if argc < 3 or not message.reference:
        await message.channel.send(usage)
        return False
    entrant_name = ' '.join(argv[2:])

    reply_message = await message.channel.fetch_message(message.reference.message_id)
    # Check if replying to a bracket message
    try:
        bracket = await mdb.find_document(db, {'message_id': reply_message.id}, BRACKETS)
    except:
        return False
    if bracket:
        return await disqualify_entrant_bracket(self, message, db, bracket, entrant_name)

    # Check if replying to match message
    try:
        match = await mdb.find_document(db, {'message_id': reply_message.id}, MATCHES)
    except:
        return False
    if match:
        return await _match.disqualify_entrant_match(self, message, db, match, entrant_name)
    await message.channel.send("DQ must be in reply to a bracket or match message.")
    return False

async def disqualify_entrant_bracket(self: Client, message: Message, db: Database, bracket, entrant_name: str):
    """
    Destroys an entrant from a tournament or DQs them if the tournament has already started from a command.
    Bracket version.
    """
    bracket_name = bracket['name']
    # Check if entrant exists
    entrant = None
    for elem in bracket['entrants']:
        if elem['name'].lower() == entrant_name.lower():
            entrant = elem
    if not entrant:
        printlog(f"User ['name'='{entrant_name}']' is not an entrant in bracket ['name'='{bracket_name}'].")
        await message.channel.send(f"There is no entrant named '{entrant_name}' in ***{bracket_name}***.")
        return False
    elif not entrant['active']:
        await message.channel.send(f"Entrant '{entrant_name}' has already been disqualified from ***{bracket_name}***.")
        return False

    # Call dq helper function
    return await disqualify_entrant(self, message, db, bracket, entrant)

async def disqualify_entrant(self: Client, message: Message, db: Database, bracket, entrant):
    """
    Function to dq an entrant in the database and challonge.
    """
    bracket_name = bracket['name']
    challonge_id = bracket['challonge']['id']
    entrant_name = entrant['name']
    entrant['active'] = False
    # Update entrant in database
    try:
        await mdb.update_single_document(db, {'name': bracket_name, "entrants.name": entrant['name']}, {'$set': {'active': True}}, BRACKETS)
    except:
        print("Failed to DQ entrant in database.")
        return False
    # Disqualify entrant on challonge
    try:
        challonge.participants.destroy(challonge_id, entrant['challonge_id'])
    except Exception as e:
        printlog(f"Failed to DQ entrant ['name'='{entrant_name}'] from bracket ['name'='{bracket_name}']", e)
        return False

    # Update all open matches
    winner_emote = None
    for bracket_match in bracket['matches']:
        # Get match document
        match = await _match.get_match(self, db, bracket_match['match_id'])
        # Check if match is open
        if match['completed']:
            continue
        # Check the players; Other player wins
        if entrant_name == match['player1']['name']:
            winner_emote = '2️⃣'
            break
        elif entrant_name == match['player2']['name']:
            winner_emote = '1️⃣'
            break
    if winner_emote:
        # Report match
        match_message = await message.channel.fetch_message(match['message_id'])
        await _match.report_match(self, match_message, db, bracket, match, winner_emote, is_dq=True)
    return True

#######################
## TESTING FUNCTIONS ##
#######################

async def create_test_bracket(self: Client, message: Message, db: Database, argv: list, argc: int):
    """
    Testing function. Creates a test bracket and adds two entrants.
    """
    printlog("Creating test bracket...")
    bracket_name = "Test Bracket"
    bracket_db , bracket_message , bracket_challonge = None, None, None
    
    # Only allow guild admins to create a test bracket
    if not message.author.guild_permissions.administrator:
        return await message.channel.send(f"Only admins can create a test bracket.")

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
        await add_entrant(self, db, bracket_db, member1, message.channel)
        # Add second entrant
        member2 = message.guild.get_member_named("pika!#3722")
        await add_entrant(self, db, bracket_db, member2, message.channel)
        # Add third entrant
        member3 = message.guild.get_member_named("Wooper#0478")
        await add_entrant(self, db, bracket_db, member3, message.channel)
        # Add fourth entrant
        member4 = message.guild.get_member_named("WOOPBOT#4140")
        await add_entrant(self, db, bracket_db, member4, message.channel)
        return True
    except Exception as e:
        await printlog_msg("Failed to create test bracket.", "Something went wrong when creating the bracket.", message.channel)
        print_exception(e)
        if bracket_message:
            argv = ["$bracket", "delete", bracket_name]
            await delete_bracket(self, message, db, argv, len(argv))
        return False