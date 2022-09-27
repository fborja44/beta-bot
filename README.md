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

### Tournaments
Tournaments must be created in designiated tournament channels. To see the list of channel commands, see the [Channels](#Channels) section.
#### Help
`/t help`
- Sends a list of tournament commands.

#### Create
`/t create <title: str> [time: str] [single_elim: bool] [max_entrants: int]`:
- Creates a new tournament with the provided name and time. Times in ET.
- Default start time is 1 hour ahead of the time of creation.
- ex. time: `10 PM` or `10:00 PM`.
- Max length of `title` is 60 characters.
- `max_entrants` must be between 4 and 24.

#### Join
`/t join [title: str]`:
- Adds the user to the specified tournament. 
- If `title` is not provided, targets the subject tournament in the thread.

#### Leave
`/t delete [title: str]`:
- Deletes the specified tournament. 
- If `title` is not provided, targets the subject tournament in the thread.

#### Delete
`/t delete [title: str]`:
- Deletes the specified tournament. 
- If `title` is not provided, targets the subject tournament in the thread.

#### Update
`/t update <title: str> [new_title: str] [time: str] [single_elim: bool] [max_entrants: int]`:
- Updates the specified tournament using the provided information. Times in ET.
- ex. time: `10 PM` or `10:00 PM`.
- Max length of title is 60 characters.
- `max_entrants` must be between 4 and 24.

#### Start
`/t start [title: str]`:
- Starts the specified tournament if in the registration phase. 
- If `title` is not provided, targets the subject tournament in the thread.
- Only one tournament may be active per server.

#### Reset
`/t reset [title: str]`:
- Resets a tournament that has been started to the specified tournament to the registration phase. 
- If `title` is not provided, targets the subject tournament in the thread.

#### Finalize
`/t finalize [title: str]`:
- Finalizes a tournament that has been started to be completed. 
- If `title` is not provided, targets the subject tournament in the thread.

#### Results
`/t results [title: str]`:
- Shows the results for the specified tournament if it has been completed. 
- If `title` is not provided, targets the subject tournament in the thread.

#### Report
`/t report <match_id: int> <winner: str>`
- Privileged instruction: Only authorized users can perform it.
- Manually reports the winner for a match, or overrides the result of a completed match.
- All matches ahead of the overwritten match are automatically reset.
- `winner` must be either a user mention, '1', '2', '1️⃣', or '2️⃣'
- Must be sent in a tournament thread.

#### Vote
`/t vote <match_id: int> <vote: str>`
- Manually votes for the winner of a match if the user is a participant in that match.
- `vote` must be either a user mention, '1', '2', '1️⃣', or '2️⃣'
- Must be sent in a tournament thread.

#### Disqualify
`/t disqualify <user_mention: str> [title: str]`:
- Privileged instruction: Only authorized users can perform it.
- Disqualifies an entrant from the target tournament.
- `user_mention` must be a valid Discord user mention.
- If the tournament has not been started, removes the entrant instead.
- If `title` is not provided, targets the subject tournament in the thread.

### Channels
Manage and configure tournament channels and alerts. A tournament channel must be created before tournaments can be created in a server.
#### Help
`/t help`
- Sends a list of channel configuration commands.

#### create
`/ch create <channel_name: str> <is_forum: bool> [allow_messages: bool] [category_name: str]`:
- Privileged instruction: Only authorized users can perform it.
- Creates a new tournament channel.
- If `is_forum` is true, created as a Forum Channel if available in the server, otherwise the channel is created as a Text Channel.

#### delete
`/ch delete [channel_mention: str]`:
- Privileged instruction: Only authorized users can perform it.
- Deletes the target channel.
- All incomplete tournaments created in the target channel are also deleted. Tournaments that have been finalized persist in the database.
- If `channel_mention` is not provided, targets the channel the command was sent in.

#### alert
`/ch alert <tournament_channel: str> [alert_channel: str]`:
- Privileged instruction: Only authorized users can perform it.
- Adds `alert_channel` to receive tournament alerts from `tournament_channel`.
- `alert_channel` and `tournament_channel` must be valid Discord channel mentions.
- If `alert_channel` is not provided, targets the channel the command was sent in.

#### remove_alert
`/ch remove_alert <tournament_channel: str> [alert_channel: str]`:
- Privileged instruction: Only authorized users can perform it.
- Removes `alert_channel` from receiving tournament alerts from `tournament_channel`.
- `alert_channel` and `tournament_channel` must be valid Discord channel mentions.
- If `alert_channel` is not provided, targets the channel the command was sent in.
