import discord
import hashlib
import aiohttp
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timezone
import asyncio
import io
import pandas as pd

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
# Icon-checking output channel (predetermined)
LOG_CHANNEL_ID: int | None = 660083489235795978  # channel where icon matches are posted; set to None to disable

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

async def get_avatar_md5(avatar_url: str | None) -> str | None:
    """Fetch avatar asynchronously and compute MD5 hash. Returns None on failure."""
    if not avatar_url:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as resp:
                if resp.status != 200:
                    return None
                content = await resp.read()
                return hashlib.md5(content).hexdigest()
    except Exception:
        # network error or similar
        return None


def load_icons(file_path: str = 'list.txt') -> set[str]:
    """Load MD5 strings from list.txt (one per line) into a set."""
    if not os.path.exists(file_path):
        return set()
    with open(file_path, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f if line.strip())


def add_md5_to_file(md5_value: str, file_path: str = 'list.txt') -> bool:
    """Add an MD5 signature to file_path. Returns True if added, False if it already existed."""
    md5_value = md5_value.strip().lower()
    if not md5_value:
        return False
    icons = load_icons(file_path)
    if md5_value in icons:
        return False
    icons.add(md5_value)
    with open(file_path, 'w', encoding='utf-8') as f:
        for i in sorted(icons):
            f.write(i + '\n')
    return True


def remove_md5_from_file(md5_value: str, file_path: str = 'list.txt') -> bool:
    """Remove an MD5 from file_path. Returns True if removed, False if not found."""
    md5_value = md5_value.strip().lower()
    if not md5_value:
        return False
    icons = load_icons(file_path)
    if md5_value not in icons:
        return False
    icons.remove(md5_value)
    with open(file_path, 'w', encoding='utf-8') as f:
        for i in sorted(icons):
            f.write(i + '\n')
    return True


def export_icons_file(file_path: str = 'list.txt') -> bytes:
    """Return the contents of the icons file as bytes (for sending as a file)."""
    if not os.path.exists(file_path):
        return b''
    with open(file_path, 'rb') as f:
        return f.read()



@bot.event
async def on_member_join(member: discord.Member):
    """On new member join: compute avatar MD5 and post to LOG_CHANNEL_ID if it matches list.txt."""
    try:
        avatar = member.avatar or member.default_avatar or member.display_avatar
        avatar_url = getattr(avatar, 'url', None)

        avatar_md5 = await get_avatar_md5(avatar_url)
        print(f"[ICON] on_member_join: member={getattr(member,'id','?')} avatar_url={avatar_url} md5={avatar_md5}")
        if not avatar_md5:
            return

        icons = load_icons('list.txt')
        print(f"[ICON] loaded {len(icons)} icons from list.txt")
        if avatar_md5 not in icons:
            print(f"[ICON] md5 {avatar_md5} not found in list.txt")
            return

        print(f"[ICON] md5 {avatar_md5} matched list.txt — delivering to LOG_CHANNEL_ID {LOG_CHANNEL_ID}")
        if LOG_CHANNEL_ID is None:
            print("[ICON] LOG_CHANNEL_ID is None — no notification will be sent")
            return

        channel = bot.get_channel(LOG_CHANNEL_ID) or member.guild.get_channel(LOG_CHANNEL_ID)
        if not channel:
            try:
                channel = await bot.fetch_channel(LOG_CHANNEL_ID)
            except Exception as e:
                print(f"[ICON] failed to fetch LOG_CHANNEL_ID {LOG_CHANNEL_ID}: {e}")
                return

        if not isinstance(channel, discord.TextChannel):
            print(f"[ICON] LOG_CHANNEL_ID {LOG_CHANNEL_ID} resolved to non-text channel: {type(channel)}")
            return

        try:
            # Compute account age in a human-friendly form
            created = getattr(member, 'created_at', None)
            age_str = 'unknown'
            if created:
                # make sure both datetimes are timezone-aware for subtraction
                now = datetime.now(timezone.utc)
                if created.tzinfo is None:
                    # treat created as UTC if naive
                    created = created.replace(tzinfo=timezone.utc)
                delta = now - created
                days = delta.days
                if days >= 365:
                    years = days // 365
                    months = (days % 365) // 30
                    age_str = f"{years}y {months}m"
                elif days >= 30:
                    months = days // 30
                    dd = days % 30
                    age_str = f"{months}mo {dd}d"
                elif days > 0:
                    age_str = f"{days}d"
                else:
                    hours = delta.seconds // 3600
                    if hours > 0:
                        age_str = f"{hours}h"
                    else:
                        mins = delta.seconds // 60
                        age_str = f"{mins}m"

            # mention the user (preferred) rather than printing plain text
            await channel.send(f":warning: {member.id} — {member.mention} — account age: {age_str} — has default icon")
        except Exception as e:
            print(f"[ICON] failed to send icon notice to LOG_CHANNEL_ID {LOG_CHANNEL_ID}: {e}")
    except Exception as e:
        print(f"[ICON] error checking member {getattr(member, 'id', 'unknown')}: {e}")

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
    
    # Create a formatted message with the last 10 commands
    log_entries = log_data[-10:]  # Get last 10 entries
    response = "📋 **Last 10 Command Logs**\n\n"
    
    for entry in log_entries:
        response += f"**Command:** /{entry['command']}\n"
        response += f"**User:** {entry['username']} (ID: {entry['user_id']})\n"
        response += f"**Time:** {entry['timestamp']}\n"
        response += "─────────────────\n"
    
    await interaction.response.send_message(response, ephemeral=True)

