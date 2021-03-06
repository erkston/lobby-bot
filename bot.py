# lil-lobby-bot
import a2s
import asyncio
import datetime
import discord
import json
import re
from discord.ext import tasks
from datetime import timedelta

# importing config and reading variables
with open("config.json", "r") as jsonfile:
    config = json.load(jsonfile)
DiscordBotToken = config['DiscordBotToken']
LobbyChannelName = config['LobbyChannelName']
LobbyRole = config['LobbyRole']
LobbyThreshold = config['LobbyThreshold']
LobbyRestartThreshold = config['LobbyRestartThreshold']
NAservers = config['NAservers']
ReactionEmojis = config['ReactionEmojis']
ReactionIntervals = config['ReactionIntervals']

# declaring other stuff
ReactionIntervalsSeconds = []
Units = {'s': 'seconds', 'm': 'minutes', 'h': 'hours', 'd': 'days', 'w': 'weeks'}
NAserverinfo = []
NALobbyActive = False
allowed_mentions = discord.AllowedMentions(roles=True)


# convert config time intervals into seconds (once) for use in asyncio.sleep
def convert_to_seconds(s):
    return int(timedelta(**{
        Units.get(m.group('unit').lower(), 'seconds'): float(m.group('val'))
        for m in re.finditer(r'(?P<val>\d+(\.\d+)?)(?P<unit>[smhdw]?)', s, flags=re.I)
    }).total_seconds())


for interval in ReactionIntervals:
    ReactionIntervalsSeconds.append(convert_to_seconds(interval))

# convert config emojis into a string for discord embed message (once)
IntervalsString = ""
for i in range(len(ReactionEmojis)):
    IntervalsString += "".join([ReactionEmojis[i], " for ", ReactionIntervals[i], "ㅤ"])

# need members intent for detecting removal of reactions
intents = discord.Intents.default()
intents.members = True


# cleanup functions to delete any messages and remove all users from lobby roles
class DiscordBot(discord.Client):
    async def cleanup(self):
        print('------------------------------------------------------')
        print(f'Shutting down {client.user}...')
        print("Cleaning up messages...")
        lobby_message = NA_lobby_message
        await lobby_message.delete()
        print("Removing roles...")
        for member in lobby_role.members:
            await member.remove_roles(lobby_role)
        if NALobbyActive:
            await active_lobby_message.delete()

    async def close(self):
        await self.cleanup()
        print("Goodbye...")
        await super().close()


client = DiscordBot(intents=intents)


# run once at bot start
@client.event
async def on_ready():
    print('------------------------------------------------------')
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------------------------------------------------------')
    print(f'{client.user} is connected to the following guild(s):')
    for guild in client.guilds:
        print(f'{guild.name} (id: {guild.id})')

    # iterate through channels to find the one that matches the name in the config
    global lobby_channel
    for guild in client.guilds:
        for channel in guild.channels:
            if channel.name == LobbyChannelName:
                lobby_channel = channel
                print(f'Channel found: #{lobby_channel.name} (ID: {lobby_channel.id})')

    # iterate through roles to find the one that matches the name in the config
    global lobby_role
    for guild in client.guilds:
        for role in guild.roles:
            if role.name == LobbyRole:
                lobby_role = role
                print(f'Role found: "{lobby_role.name}" (ID: {lobby_role.id})')

    print('------------------------------------------------------')

    await initialize_lobby_message()

    await mainloop.start(NA_lobby_message)


# force update server info and refresh discord message every minute
@tasks.loop(minutes=1)
async def mainloop(lobby_message):
    await update_servers()
    await update_msg(lobby_message)


async def initialize_lobby_message():
    embed = discord.Embed(title='Reticulating Splines...', color=0xfd8002)
    global NA_lobby_message
    NA_lobby_message = await lobby_channel.send(embed=embed)
    for emoji in ReactionEmojis:
        await NA_lobby_message.add_reaction(emoji)
    print(f'Lobby message ID {NA_lobby_message.id}')


