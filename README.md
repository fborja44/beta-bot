# **beta-bot**
**beta-bot** is an interactive discord bot using the [discord.py](https://discordpy.readthedocs.io/en/stable/) library to create and administrate tournaments through Discord text channels.

Brackets are generated using the [Challonge.com API](https://api.challonge.com/v1). Bracket images are created and hosted on imgur using the [Imgur API](https://apidocs.imgur.com/).

## Commands
### Brackets
`$bracket create <name> [time]`:
- Creates a new bracket with the provided name and time. Times in EST.
- Default start time is 1 hour ahead of current time. 

`$bracket delete [name]`:
- Deletes the specified bracket. 
- If no name is provided, deletes the most recently created bracket.

`$bracket update [name]`:
- Incomplete

`$bracket start [name]`:
- Starts the specified bracket if in the registration phase. 
- If no name is provided, starts the most recently created bracket that has not yet been completed.
- Only one bracket may be active per server.

`$bracket reset [name]`:
- Resets a bracket that has been started to the specified bracket to the registration phase. 
- If no name is provided, resets the current active bracket.

`$bracket finalize [name]`:
- Finalizes a bracket that has been started to be completed. 
- If no name is provided, finalizes the current active bracket.

`$bracket results [name]`:
- Shows the results for the specified bracket if it has been completed. 
- If no name is provided, shows the results for the most recently completed bracket.

`$bracket dq [entrant_name]` as reply:
- Disqualifies an entrant from the targeted bracket.
- Must be in reply to an active bracket or match message.

### Bracket Matches
`$bracket override <entrant_name | 1 | 2>` as reply:
- Manually reports the winner for a match, or overrides the result of a completed match.
- All matches ahead of the overwritten match are automatically reset.
- Must be in reply to a match message.

`$bracket dq [entrant_name]` as reply:
- Disqualifies an entrant from the targeted match's bracket.
- Must be in reply to an active bracket or match message.