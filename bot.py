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
with open("config/config.json", "r") as jsonfile:
    config = json.load(jsonfile)
DiscordBotToken = config['DiscordBotToken']
LobbyChannelName = config['LobbyChannelName']
LobbyRole = config['LobbyRole']
PersistentLobbyRole = config['PersistentLobbyRole']
LobbyThreshold = config['LobbyThreshold']
LobbyRestartThreshold = config['LobbyRestartThreshold']
LobbyCooldown = config['LobbyCooldown']
PingRemovalTimer = config['PingRemovalTimer']
Servers = config['Servers']
ReactionEmojis = config['ReactionEmojis']
ReactionIntervals = config['ReactionIntervals']

# declaring other stuff
ReactionIntervalsSeconds = []
Units = {'s': 'seconds', 'm': 'minutes', 'h': 'hours', 'd': 'days', 'w': 'weeks'}
serverinfo = []
CurrentLobbyMembers = []
LobbyActive = False
UpdatingServerInfo = False
allowed_mentions = discord.AllowedMentions(roles=True)


# convert config time intervals into seconds (once) for use in asyncio.sleep
def convert_to_seconds(s):
    return int(timedelta(**{
        Units.get(m.group('unit').lower(), 'seconds'): float(m.group('val'))
        for m in re.finditer(r'(?P<val>\d+(\.\d+)?)(?P<unit>[smhdw]?)', s, flags=re.I)
    }).total_seconds())

# check if a message still exists

for interval in ReactionIntervals:
    ReactionIntervalsSeconds.append(convert_to_seconds(interval))

LobbyCooldownSeconds = convert_to_seconds(LobbyCooldown)
PingRemovalTimerSeconds = convert_to_seconds(PingRemovalTimer)
NaptimeRemainingSeconds = LobbyCooldownSeconds-PingRemovalTimerSeconds

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
        if LobbyActive:
            await active_lobby_message.delete()
        else:
            lobby_message = main_lobby_message
            await lobby_message.delete()
        print("Removing roles...")
        for member in lobby_role.members:
            await member.remove_roles(lobby_role)


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
    global persistent_lobby_role
    for guild in client.guilds:
        for role in guild.roles:
            if role.name == LobbyRole:
                lobby_role = role
                print(f'Lobby Role found: "{lobby_role.name}" (ID: {lobby_role.id})')
            if role.name == PersistentLobbyRole:
                persistent_lobby_role = role
                print(f'Persistent Role found: "{persistent_lobby_role.name}" (ID: {persistent_lobby_role.id})')

    print('------------------------------------------------------')
    print('Checking for old lobby messages to delete...')
    async for message in lobby_channel.history(limit=10):
        if message.author == client.user:
            print(f'Found old message from {client.user}, deleting it')
            await message.delete()
        else:
            print(f'Found old message from {message.author}, leaving it alone')
    print('Finished checking for old messages')
    print('------------------------------------------------------')


    await initialize_lobby_message()

    await mainloop.start(main_lobby_message)


# force update server info and refresh discord message every minute
@tasks.loop(minutes=1)
async def mainloop(lobby_message):
    await update_servers()
    await update_msg(lobby_message)


async def initialize_lobby_message():
    embed = discord.Embed(title='Reticulating Splines...', color=0xfd8002)
    global main_lobby_message
    main_lobby_message = await lobby_channel.send(embed=embed)
    for emoji in ReactionEmojis:
        await main_lobby_message.add_reaction(emoji)
    print(f'Lobby message ID {main_lobby_message.id}')


async def is_message_deleted(ctx, message_id):
    try:
        await ctx.fetch_message(message_id)
        return False
    except discord.errors.NotFound:
        # if a NotFound error appears, the message is either not in this channel or deleted
        return True


# function to update server, only runs in mainloop and activate_lobby (once per minute)
# and should not be called otherwise
async def update_servers():
    UpdatingServerInfo = True
    print(f'Updating server information...')
    global serverinfo
    serverinfo.clear()
    for i in range(len(Servers)):
        serverinfo.append(a2s.info(tuple(Servers[i])))
        print(f'{serverinfo[i].server_name} currently has {serverinfo[i].player_count} players')
    now = datetime.datetime.now()
    print(f'Finished updating server information')
    UpdatingServerInfo = False


