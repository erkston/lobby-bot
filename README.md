## lil-lobby-bot
This is a discord bot designed to place users into a "lobby" that sends players to a server once a set amount have joined. 
Users join the lobby by clicking a reaction in discord, different reactions have different lengths of time for the bot to wait before they remove the user (or until the lobby is full and "launches").

![Example lobby](https://i.imgur.com/Zxvdfil.png)

The bot reads the number of current players on the servers and adds that to the number of players waiting in discord, and alerts when that total meets a threshold:

![Example alert](https://i.imgur.com/ATHpA3z.png)

Made for TF2 but should work with anything compatible with python-a2s.
## Discord set-up
The bot requires the following permissions: Manage Roles, Send Messages, Manage Messages, Embed Links, Add Reactions. It also requires the "Members" Privileged Gateway Intent, and permission to mention roles.
The server should have a dedicated channel and role as well (see config below)
## Configuration
- DiscordBotToken - Your bots token from the Discord Developer Portal
- LobbyChannelName - The Channel name the bot should use to send messages
- LobbyRole - The Role name the bot should use to alert people once the lobby is full
- PersistentLobbyRole - A separate Role that will always be pinged when the lobby is full. Role members are not removed automatically (as they are for LobbyRole) so members of this role will  always be notified when a lobby fills without having to enter the lobby themselves. Members of this role are not considered in the math that determines when the lobby is full.
- LobbyThreshold - The number of players the bot should wait for before sending discord pings. This is total players including any already on the server
- LobbyRestartThreshold - The bot will wait until the number of players on the server falls below this number to reset and start a new discord lobby
- Servers - List of servers to check, can be any number of servers as long as the syntax is preserved.
- ReactionEmojis and ReactionIntervals - These are used for the reactions on the lobby message that users will click to join the lobby. There can be any number of each, so long as each emoji has a corresponding time interval. From top to bottom in the config they will appear in discord left to right. Time intervals must have units attached (30s, 45m, 5h, etc) 