# function to update server, only runs in mainloop (once per minute) and should not be called otherwise
async def update_servers():
    print(f'Updating server information...')
    global NAserverinfo
    for i in range(len(NAservers)):
        NAserverinfo.append(a2s.info(tuple(NAservers[i])))
        print(f'{NAserverinfo[i].server_name} currently has {NAserverinfo[i].player_count} players')


# main function for evaluating server info and updating lobby message
# does NOT refresh server info as it would ping servers very frequently
async def update_msg(lobby_message):
    # needed if the message has changed since first run
    lobby_message = NA_lobby_message
    # determine most full server to populate once the lobby is full
    NAtargetindex = 0
    for i in range(len(NAserverinfo)):
        if NAserverinfo[i].player_count > NAserverinfo[NAtargetindex].player_count:
            NAtargetindex = i
    # embeds won't let you do this directly
    CurrentServerPlayers = NAserverinfo[NAtargetindex].player_count
    DiscordersRequired = int(LobbyThreshold) - CurrentServerPlayers
    print(
        f'Current target server is {NAserverinfo[NAtargetindex].server_name} with {CurrentServerPlayers} players online')
    await update_lobby_members()
    # pause a second for members to update
    await asyncio.sleep(1)
    # get lobby members and format into nice string for discord embed
    CurrentLobbySize = len(CurrentLobbyMembers)
    s = ", "
    LobbyMembersString = s.join(CurrentLobbyMembers)
    # if no members display "None" in discord
    if not LobbyMembersString:
        LobbyMembersString = "None"
    # if the threshold is not met AND lobby is not already active, display lobby info in embed
    if CurrentServerPlayers + CurrentLobbySize < int(LobbyThreshold) and NALobbyActive is False:
        print(f'Lobby threshold not met ({CurrentLobbySize}+{CurrentServerPlayers}<{LobbyThreshold}) or lobby still active, displaying lobby information')
        embed = discord.Embed(title='🇺🇸 NA Central Casual Lobby',
                              description='Pings will be sent once ' + LobbyThreshold + ' players are ready. \n Currently ' + str(
                                  CurrentServerPlayers) + ' player(s) in-game and ' + str(
                                  DiscordersRequired) + ' more needed here!',
                              color=0xfd8002)
        embed.add_field(name='Players in lobby (' + str(CurrentLobbySize) + "/" + str(
                                  DiscordersRequired) + '):', value=LobbyMembersString,
                        inline=False)
        embed.add_field(name='\u200b', value='\u200b', inline=False)
        embed.add_field(name='React below to join!', value=IntervalsString, inline=False)
        embed.timestamp = datetime.datetime.now()
        embed.set_footer(text='Last updated')
        await lobby_message.edit(embed=embed)
        now = datetime.datetime.now()
        print(f'Lobby message updated ' + now.strftime("%Y-%m-%d %H:%M:%S"))
    else:
        print(f'Lobby threshold met! ({CurrentLobbySize}+{CurrentServerPlayers}>={LobbyThreshold})')
        await activate_lobby(lobby_message, NAtargetindex)
    return


