import discord
import pymongo
import re
import mdb

from pprint import pprint

# command.py
# $cmd custom commands

COMMANDS = 'commands'
PRESET_CMD = ['$cmd', '$delcmd', '$editcmd', '$info']

# Regex
specArg = re.compile(r'\$\{(\d?)\}') # ${[0, N)} 
specVar = re.compile(r'\$\{(\w*?)\}') # ['count', 'user', 'randInt', 'jmook', 'emote']

async def get_cmd(self, message, db, cmd_name):
    try:
        cmd = await mdb.find_document(db, {"name": cmd_name}, COMMANDS)
    except:
        await message.channel.send("Failed to find command '{0}'.".format(cmd_name))
    if not cmd:
        await message.channel.send("Command '{0}' not found.".format(cmd_name))
    return cmd

async def register_cmd(self, message, db):
    usage = 'Usage: `$cmd <name> <text>`'
    cmd_arr = message.content.split()

    # Error checking
    if len(cmd_arr) < 3:
        await message.channel.send(usage)
        return

    cmd_name = cmd_arr[1]

    # Check if command already exists or in PRESET_CMD
    cmd = await mdb.find_document(db,"name", cmd_name, COMMANDS)
    if cmd or cmd_name in PRESET_CMD:
        await message.channel.send("Command with name '{0}' already exists.".format(cmd_name))
        return

    # Check if command name contains only alphanumeric characters
    # First character may be $
    valid = re.match('(^\$[\w-]+$)|(^[\w-]+$)', cmd_name) is not None
    if not valid:
        await message.channel.send("Command with name '{0}' is invalid. Only alphanumeric characters and prefix '$' are allowed.".format(cmd_name))
        return

    # Build command and add to collection   
    cmd_content = ' '.join(cmd_arr[2:]) # get cmd message
    cmd = {"name": cmd_name,
        "content": cmd_content,
        "author": { "username": message.author.name, "id": message.author.id },
        "argc": 0}

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
                    msg += "'{0}', ".format(missing[i])
                else:
                    msg += "'{0}'.".format(missing[i])
            await message.channel.send(msg)
            return
        # Successfully parsed special arguments
        cmd["argc"] = specArgc

    cmd_id = await mdb.add_document(db, cmd, COMMANDS)
    if cmd_id:
        msg = "Created new command '{0}' with content '{1}'.".format(cmd_name, cmd_content)
    else:
        msg = "Failed to create new command."
    await message.channel.send(msg)

async def call_cmd(self, message, db):
    cmd_arr = message.content.split()
    if message.author.bot or len(cmd_arr) == 0:
        # print("Detected bot or system message.")
        return
    cmd_name = cmd_arr[0]
    argc = len(cmd_arr) - 1
    argv = cmd_arr[1:]

    # Get command from database
    cmd = await get_cmd(self, message, db, cmd_name)
    if cmd:
        # Check argument count
        # Extra arguments don't matter / won't be printed
        if argc < cmd["argc"]:
            await message.channel.send("Missing {0} argument(s).".format(abs(argc-cmd["argc"])))
            return

        # Print with arguments inserted
        # Replace each instance of ${n} one by one
        for i in range(argc):
            cmd["content"] = cmd["content"].replace("${{{0}}}".format(str(i)), argv[i])

        # Print with counter
        if 'count' in cmd.keys():
            result = mdb.update_single_field(db, {'name': cmd_name}, {'$inc': {'count': 1}}, COMMANDS)
            if result:
                print("Incremented count for command '{0}'.".format(cmd_name))
                await message.channel.send(cmd["content"].replace('${count}', str(cmd['count']+1)))
            else: # Still print message on failure with non-updated count
                print("Failed to increment count for command '{0}'.".format(cmd_name))
                await message.channel.send(cmd["content"].replace('${count}', str(cmd['count'])))
        else: # Print normally
            await message.channel.send(cmd["content"])

async def delete_cmd(self, message, db):
    usage = 'Usage: `$delcmd <name>`'
    cmd_arr = message.content.split()

    # Check num args
    argc = len(cmd_arr) - 1
    if argc < 1:
        await message.channel.send(usage)
        return
    elif argc > 1:
        await message.channel.send("Too many arguments.\n" + usage)
        return

    cmd_name = cmd_arr[1]
    # Get command from database and delete
    result = await mdb.delete_document(db, {"name": cmd_name}, COMMANDS)
    # Command does not exist
    if result:
        await message.channel.send(msg = "Successfully deleted command '{0}'.".format(cmd_name))
    else:
        await message.channel.send("Failed to delete command '{0}'; Command does not exist.".format(cmd_name))

async def edit_cmd(self, message, db):
    usage = 'Usage: `$editcmd <name> <text>`'
    cmd_arr = message.content.split()
    cmd_content = ' '.join(cmd_arr[2:]) # get cmd message

    # Check num args
    argc = len(cmd_arr) - 1
    if argc < 2:
        await message.channel.send(usage)
        return

    cmd_name = cmd_arr[1]
    # Get command from database and update
    cmd = await mdb.update_single_field(db, {"name": cmd_name}, {'$set': {'content': cmd_content}}, COMMANDS)
    # Command does not exist
    if cmd:
        msg = "Successfully edited command '{0}'.".format(cmd_name)
        await message.channel.send(msg)
    else:
        await message.channel.send("Failed to edit command '{0}'; Command does not exist.".format(cmd_name))