# main function for evaluating server info and updating lobby message
# does NOT refresh server info as it would ping servers very frequently
async def update_msg(lobby_message):
    if LobbyActive is True:
        now = datetime.datetime.now()
        print(f'Lobby is active, no need to update message ' + now.strftime("%Y-%m-%d %H:%M:%S"))
        return
    else:
        # needed if the message has changed since first run
        lobby_message = main_lobby_message
        # determine most full server to populate once the lobby is full
        targetindex = 0
        for i in range(len(serverinfo)):
            if serverinfo[i].player_count > serverinfo[targetindex].player_count:
                targetindex = i
        # embeds won't let you do this directly
        CurrentServerPlayers = serverinfo[targetindex].player_count
        DiscordersRequired = int(LobbyThreshold) - CurrentServerPlayers
        print(
            f'Current target server is {serverinfo[targetindex].server_name} with {CurrentServerPlayers} players online')
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
        if CurrentServerPlayers + CurrentLobbySize < int(LobbyThreshold) and LobbyActive is False:
            print(f'Lobby threshold not met ({CurrentLobbySize}+{CurrentServerPlayers}<{LobbyThreshold}), displaying lobby information')
            embed = discord.Embed(title='🇺🇸 Atlanta Regulars Lobby',
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
                while UpdatingServerInfo:
                    print(f'Lobby activated while server info is still updating, waiting a sec for it to finish...')
                    await asyncio.sleep(3)
                print(f'Lobby threshold met! ({CurrentLobbySize}+{CurrentServerPlayers}>={LobbyThreshold})')
                await activate_lobby(lobby_message, targetindex)
        return


# runs when lobby threshold is met
async def activate_lobby(lobby_message, targetindex):
    global LobbyActive
    global active_lobby_message
    # check if the lobby has previously been launched (to prevent multiple notifications)
    if not LobbyActive:
        LobbyActive = True
        # delete old lobby message and send a new message (can't notify role members in edits)
        await lobby_message.delete()
        now = datetime.datetime.now()
        print(f'Old lobby message deleted ' + now.strftime("%Y-%m-%d %H:%M:%S"))
        # new message with role mention to notify lobby members
        # no mentions allowed in embeds, so it has to be ugly :(

        ConnectString = "".join(["steam://connect/", str(Servers[targetindex][0]), ":", str(Servers[targetindex][1])])
        active_lobby_message = await lobby_channel.send(f'\n {lobby_role.mention} {persistent_lobby_role.mention} \n**SERVER IS FILLING UP, GET IN HERE!**\n\n{serverinfo[targetindex].server_name} \n**Connect:** {ConnectString}', allowed_mentions=allowed_mentions)

        print(f'Lobby launched! Message ID: {active_lobby_message.id}')
        print(f'Sleeping for {PingRemovalTimer} before removing ping message')
        await asyncio.sleep(PingRemovalTimerSeconds)
        print(f'PingRemovalTimer expired, removing ping message')
        embed = discord.Embed(title='SERVER IS FILLING UP, GET IN THERE!',
                              description='lil-lobby-bot is napping, lobby will return later',
                              color=0x3b7030)
        await active_lobby_message.edit(embed=embed, content='')
        print(f'Napping notification sent, sleeping until LobbyCooldown ({LobbyCooldown}) has passed since pings')
        await asyncio.sleep(NaptimeRemainingSeconds)
        print(f'My nap is over!')
        embed = discord.Embed(title='I am awake!',
                              description=f'Lobby will return when the server player count gets below {LobbyRestartThreshold}',
                              color=0x3b7030)
        await active_lobby_message.edit(embed=embed, content='')
        print(f'Edited message to let discord know I am awake')
        # remove role now so the logic doesn't double count everyone who joins the server
        print(f'Removing all role members...')
        for member in lobby_role.members:
            await member.remove_roles(lobby_role)
            print(f'Removed {member.name} from {lobby_role.name}')
        await update_servers()
        # don't reactivate lobby until we fall below the restart threshold
        while serverinfo[targetindex].player_count > int(LobbyRestartThreshold):
            print(f'Lobby active and minimum threshold is met ({serverinfo[targetindex].player_count}>{LobbyRestartThreshold}), sleeping some more')
            # main loop should keep server info up to date, it seems to crash sometimes though...
            await asyncio.sleep(60)
        if serverinfo[targetindex].player_count <= int(LobbyRestartThreshold):
            # reset by deleting the launched lobby message and remove roles (just to make sure it's empty before restarting)
            print(f'We fell below the minimum player threshold ({serverinfo[targetindex].player_count}<={LobbyRestartThreshold})')
            print(f'Cleaning up and restarting lobby...')
            await active_lobby_message.delete()
            LobbyActive = False
            for member in lobby_role.members:
                await member.remove_roles(lobby_role)
            await initialize_lobby_message()
            await update_msg(main_lobby_message)
            return
    else:
        # if we are here that means the lobby threshold is met, but notifications have already been sent, do nothing
        print(f'Lobby active but pings have already been sent, doing nothing...')
        return


# refreshes list of lobby members
async def update_lobby_members():
    CurrentLobbyMembers.clear()
    for member in lobby_role.members:
        CurrentLobbyMembers.append(str(member.display_name))
    if not CurrentLobbyMembers:
        print(f'Lobby is currently empty :(')
    else:
        print(f'Current lobby members are:')
        print(" ".join(CurrentLobbyMembers))


# main function for catching user reactions
@client.event
async def on_reaction_add(reaction, member):
    if not member.bot:
        if reaction.message.id == main_lobby_message.id:
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
                        await update_msg(main_lobby_message)
                    else:
                        # if member is not in lobby, put them there
                        reacted_message_id = main_lobby_message.id
                        await member.add_roles(lobby_role)
                        print(f'User {member.name} added to "{lobby_role.name}" for {ReactionIntervals[i]}')
                        # if the lobby is started from someone's reaction, the below update_msg will be awaited until
                        # the bot resets completely (LobbyRestartThreshold), at which point the timer will start.
                        # shouldn't cause an issue with roles because of the reacted_message_id check but
                        # may cause confusing console output. this only applies for the user who puts the lobby
                        # over the threshold, all other timers should work fine
                        await update_msg(main_lobby_message)
                        await asyncio.sleep(ReactionIntervalsSeconds[i])
                        print(f'Timer expired for {member.name} for "{lobby_role.name}" after {ReactionIntervals[i]}!')
                        # after the selected time has passed, check if the message still exists
                        reacted_message_deleted = await is_message_deleted(lobby_channel, reacted_message_id)
                        if reacted_message_deleted:
                            print(f'{member.name} reacted to message {reacted_message_id} but it no longer exists, doing nothing')
                            pass
                        else:
                            # the message still exists, lets check if they're still in the lobby
                            await update_lobby_members()
                            if any(lobbymember == member.name for lobbymember in CurrentLobbyMembers):
                                # if they're still there, AND if the original message they reacted to still exists, remove them
                                print(f'{member.name} reacted to message {reacted_message_id} which still exists, removing them')
                                await reaction.remove(member)
                            else:
                                # if they're not, do nothing (may have removed themselves before the timer was up)
                                print(f'{ReactionIntervals[i]} timer expired for {member.name} but they were previously removed from {lobby_role.name}')
        else:
            pass


# function for catching reaction removals, this fires any time any reaction is removed
# we do not get information about how the reaction was removed (by original user or bot)
# so this should be kept as simple as possible
@client.event
async def on_reaction_remove(reaction, member):
    if reaction.message.id == main_lobby_message.id:
        for i in range(len(ReactionEmojis)):
            if reaction.emoji == ReactionEmojis[i]:
                await member.remove_roles(lobby_role)
                print(f'User {member.name} removed from "{lobby_role.name}"')
                await update_msg(main_lobby_message)


client.run(DiscordBotToken)
