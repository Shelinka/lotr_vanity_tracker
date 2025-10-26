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
PING_LOG_CHANNEL_ID = 123456789  # Replace with your channel ID
LFG_CHANNEL_IDS = [111111, 222222]  # Replace with your LFG channel IDs

# Role IDs and their corresponding thresholds
ROLE_THRESHOLDS = {
    'tank': {'role_id': 333333, 'threshold': 50},    # Replace with tank role ID
    'healer': {'role_id': 444444, 'threshold': 50},  # Replace with healer role ID
    'dps': {'role_id': 555555, 'threshold': 50}      # Replace with DPS role ID
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
    monthly_report.start()

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
                'soundless': 0,
                'rare_spawns': 0,
                'raids': 0,
                'dungeons': 0
            }
        }

    # Update ping counts based on message content
    content = message.content.lower()
    if 'soundless' in content:
        ping_data[author_id]['categories']['soundless'] += 1
    if any(rare in content for rare in ['rare', 'spawn', 'world boss']):
        ping_data[author_id]['categories']['rare_spawns'] += 1

    ping_data[author_id]['total_pings'] += 1
    
    # Check thresholds
    await check_thresholds(message.author, ping_data[author_id])
    await save_data()
    await bot.process_commands(message)

async def check_thresholds(user, user_data):
    channel = bot.get_channel(PING_LOG_CHANNEL_ID)
    if not channel:
        return

    for category, threshold in THRESHOLD_NOTIFICATIONS.items():
        if user_data['categories'][category] == threshold:
            await channel.send(f'🎉 {user.mention} has reached {threshold} {category} shares!')

@tasks.loop(hours=24*30)  # Monthly report
async def monthly_report():
    channel = bot.get_channel(PING_LOG_CHANNEL_ID)
    if not channel:
        return

    report = "📊 Monthly Ping Report 📊\n\n"
    
    for user_id, data in ping_data.items():
        user = bot.get_user(int(user_id))
        if user:
            report += f"{user.name}:\n"
            report += f"Total pings: {data['total_pings']}\n"
            for category, count in data['categories'].items():
                report += f"{category}: {count}\n"
            report += "\n"

    await channel.send(report)

@bot.command()
@commands.has_permissions(administrator=True)
async def check_stats(ctx, member: discord.Member):
    """Check stats for a specific user"""
    if str(member.id) in ping_data:
        data = ping_data[str(member.id)]
        embed = discord.Embed(title=f"Stats for {member.name}", color=discord.Color.blue())
        embed.add_field(name="Total Pings", value=str(data['total_pings']))
        for category, count in data['categories'].items():
            embed.add_field(name=category.title(), value=str(count))
        await ctx.send(embed=embed)
    else:
        await ctx.send("No data found for this user.")

# Run the bot
bot.run('YOUR_BOT_TOKEN')