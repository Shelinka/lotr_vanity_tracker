import discord
from discord.ext import commands, tasks
import json
from datetime import datetime
import asyncio
import io

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Command logging
async def log_command(interaction: discord.Interaction, command_name: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "user_id": str(interaction.user.id),
        "username": str(interaction.user),
        "command": command_name,
        "timestamp": timestamp
    }
    
    try:
        with open('commands_log.json', 'r') as f:
            log_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        log_data = []
    
    log_data.append(log_entry)
    
    with open('commands_log.json', 'w') as f:
        json.dump(log_data, f, indent=4)

# Constants
PING_LOG_CHANNEL_ID = 660083489235795978  # Channel for pign stat outputs and notifications
LFG_CHANNEL_IDS = [778288621354352690, 778288573623304262, 986715171022049363, 778288662273851442, 778288798898978836, 986715510358040666]  # LFG channel IDs
ADMINITARTOR_ROLES = [711224923460468826, 659740317259661372, 1433141810057969674]  # IDs of roles who can use admin commands

# Role IDs and their corresponding thresholds
ROLE_THRESHOLDS = {
    'Ultra_rares': {'role_id': [687028469930131000, 687028563865632849, 687028613459214379, 687028919936876627, 687028971267031064, 687028721861001412, 660081524657487892, 939823090307850280], 'threshold': 20},  
    'ID_sharing': {'role_id': [903969899918008410], 'threshold': 20},
    'Rares': {'role_id': [777484092282896394, 666199077481873449, 666197795144859649, 1038892426519121990, 1038892485096775771, 753501961101246475, 753501962766647427, 748133477056249876, 753530278273744899, 758937734525091850, 748133605368266782, 781889750448865310, 855135324657549333, 855135349575516191, 939822538920427611, 1034807828432568372, 1094150532807000144, 1258021911196209172, 1260968614903939153, 1341727244124684330, 1385303579233095720, 1385304598322872542, 1359807972829696040], 'threshold': 30},
    'Dungeons': {'role_id': [985794399067865139, 985796623433076778, 985794425944956978, 1107600943043858502, 1258022020239720611, 1258021968540860517, 1430567782163943625, 1430556629010616350], 'threshold': 20},
    'Raids': {'role_id': [711225442325102683, 985794435440844840, 1034811690237317230, 1094149884812206131, 1150685526291120208, 1258022624240336916, 1328727728576528415], 'threshold': 20},
    'Mythic_raids': {'role_id': [985794654098292776, 985794516202172417, 985794709412786176, 1150685197474463855, 1258022786056847420, 1328727871090593874, 1385302809771118834, 1430557202648928397], 'threshold': 20},    
    'Glory_runs': {'role_id': [1034812108602351746, 778323337683533854, 1034811877726883910, 710542726374096998, 710542724268294185, 855145467490861098, 710542719088328746, 710542721416298638, 710540675409510460, 710540675078422609, 748134751377948693, 748132701722247188, 842315872172507177, 939822516308946954, 1034807652334714910, 1034807546361434173, 1094150371993210970, 1167469088877056060, 1258022446015971370, 1341727037324525569, 1385302843484930139, 1430556457090158693], 'threshold': 20},
    'World_events': {'role_id': [976405965454848040, 778323490507194389, 1150684869584769044, 752275368433418310, 750979637059911743, 777484095831801866, 1034812038993690724, 856199620173365289, 1048243711261290596, 1034811852212940872, 1260966109428056094, 1170682058796970006, 1359808209677979648, 1041664703849562163], 'threshold': 40},    
    'Secret(:': {'role_id': [711224923460468826, 659740317259661372, 1433141810057969674], 'threshold': 100}   
}


# Data storage
ping_data = {}

# Load existing data
try:
    with open('ping_data.json', 'r') as f:
        ping_data = json.load(f)
except FileNotFoundError:
    pass

# Save data function
async def save_data():
    with open('ping_data.json', 'w') as f:
        json.dump(ping_data, f)

@bot.event
async def on_ready():
    print(f'Bot is ready as {bot.user}')
    try:
        synced = await bot.tree.sync()  # register slash commands with Discord
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
  #  monthly_report.start()

@bot.event
async def on_message(message):
    if message.channel.id not in LFG_CHANNEL_IDS:
        return

    author_id = str(message.author.id)
    
    # Initialize user data if not exists
    if author_id not in ping_data:
        ping_data[author_id] = {
            'total_pings': 0,
            'categories': {
                'Ultra_rares': 0,
                'ID_sharing': 0,
                'Rares': 0,
                'Dungeons': 0,
                'Raids': 0,
                'Mythic_raids': 0,
                'Glory_runs': 0,
                'World_events': 0,
                'Secret(:': 0
            }
        }

    # Update ping counts based on role mentions
    for role in message.role_mentions:
        role_id = role.id
        # Check which role category was pinged
        for category, data in ROLE_THRESHOLDS.items():
            if role_id in data['role_id']:  # Changed from == to in to check list membership
                ping_data[author_id]['categories'][category] += 1
                ping_data[author_id]['total_pings'] += 1
                break  # Break to avoid counting the same ping multiple times
    
    # Check thresholds
    await check_thresholds(message.author, ping_data[author_id])
    await save_data()
    await bot.process_commands(message)