# runs when lobby threshold is met
async def activate_lobby(lobby_message, NAtargetindex):
    global NALobbyActive
    global active_lobby_message
    # check if the lobby has previously been launched (to prevent multiple notifications)
    if not NALobbyActive:
        NALobbyActive = True
        # delete old lobby message and send a new message (can't notify role members in edits)
        await lobby_message.delete()
        now = datetime.datetime.now()
        print(f'Old lobby message deleted ' + now.strftime("%Y-%m-%d %H:%M:%S"))
        # new message with role mention to notify lobby members
        # no mentions allowed in embeds, so it has to be ugly :(

        ConnectString = "".join(["steam://connect/", str(NAservers[NAtargetindex][0]), ":", str(NAservers[NAtargetindex][1])])
        active_lobby_message = await lobby_channel.send(f'{lobby_role.mention} \n**GET IN HERE!**\n\n{NAserverinfo[NAtargetindex].server_name} \n**Connect:** {ConnectString}', allowed_mentions=allowed_mentions)

        print(f'Lobby launched! Message ID: {active_lobby_message.id}')
        # wait 5 minutes for people to connect
        await asyncio.sleep(20)
        # remove role now so the logic doesn't double count everyone who joins the server
        for member in lobby_role.members:
            await member.remove_roles(lobby_role)
        # don't reactivate lobby until we fall below the restart threshold
        if NAserverinfo[NAtargetindex].player_count > int(LobbyRestartThreshold):
            print(f'Lobby active and minimum threshold is met, sleeping some more')
            await asyncio.sleep(60)
        else:
            # reset by deleting the launched lobby message and remove roles (just to make sure it's empty before restarting)
            print(f'Lobby active but we fell below the minimum player threshold, cleaning up and restarting lobby...')
            await active_lobby_message.delete()
            NALobbyActive = False
            for member in lobby_role.members:
                await member.remove_roles(lobby_role)
            await initialize_lobby_message()
            await update_msg(NA_lobby_message)
    else:
        # if we are here that means the lobby threshold is met, but notifications have already been sent, do nothing
        return


# refreshes list of lobby members
# why is this a separate function? i forget
async def update_lobby_members():
    global CurrentLobbyMembers
    CurrentLobbyMembers = []
    for member in lobby_role.members:
        CurrentLobbyMembers.append(member.name)


# main function for catching user reactions
@client.event
async def on_reaction_add(reaction, member):
    if not member.bot:
        if reaction.message.id == NA_lobby_message.id:
            for i in range(len(ReactionEmojis)):
                if reaction.emoji == ReactionEmojis[i]:
                    # if user is already in lobby, remove this reaction but keep them in the lobby
                    # since this removes the reaction it will remove the role as well, so we need to give it back to them
                    if any(role.id == lobby_role.id for role in member.roles):
                        await reaction.remove(member)
                        print(f'User {member.name} already has role "{lobby_role.name}"')
                        # wait 2 seconds for the reaction remove event to complete before putting member back in lobby
                        await asyncio.sleep(2)
                        await member.add_roles(lobby_role)
                        await update_msg(NA_lobby_message)
                    else:
                        # if member is not in lobby, put them there
                        await member.add_roles(lobby_role)
                        print(f'User {member.name} added to "{lobby_role.name}" for {ReactionIntervals[i]}')
                        await update_msg(NA_lobby_message)
                        await asyncio.sleep(ReactionIntervalsSeconds[i])
                        # after the selected time has passed, check if they are still in the lobby
                        await update_lobby_members()
                        if any(lobbymember == member.name for lobbymember in CurrentLobbyMembers):
                            # if they're still there, remove them
                            print(
                                f'Timer expired for {member.name} for "{lobby_role.name}" after {ReactionIntervals[i]}!')
                            await reaction.remove(member)
                        else:
                            # if they're not, do nothing (may have removed themselves before the timer was up)
                            print(
                                f'{ReactionIntervals[i]} timer expired for {member.name} but they were previously removed from {lobby_role.name}!')
        else:
            pass


# function for catching reaction removals, this fires any time any reaction is removed
# we do not get information about how the reaction was removed (by original user or bot)
# so this should be kept as simple as possible
@client.event
async def on_reaction_remove(reaction, member):
    if reaction.message.id == NA_lobby_message.id:
        for i in range(len(ReactionEmojis)):
            if reaction.emoji == ReactionEmojis[i]:
                await member.remove_roles(lobby_role)
                print(f'User {member.name} removed from "{lobby_role.name}"')
                await update_msg(NA_lobby_message)


client.run(DiscordBotToken)
