# **beta-bot**
**beta-bot** is an interactive discord bot using the [discord.py](https://discordpy.readthedocs.io/en/stable/) [2.0] library to create and administrate tournaments through Discord text channels using the [Discord API](https://discord.com/developers/docs/intro).

Brackets are generated using the [Challonge.com API](https://api.challonge.com/v1). Bracket images are created and hosted on imgur using the [Imgur API](https://apidocs.imgur.com/).

## Links
- Challonge.com API: https://api.challonge.com/v1
- Discord API: https://discord.com/developers/docs/intro
- discord.py: https://discordpy.readthedocs.io/en/stable/
- Imgur API: https://apidocs.imgur.com/

## Commands
All commands use the `/` prefix and `/slash command` feature of Discord for help with validation, error handling, and parameter autofill/documentation.

### Brackets
`/bracket create <bracket_title: str> [time: str] [single_elim: bool] [max_entrants: int]`:
- Creates a new bracket with the provided name and time. Times in EST.
- Default start time is 1 hour ahead of current time. 
- ex. time: `10 PM` or `10:00 PM`.
- Max length of `bracket_title` is 60 characters.
- `max_entrants` must be between 4 and 24.

`/bracket delete [bracket_title: str]`:
- Deletes the specified bracket. 
- If `bracket_title` is not provided, deletes the most recently created bracket.

`/bracket update <bracket_title: str> [new_bracket_title: str] [time: str] [single_elim: bool] [max_entrants: int]`:
- Updates the specified bracket using the provided information.
- ex. time: `10 PM` or `10:00 PM`.
- Max length of title is 60 characters.
- `max_entrants` must be between 4 and 24.

`/bracket start [bracket_title: str]`:
- Starts the specified bracket if in the registration phase. 
- If `bracket_title` is not provided, starts the most recently created bracket that has not yet been completed.
- Only one bracket may be active per server.

`/bracket reset [bracket_title: str]`:
- Resets a bracket that has been started to the specified bracket to the registration phase. 
- If `bracket_title` is not provided, resets the current active bracket.

`/bracket finalize [bracket_title: str]`:
- Finalizes a bracket that has been started to be completed. 
- If `bracket_title` is not provided, finalizes the current active bracket.

`/bracket results [bracket_title: str]`:
- Shows the results for the specified bracket if it has been completed. 
- If `bracket_title` is not provided, shows the results for the most recently completed bracket.

`/bracket report <match_challonge_id: int> <winner: str>`
- Manually reports the winner for a match, or overrides the result of a completed match.
- All matches ahead of the overwritten match are automatically reset.
- `winner` must be either a player name, '1', '2', '1️⃣', or '2️⃣'

`/bracket disqualify <entrant_name: str> [bracket_title: str]`:
- Disqualifies an entrant from the targeted bracket.
- If the bracket has not been started, removes the entrant instead.
- If `bracket_title` is not provided, targets the current active bracket.

### Challenges
`/challenge create [best_of: int] [player_mention: str]`
- Creates a new challenge. By default, is a best of 3.
- If `player_mention` is not provided, creates an open challenge. Otherwise, directly challenges the mentioned player.
- `best_of` must be a positive odd integer.
- `player_mention` must be a mention of a player. ex. `@WOOPBOT`

`/challenge cancel [challenge_id: int]`
- Cancels a challenge if it has not been accepted.
- If `challenge_id` is not provided, targets the user's active challenge if it exists.

`/challenge delete [challenge_id: int]`
- Privileged instruction: Only authorized users can perform it.
- Cancels a challenge no matter the state.
- Leaderboard records are updated appropriately.
- If `challenge_id` is not provided, targets the user's active challenge if it exists.

### Challenges Leaderboard
`/leaderboard stats [player_mention: str]`
- Retreives and displays the leaderboard stats for the targeted player.
- If `player_mention` is not provided, targets the user who called the command.
- `player_mention` must be a mention of a player. ex. `@WOOPBOT`