async def check_thresholds(user, user_data):
    channel = bot.get_channel(PING_LOG_CHANNEL_ID)
    if not channel:
        return

    for category, data in ROLE_THRESHOLDS.items():
        if user_data['categories'][category] == data['threshold']:
            # Send notification for each role in the category
            for role_id in data['role_id']:
                role = user.guild.get_role(role_id)
                if role:
                    await channel.send(f'🎉 {user.mention} has reached {data["threshold"]} {category} role pings!')
                    break  # Send only one notification per threshold reached

@tasks.loop(hours=24*30)  # Monthly report
async def monthly_report():
    channel = bot.get_channel(PING_LOG_CHANNEL_ID)
    if not channel:
        return

    report = "Monthly Ping Report \n\n"
    
    for user_id, data in ping_data.items():
        user = bot.get_user(int(user_id))
        if user:
            report += f"{user.name}:\n"
            report += f"Total pings: {data['total_pings']}\n"
            for category, count in data['categories'].items():
                report += f"{category}: {count}\n"
            report += "\n"

    await channel.send(report)

# Slash commands



@bot.tree.command(name="makereport", description="Generate the ping report now")
async def makereport(interaction: discord.Interaction):
    await log_command(interaction, "makereport")
    if not any(role.id in ADMINITARTOR_ROLES for role in interaction.user.roles):
        return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)

    channel = bot.get_channel(PING_LOG_CHANNEL_ID)
    # Build report (same logic as monthly_report)
    report = "Ping Report\n\n"
    for user_id, data in ping_data.items():
        user = bot.get_user(int(user_id))
        if user:
            report += f"{user.name}:\n"
            report += f"Total pings: {data['total_pings']}\n"
            for category, count in data['categories'].items():
                report += f"{category}: {count}\n"
            report += "\n"
    # Respond to the interaction with the report (visible to the channel or just the user)
    await interaction.response.send_message(report, ephemeral=False)

@bot.tree.command(name="checkstats", description="Generate ping stats for specified user")
async def checkstats(interaction: discord.Interaction, member: discord.Member):
    await log_command(interaction, "checkstats")
    if not any(role.id in ADMINITARTOR_ROLES for role in interaction.user.roles):
        return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)

    if str(member.id) in ping_data:
        data = ping_data[str(member.id)]
        embed = discord.Embed(title=f"Stats for {member.name}", color=discord.Color.blue())
        embed.add_field(name="Total Pings", value=str(data['total_pings']))
        for category, count in data['categories'].items():
            embed.add_field(name=category.title(), value=str(count))
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("No data found for this user.")

@bot.tree.command(name="mystats", description="View your own ping statistics")
async def mystats(interaction: discord.Interaction):
    await log_command(interaction, "mystats")
    user_id = str(interaction.user.id)
    if user_id in ping_data:
        data = ping_data[user_id]
        embed = discord.Embed(title=f"Your Stats", color=discord.Color.blue())
        embed.add_field(name="Total Pings", value=str(data['total_pings']))
        for category, count in data['categories'].items():
            embed.add_field(name=category.title(), value=str(count))
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message("You have no ping statistics yet.", ephemeral=True)


bot_start_time = datetime.now()

@bot.tree.command(name="uptime", description="Shows how long the bot has been running")
async def uptime(interaction: discord.Interaction):
    await log_command(interaction, "uptime")
    current_time = datetime.now()
    uptime_duration = current_time - bot_start_time
    days = uptime_duration.days
    hours, remainder = divmod(uptime_duration.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    await interaction.response.send_message(
        f"Bot uptime: {days}d {hours}h {minutes}m {seconds}s"
    )
     

@bot.tree.command(name="viewlogs", description="View the command usage logs")
async def viewlogs(interaction: discord.Interaction):
    await log_command(interaction, "viewlogs")
    if not any(role.id in ADMINITARTOR_ROLES for role in interaction.user.roles):
        return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
    
    try:
        with open('commands_log.json', 'r') as f:
            log_data = json.load(f)
    except FileNotFoundError:
        return await interaction.response.send_message("No command logs found.", ephemeral=True)
    
    # Create a formatted message with the last 20 commands
    log_entries = log_data[-20:]  # Get last 20 entries
    response = "📋 **Last 20 Command Logs**\n\n"
    
    for entry in log_entries:
        response += f"**Command:** /{entry['command']}\n"
        response += f"**User:** {entry['username']} (ID: {entry['user_id']})\n"
        response += f"**Time:** {entry['timestamp']}\n"
        response += "─────────────────\n"
    
    await interaction.response.send_message(response, ephemeral=True)

@bot.tree.command(name="shutdown", description="Shuts down the bot")
async def shutdown(interaction: discord.Interaction):
    await log_command(interaction, "shutdown")
    if not any(role.id in ADMINITARTOR_ROLES for role in interaction.user.roles):
        return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)

    await interaction.response.send_message("kk bye :(")
    await bot.close()
    print(f'Script closed by {interaction.user}')
    

@bot.tree.command(name="export", description="Export the current stats as a JSON file")
async def export_stats(interaction: discord.Interaction):
    await log_command(interaction, "export")
    if not any(role.id in ADMINITARTOR_ROLES for role in interaction.user.roles):
        return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)

    json_string = json.dumps(ping_data, indent=4)
    
    file = discord.File(
        fp=io.StringIO(json_string),
        filename="ping_stats.json"
    )
    
    await interaction.response.send_message(
        "Here are the current stats:",
        file=file,
        ephemeral=True
    )


with open(".env", "r") as f:
    token = f.read().strip()

bot.run(token)