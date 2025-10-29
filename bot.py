import discord
from discord.ext import commands, tasks
import json
from datetime import datetime
import asyncio

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Constants
PING_LOG_CHANNEL_ID = 1432769797481042040  # Channel for pign stat outputs and notifications 660083489235795978
LFG_CHANNEL_IDS = [1432769729805811874]  # Replace with your LFG channel IDs # IDs for LotR lfg channels are 778288621354352690, 778288573623304262, 986715171022049363, 778288662273851442, 778288798898978836, 986715510358040666

# Role IDs and their corresponding thresholds
ROLE_THRESHOLDS = {
    'Rares': {'role_ids': [1432770068353384620, 1432810765466992660], 'threshold': 2},    # Rares (soundless, nuneaton)
    'role2': {'role_ids': [1432770153828978809], 'threshold': 3},    # TLPD
    'role3': {'role_ids': [1432770176767754342], 'threshold': 4}    # PvP
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
                'Rares': 0,
                'role2': 0,
                'role3': 0
            }
        }

    # Update ping counts based on role mentions
    for role in message.role_mentions:
        role_id = role.id
        # Check which role category was pinged
        for category, data in ROLE_THRESHOLDS.items():
            if role_id == data['role_ids']:
                ping_data[author_id]['categories'][category] += 1
                ping_data[author_id]['total_pings'] += 1
    
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
            role = user.guild.get_role(data['role_ids'])
            if role:
                await channel.send(f'🎉 {user.mention} has reached {data["threshold"]} {category} role pings!')

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

# Add a slash command to trigger the report manually
@bot.tree.command(name="makereport", description="Generate the ping report now")
async def makereport(interaction: discord.Interaction):
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

    if str(member.id) in ping_data:
        data = ping_data[str(member.id)]
        embed = discord.Embed(title=f"Stats for {member.name}", color=discord.Color.blue())
        embed.add_field(name="Total Pings", value=str(data['total_pings']))
        for category, count in data['categories'].items():
            embed.add_field(name=category.title(), value=str(count))
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("No data found for this user.")

bot_start_time = datetime.now()

@bot.tree.command(name="uptime", description="Shows how long the bot has been running")
async def uptime(interaction: discord.Interaction):
    current_time = datetime.now()
    uptime_duration = current_time - bot_start_time
    days = uptime_duration.days
    hours, remainder = divmod(uptime_duration.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    await interaction.response.send_message(
        f"Bot uptime: {days}d {hours}h {minutes}m {seconds}s"
    )
     

@bot.tree.command(name="shutdown", description="Shuts down the bot")
async def shutdown(interaction: discord.Interaction):
    await interaction.response.send_message("Shutting down...")
    await bot.close()


# Run the bot
bot.run('Here-goes-the-secret-sauce_uwu')    