from discord import Client, Message
from gridfs import Database
from logger import printlog
from pprint import pprint
import mdb
import re

# command.py
# $cmd custom commands

COMMANDS = 'commands'
PRESET_CMD = ['$cmd', '$info']

# Regex
specArg = re.compile(r'\$\{(\d?)\}') # ${[0, N)} 
specVar = re.compile(r'\$\{(\w*?)\}') # ['count', 'user', 'randInt', 'jmook', 'emote']

async def get_cmd(self, message: Message, db: Database, cmd_name: str):
    """
    Retrieves the specified command from the database.
    """
    try:
        cmd = await mdb.find_document(db, {"name": cmd_name}, COMMANDS)
    except:
        printlog(f"DB_ERROR: Failed to find command '{cmd_name}'.")
    # if not cmd:
    #     await message.channel.send(f"Command '{cmd_name}' not found.")
    return cmd

async def register_cmd(self, message, db: Database, argv: list, argc: int):
    """
    Registers a new command to the database. Can have special arguments specified.
    """
    usage = 'Usage: `$cmd <name> <text>`'
    # Error checking
    if argc < 3:
        return await message.channel.send(usage)

    cmd_name = argv[1]
    # Check if command already exists or in PRESET_CMD
    cmd = await mdb.find_document(db, {"name": cmd_name}, COMMANDS)
    if cmd or cmd_name in PRESET_CMD:
        return await message.channel.send(f"Command with name '{cmd_name}' already exists.")

    # Check if command name contains only alphanumeric characters
    # First character may be $
    valid = re.match('(^\$[\w-]+$)|(^[\w-]+$)', cmd_name) is not None
    if not valid:
        return await message.channel.send(f"Command with name '{cmd_name}' is invalid. Only alphanumeric characters and prefix '$' are allowed.")

    # Build command and add to collection   
    cmd_content = ' '.join(argv[2:]) # get cmd message
    cmd = {
        "name": cmd_name,
        "content": cmd_content,
        "author": { "username": message.author.name, "id": message.author.id },
        "argc": 0
    }

    # Check for ${} special variables
    cmd_specVar = specVar.search(cmd['content'])
    if cmd_specVar:
        match cmd_specVar.group():
            case '${count}':
                cmd.update({"count": 0})
            case _:
                pass

    # Check for numbered arguments
    cmd_specArg = specArg.findall(cmd['content'])
    if cmd_specArg:
        specArgc = len(cmd_specArg)
        missing = []
        for i in range(specArgc):
            if str(i) not in cmd_specArg: # Missing argument value
                missing.append(i)
        if len(missing) > 0:
            missing.sort()
            msg = "Failed to create new command. Invalid argument syntax. Missing number(s): "
            for i in range(len(missing)):
                if i != len(missing)-1:
                    msg += f"'{missing[i]}', "
                else:
                    msg += f"'{missing[i]}'."
            return await message.channel.send(msg)
        # Successfully parsed special arguments
        cmd["argc"] = specArgc + 1

    cmd_id = await mdb.add_document(db, cmd, COMMANDS)
    if cmd_id:
        msg = f"Created new command '{cmd_name}'."
        print(f"User '{message.author.name}' [id={message.author.id}] created new command '{cmd_name}'.")
    else:
        msg = "Failed to create new command."
    await message.channel.send(msg)
    return cmd

async def call_cmd(self, message, db: Database, argv: list, argc: int):
    """
    Checks if the message is a valid command in the database and sends a message with the command's content.
    """
    if message.author.bot or message.is_system() or len(argv) == 0:
        printlog("Detected bot or system message.")
        return
    cmd_name = argv[0]

    # Get command from database
    cmd = await get_cmd(self, message, db, cmd_name)
    if cmd:
        # Check argument count
        # Extra arguments don't matter / won't be printed
        diff = abs(argc-cmd["argc"]) + 1
        if argc < cmd["argc"]:
            return await message.channel.send(f"Missing {diff} argument(s).")

        # Print with arguments inserted
        # Replace each instance of ${n} one by one
        for i in range(argc-1):
            cmd["content"] = cmd["content"].replace(f"${{{i}}}", argv[i+1])

        # Print with counter
        if 'count' in cmd.keys():
            result = await mdb.update_single_document(db, {'name': cmd_name}, {'$inc': {'count': 1}}, COMMANDS)
            if result:
                print(f"Incremented count for command '{cmd_name}'.")
                new_count = str(cmd['count']+1)
                await message.channel.send(cmd["content"].replace(f'${{count}}', new_count))
            else: # Still print message on failure with non-updated count
                print(f"Failed to increment count for command '{cmd_name}'.")
                await message.channel.send(cmd["content"].replace('${count}', str(cmd['count'])))
        else: # Print normally
            await message.channel.send(cmd["content"])

async def delete_cmd(self, message, db: Database, argv: list, argc: int):
    """
    Deletes the specified command from the database.
    """
    usage = 'Usage: `$cmd delete <name>`'
    # Check num args
    if argc < 3:
        await message.channel.send(usage)
        return
    elif argc > 3:
        return await message.channel.send("Too many arguments.\n" + usage)

    cmd_name = argv[2]
    # Get command from database and delete
    result = await mdb.delete_document(db, {"name": cmd_name}, COMMANDS)
    # Command does not exist
    if result:
        await message.channel.send(f"Successfully deleted command '{cmd_name}'.")
    else:
        await message.channel.send(f"Failed to delete command '{cmd_name}'; Command does not exist.")

async def edit_cmd(self, message, db: Database, argv: list, argc: int):
    """
    Edits the content of the specified command.
    """
    usage = 'Usage: `$cmd edit <name> <text>`'
    cmd_content = ' '.join(argv[2:]) # get cmd message

    # Check num args
    if argc < 4:
        return await message.channel.send(usage)

    cmd_name = argv[1]
    # Get command from database and update
    cmd = await mdb.update_single_document(db, {"name": cmd_name}, {'$set': {'content': cmd_content}}, COMMANDS)
    # Command does not exist
    if cmd:
        msg = f"Successfully edited command '{cmd_name}'."
        await message.channel.send(msg)
    else:
        await message.channel.send(f"Failed to edit command '{cmd_name}'; Command does not exist.")