# Slash command: /md5 <member>
# Returns the MD5 of the supplied member's avatar image (or default avatar).



@bot.tree.command(name='md5', description="MD5 utilities: check/add/remove/list against the icons list")
@discord.app_commands.choices(action=[
    discord.app_commands.Choice(name='check', value='check'),
    discord.app_commands.Choice(name='add', value='add'),
    discord.app_commands.Choice(name='remove', value='remove'),
    discord.app_commands.Choice(name='list', value='list'),
])
@discord.app_commands.describe(action='Action to perform (check/add/remove/list)', member='Member to inspect for check', value='MD5 value to add/remove')
async def md5(interaction: discord.Interaction, action: str, member: discord.Member | None = None, value: str | None = None):
    await log_command(interaction, "md5")
    if not any(role.id in ADMINITARTOR_ROLES for role in interaction.user.roles):
        return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
    
    await interaction.response.defer()
    
    # Action-based handling
    action = action.lower() if action else 'check'

    # --- CHECK: compute avatar md5 for given member
    if action == 'check':
        if not member:
            await interaction.followup.send('You must supply a member when using action `check`', ephemeral=True)
            return
        avatar = member.avatar or member.default_avatar or member.display_avatar
        avatar_url = getattr(avatar, 'url', None)
        avatar_md5 = await get_avatar_md5(avatar_url)
        if not avatar_md5:
            await interaction.followup.send(f'Could not fetch avatar for user {member.id}')
            return
        await interaction.followup.send(f'{member.id} avatar MD5: {avatar_md5}')
        return

    # --- ADD: add a new MD5 value to list.txt
    if action == 'add':
        if not value:
            await interaction.followup.send('You must provide an MD5 value to add (use the `value` parameter)', ephemeral=True)
            return
        normalized = value.strip().lower()
        if len(normalized) != 32 or not all(c in '0123456789abcdef' for c in normalized):
            await interaction.followup.send('Provided value does not look like a valid MD5 (32 hex chars).', ephemeral=True)
            return
        added = add_md5_to_file(normalized, 'list.txt')
        if added:
            await interaction.followup.send(f'Added MD5 to list: {normalized}')
        else:
            await interaction.followup.send(f'MD5 already present: {normalized}')
        return

    # --- REMOVE: remove an MD5 value from list.txt
    if action == 'remove':
        if not value:
            await interaction.followup.send('You must provide an MD5 value to remove (use the `value` parameter)', ephemeral=True)
            return
        normalized = value.strip().lower()
        removed = remove_md5_from_file(normalized, 'list.txt')
        if removed:
            await interaction.followup.send(f'Removed MD5 from list: {normalized}')
        else:
            await interaction.followup.send(f'MD5 not found in list: {normalized}')
        return

    # --- LIST: export list.txt as a file
    if action == 'list':
        data = export_icons_file('list.txt')
        if not data:
            await interaction.followup.send('icons list is empty or file not found')
            return
        import io
        buf = io.BytesIO(data)
        buf.seek(0)
        file = discord.File(fp=buf, filename='list.txt')
        await interaction.followup.send('Here is the current icons list:', file=file)
        return

    await interaction.followup.send('Unknown action. Valid actions: check, add, remove, list', ephemeral=True)

@bot.tree.command(name="shutdown", description="Shuts down the bot")
async def shutdown(interaction: discord.Interaction):
    await log_command(interaction, "shutdown")
    if not any(role.id in ADMINITARTOR_ROLES for role in interaction.user.roles):
        return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)

    await interaction.response.send_message("kk bye :(")
    await bot.close()
    print(f'Script closed by {interaction.user}')
    

@bot.tree.command(name="export", description="Export the current stats as an Excel file")
async def export_stats(interaction: discord.Interaction):
    await log_command(interaction, "export")
    if not any(role.id in ADMINITARTOR_ROLES for role in interaction.user.roles):
        return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)

    try:
        
        # Create a list to store the data for each user
        data_rows = []
        
        # Iterate through each user's data
        for user_id, data in ping_data.items():
            user = bot.get_user(int(user_id))
            nickname = user.name if user else "Unknown User"
            
            # Create a row with user info and all category counts
            row = {
                'User ID': user_id,
                'Nickname': nickname,
                'Total Pings': data['total_pings']
            }
            # Add all category counts
            row.update(data['categories'])
            
            data_rows.append(row)
        
        # Create DataFrame
        df = pd.DataFrame(data_rows)
        
        # Save to BytesIO buffer
        excel_buffer = io.BytesIO()
        df.to_excel(excel_buffer, index=False)
        excel_buffer.seek(0)
        
        # Create Discord file
        file = discord.File(
            fp=excel_buffer,
            filename="ping_stats.xlsx"
        )
        
        await interaction.response.send_message(
            "Here are the current stats in Excel format:",
            file=file,
            ephemeral=True
        )
        
    except Exception as e:
        await interaction.response.send_message(
            f"An error occurred while generating the Excel file: {str(e)}",
            ephemeral=True
        )


with open(".env", "r") as f:
    token = f.read().strip()

bot.run(token)