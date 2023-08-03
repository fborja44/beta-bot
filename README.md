# **beta-bot**
**beta-bot** is an interactive discord bot using the [discord.py](https://discordpy.readthedocs.io/en/stable/) [2.0] library to create and administrate tournaments through Discord text channels using the [Discord API](https://discord.com/developers/docs/intro).

Tournaments are generated using the [Challonge.com API](https://api.challonge.com/v1). bracket images are created and hosted on imgur using the [Imgur API](https://apidocs.imgur.com/).

All data is stored using MongoDB through the [PyMongo](https://pymongo.readthedocs.io/en/stable/) library.

## Links
- Challonge.com API: https://api.challonge.com/v1
- Discord API: https://discord.com/developers/docs/intro
- discord.py: https://discordpy.readthedocs.io/en/stable/
- Imgur API: https://apidocs.imgur.com/
- PyMongo: https://pymongo.readthedocs.io/en/stable/

## Commands
All commands use the `/` prefix and `/slash command` feature of Discord for help with validation, error handling, and parameter autofill/documentation.

## Permissions
**beta-bot** requires thread permissions and `members` intents to operate properly. All tournaments generated are created as messages. If these permissions are not given, tournaments will not be able to be created. This is to improve organization and avoid unnecessary spam in Discord text channels.

### Tournament Brackets
Tournaments must be created in text channels. Tournaments cannot be created in threads or forum channels.

#### Help
`/bracket help`
- Sends a list of tournament commands.

#### Create
`/bracket create <title: str> [time: str] [single_elim: bool] [max_entrants: int]`:
- Creates a new tournament with the provided name and time. Times in ET.
- Default start time is 1 hour ahead of the time of creation.
- ex. time: `10 PM` or `10:00 PM`.
- Max length of `title` is 60 characters.
- `max_entrants` must be between 4 and 24.

#### Join
`/bracket join [title: str]`:
- Adds the user to the specified tournament. 
- Must be sent in a tournament thread.

#### Leave
`/bracket delete [title: str]`:
- Deletes the specified tournament. 
- Must be sent in a tournament thread.

#### Delete
`/bracket delete [title: str]`:
- Deletes the specified tournament. 
- If `title` is not provided, targets the subject tournament in the thread.

#### Update
`/bracket update <title: str> [new_title: str] [time: str] [single_elim: bool] [max_entrants: int]`:
- Updates the specified tournament using the provided information. Times in ET.
- ex. time: `10 PM` or `10:00 PM`.
- Max length of title is 60 characters.
- `max_entrants` must be between 4 and 24.

#### Start
`/bracket start [title: str]`:
- Starts the specified tournament if in the registration phase. 
- If `title` is not provided, targets the subject tournament in the thread.
- Only one tournament may be active per server.

#### Reset
`/bracket reset [title: str]`:
- Resets a tournament that has been started to the specified tournament to the registration phase. 
- If `title` is not provided, targets the subject tournament in the thread.

#### Finalize
`/bracket finalize [title: str]`:
- Finalizes a tournament that has been started to be completed. 
- If `title` is not provided, targets the subject tournament in the thread.

#### Results
`/bracket results [title: str]`:
- Shows the results for the specified tournament if it has been completed. 
- If `title` is not provided, targets the subject tournament in the thread.

#### Disqualify
`/bracket disqualify <user_mention: str>`:
- Privileged instruction: Only authorized users can perform it.
- Disqualifies an entrant from the target tournament.
- `user_mention` must be a valid Discord user mention.
- If the tournament has not been started, removes the entrant instead.
- Must be sent in a tournament thread.

### Matches
#### Report
`/match report <match_id: int> <winner: str>`
- Privileged instruction: Only authorized users can perform it.
- Manually reports the winner for a match, or overrides the result of a completed match.
- All matches ahead of the overwritten match are automatically reset.
- `winner` must be either a user mention, '1', '2', '1️⃣', or '2️⃣'
- Must be sent in a tournament thread.

#### Vote
`/match vote <match_id: int> <vote: str>`
- Manually votes for the winner of a match if the user is a participant in that match.
- `vote` must be either a user mention, '1', '2', '1️⃣', or '2️⃣'
- Must be sent in a tournament thread.

#### Medic
`/match medic`
- Re-calls any missing matches for a tournament in discord.
- Must be sent in a tournament thread.