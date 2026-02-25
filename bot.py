import discord
import discord.ui
import hashlib
import aiohttp
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timezone
import asyncio
import io
import pandas as pd

# Load configuration from .conf file
def load_config(config_file: str = '.conf') -> dict:
    """Load configuration from JSON file."""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file '{config_file}' not found.")
    except json.JSONDecodeError:
        raise ValueError(f"Configuration file '{config_file}' contains invalid JSON.")

CONFIG = load_config()

# Extract configuration values
PING_LOG_CHANNEL_ID = CONFIG['PING_LOG_CHANNEL_ID']
LFG_CHANNEL_IDS = CONFIG['LFG_CHANNEL_IDS']
ADMINISTRATOR_ROLES = CONFIG['ADMINISTRATOR_ROLES']
LOG_CHANNEL_ID = CONFIG['LOG_CHANNEL_ID']
ROLE_THRESHOLDS = CONFIG['ROLE_THRESHOLDS']
ROLES_EXCEPTIONS = CONFIG.get('ROLES_EXCEPTIONS', [])  # Roles that should not be removed by rolepurge
MD5_CHECK_STATUS = CONFIG['MD5_CHECK_STATUS']
MD5_ACC_AGE_NOTIFICATION_LIMIT = CONFIG['MD5_ACC_AGE_NOTIFICATION_LIMIT']

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


# Data storage
ping_data = {}

# Load existing data
try:
    with open('ping_data.json', 'r') as f:
        ping_data = json.load(f)
except FileNotFoundError:
    pass

# Track recent warning messages to edit if user is banned within 5 seconds
recent_warnings = {}  # {user_id: {"message": discord.Message, "timestamp": datetime}}

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
    
    # Re-add persistent views for any active warning messages
    try:
        for user_id, warning_data in list(recent_warnings.items()):
            if 'member' in warning_data:
                member = warning_data['member']
                bot.add_view(MD5ResponseView(member))
                print(f"[ICON] Re-attached view for warning message user {user_id}")
    except Exception as e:
        print(f"[ICON] Error re-attaching views on ready: {e}")
    
    # Start the presence update task
    if not update_presence.is_running():
        update_presence.start()
        print("[PRESENCE] Uptime presence task started")
    
    # Start the periodic ban check task
    if not check_recent_bans.is_running():
        check_recent_bans.start()
        print("[ICON] Periodic ban check task started")
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

@tasks.loop(seconds=30)  # Update presence every 30 seconds
async def update_presence():
    """Update bot presence to show current uptime."""
    try:
        current_time = datetime.now()
        uptime_duration = current_time - bot_start_time
        days = uptime_duration.days
        hours, remainder = divmod(uptime_duration.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        uptime_str = f"Uptime: {days}d {hours}h {minutes}m"
        activity = discord.Activity(type=discord.ActivityType.watching, name=uptime_str)
        await bot.change_presence(activity=activity)
    except Exception as e:
        print(f"[PRESENCE] Error updating presence: {e}")

@tasks.loop(seconds=1)  # Check for bans every 1 second
async def check_recent_bans():
    """Periodically check if users in recent_warnings have been banned."""
    try:
        for user_id, warning_data in list(recent_warnings.items()):
            elapsed = (datetime.now(timezone.utc) - warning_data["timestamp"]).total_seconds()
            
            # Stop checking after 10 seconds
            if elapsed > 10:
                recent_warnings.pop(user_id, None)
                continue
            
            # Check if user is still in the guild
            member = warning_data.get("member")
            if member and member.guild:
                try:
                    # Try to fetch the user from the guild
                    fetched_member = await member.guild.fetch_member(user_id)
                except discord.NotFound:
                    # User is no longer in the guild (likely banned/removed)
                    # Check the audit log to find who banned them
                    try:
                        async for entry in member.guild.audit_logs(limit=10, action=discord.AuditLogAction.ban):
                            if entry.target.id == user_id:
                                await handle_user_banned(user_id, str(entry.user))
                                print(f"[ICON] Detected ban for user {user_id} by {entry.user} (via periodic check)")
                                break
                    except Exception as e:
                        print(f"[ICON] Failed to check audit log in periodic check: {e}")
                    # Clean up even if we couldn't find the audit log entry
                    recent_warnings.pop(user_id, None)
                except Exception as e:
                    print(f"[ICON] Error checking member {user_id} in periodic ban check: {e}")
    except Exception as e:
        print(f"[ICON] Error in periodic ban check task: {e}")

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


async def log_ban_action(user_id: int, user_name: str, action: str, moderator_id: int, moderator_name: str):
    """Log ban actions to bot_ban_log.txt"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] User ID: {user_id} ({user_name}) | Action: {action} | Moderator ID: {moderator_id} ({moderator_name})\n"
    
    with open('bot_ban_log.txt', 'a', encoding='utf-8') as f:
        f.write(log_entry)


async def handle_user_banned(user_id: int, banned_by_name: str):
    """Edit warning message if one exists for this user and they were banned within 10 seconds."""
    if user_id not in recent_warnings:
        return
    
    warning_data = recent_warnings[user_id]
    elapsed = (datetime.now(timezone.utc) - warning_data["timestamp"]).total_seconds()
    
    # Only edit if within 10 seconds
    if elapsed <= 10:
        message = warning_data["message"]
        try:
            # Edit the message to remove buttons and add "removed by" info
            new_content = message.content.replace("— has default icon", f"— has default icon — removed by {banned_by_name}")
            await message.edit(
                content=new_content,
                view=None
            )
            print(f"[ICON] Updated warning message for banned user {user_id}")
        except Exception as e:
            print(f"[ICON] Failed to edit warning message: {e}")
    
    # Clean up
    recent_warnings.pop(user_id, None)

# MD5 bot check button helper
class MD5ResponseView(discord.ui.View):
    """View with Positive (ban) and Negative (flag) buttons for MD5 matches."""
    
    def __init__(self, member: discord.Member, timeout: int | None = None):
        super().__init__(timeout=timeout)  # timeout=None means buttons never expire
        self.member = member
    
    @discord.ui.button(label="Positive - Ban", style=discord.ButtonStyle.red, emoji="⚠️", custom_id="md5_positive_ban")
    async def positive_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ban the user and log the action."""
        try:
            # Defer the interaction immediately to avoid timeout
            await interaction.response.defer()
            
            # Ban the user
            await self.member.ban(reason=f"MD5 icon match - banned by {interaction.user}")
            
            # Log the action
            await log_ban_action(
                user_id=self.member.id,
                user_name=str(self.member),
                action="BANNED",
                moderator_id=interaction.user.id,
                moderator_name=str(interaction.user)
            )
            
            # Edit warning message if it exists
            await handle_user_banned(self.member.id, str(interaction.user))
            
            # Send confirmation message via followup
            # Add red-square reaction to the original warning message
            await interaction.message.add_reaction("🟥")

            # Send ephemeral confirmation message via followup
            await interaction.followup.send(
                f"✅ User ID {self.member.id} banned",
                ephemeral=True
            )

            # Remove the buttons after action
            await interaction.message.edit(view=None)
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ Failed to ban user: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(label="Negative", style=discord.ButtonStyle.green, emoji="✅", custom_id="md5_negative_flag")
    async def negative_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Add green_square reaction and log the action."""
        try:
            # Defer the interaction immediately to avoid timeout
            await interaction.response.defer()
            
            # Add green_square reaction
            await interaction.message.add_reaction("🟢")
            
            # Log the action
            await log_ban_action(
                user_id=self.member.id,
                user_name=str(self.member),
                action="FLAGGED_NEGATIVE",
                moderator_id=interaction.user.id,
                moderator_name=str(interaction.user)
            )
            
            # Send confirmation message via followup
            await interaction.followup.send(
                f"✅ User marked as not a match",
                ephemeral=True
            )
            
            # Remove the buttons after action
            await interaction.message.edit(view=None)
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ Failed to add reaction: {str(e)}",
                ephemeral=True
            )


@bot.event
async def on_member_remove(member: discord.Member):
    """Check if member was banned and edit warning message if so."""
    if member.id not in recent_warnings:
        return
    
    try:
        # Check audit logs to see if this was a ban
        async for entry in member.guild.audit_logs(limit=10, action=discord.AuditLogAction.ban):
            if entry.target.id == member.id:
                # Found the ban, edit the warning message
                await handle_user_banned(member.id, str(entry.user))
                print(f"[ICON] Detected ban for user {member.id} by {entry.user}")
                return
    except Exception as e:
        print(f"[ICON] Failed to check audit log for ban: {e}")


@bot.event
async def on_member_join(member: discord.Member):
    """On new member join: compute avatar MD5 and post to LOG_CHANNEL_ID if it matches list.txt."""
    try:
        # Check if MD5 checking is enabled
        if not MD5_CHECK_STATUS:
            print(f"[ICON] MD5 checking is disabled (MD5_CHECK_STATUS=False)")
            return
        
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
            age_days = None
            if created:
                # make sure both datetimes are timezone-aware for subtraction
                now = datetime.now(timezone.utc)
                if created.tzinfo is None:
                    # treat created as UTC if naive
                    created = created.replace(tzinfo=timezone.utc)
                delta = now - created
                days = delta.days
                age_days = days
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
            
            # Check if account age exceeds notification limit
            if age_days is not None and age_days >= MD5_ACC_AGE_NOTIFICATION_LIMIT:
                print(f"[ICON] Account age ({age_days} days) exceeds notification limit ({MD5_ACC_AGE_NOTIFICATION_LIMIT} days) - skipping notification")
                return

            # Create view with buttons
            view = MD5ResponseView(member)
            
            # mention the user (preferred) rather than printing plain text
            warning_message = await channel.send(f":warning: {member.id} — {member.mention} — account age: {age_str} — has default icon", view=view)
            
            # Store the message reference to update if user is banned
            recent_warnings[member.id] = {
                "message": warning_message,
                "timestamp": datetime.now(timezone.utc),
                "member": member  # Store member for view persistence on bot restart
            }
        except Exception as e:
            print(f"[ICON] failed to send icon notice to LOG_CHANNEL_ID {LOG_CHANNEL_ID}: {e}")
    except Exception as e:
        print(f"[ICON] error checking member {getattr(member, 'id', 'unknown')}: {e}")

# Slash commands



@bot.tree.command(name="makereport", description="Generate the ping report now")
async def makereport(interaction: discord.Interaction):
    await log_command(interaction, "makereport")
    if not any(role.id in ADMINISTRATOR_ROLES for role in interaction.user.roles):
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
    if not any(role.id in ADMINISTRATOR_ROLES for role in interaction.user.roles):
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
    if not any(role.id in ADMINISTRATOR_ROLES for role in interaction.user.roles):
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



@bot.tree.command(name='md5', description="MD5 utilities: check/add/remove/list/status/acc_age against the icons list")
@discord.app_commands.choices(action=[
    discord.app_commands.Choice(name='check', value='check'),
    discord.app_commands.Choice(name='add', value='add'),
    discord.app_commands.Choice(name='remove', value='remove'),
    discord.app_commands.Choice(name='list', value='list'),
    discord.app_commands.Choice(name='status', value='status'),
    discord.app_commands.Choice(name='acc_age', value='acc_age'),
])
@discord.app_commands.describe(action='Action to perform (check/add/remove/list/status/acc_age)', member='Member to inspect for check', value='MD5 value to add/remove, "on"/"off" for status, or number of days for acc_age')
async def md5(interaction: discord.Interaction, action: str, member: discord.Member | None = None, value: str | None = None):
    await log_command(interaction, "md5")
    if not any(role.id in ADMINISTRATOR_ROLES for role in interaction.user.roles):
        return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
    
    await interaction.response.defer()
    
    # Declare global variables at the start of the function
    global MD5_CHECK_STATUS
    global MD5_ACC_AGE_NOTIFICATION_LIMIT
    
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

    # --- STATUS: toggle MD5_CHECK_STATUS on/off
    if action == 'status':
        if not value:
            # Show current status
            status_text = "enabled" if MD5_CHECK_STATUS else "disabled"
            await interaction.followup.send(f'MD5 checking is currently {status_text}. Use value "on" or "off" to change it.')
            return
        
        normalized_value = value.strip().lower()
        if normalized_value in ['on', 'true', '1', 'yes']:
            new_status = True
        elif normalized_value in ['off', 'false', '0', 'no']:
            new_status = False
        else:
            await interaction.followup.send('Invalid value. Use "on" or "off".', ephemeral=True)
            return
        
        # Update the global variable
        MD5_CHECK_STATUS = new_status
        
        # Update the config file
        CONFIG['MD5_CHECK_STATUS'] = new_status
        with open('.conf', 'w') as f:
            json.dump(CONFIG, f, indent=4)
        
        status_text = "enabled" if new_status else "disabled"
        await interaction.followup.send(f'✅ MD5 checking {status_text}')
        return

    # --- ACC_AGE: set MD5_ACC_AGE_NOTIFICATION_LIMIT
    if action == 'acc_age':
        if not value:
            # Show current limit
            await interaction.followup.send(f'Current account age notification limit: {MD5_ACC_AGE_NOTIFICATION_LIMIT} days. Provide a number to change it.')
            return
        
        try:
            new_limit = int(value.strip())
            if new_limit < 0:
                await interaction.followup.send('Age limit must be a non-negative number.', ephemeral=True)
                return
        except ValueError:
            await interaction.followup.send('Invalid number. Please provide a valid number of days.', ephemeral=True)
            return
        
        # Update the global variable
        MD5_ACC_AGE_NOTIFICATION_LIMIT = new_limit
        
        # Update the config file
        CONFIG['MD5_ACC_AGE_NOTIFICATION_LIMIT'] = new_limit
        with open('.conf', 'w') as f:
            json.dump(CONFIG, f, indent=4)
        
        await interaction.followup.send(f'✅ Account age notification limit set to {new_limit} days')
        return

    await interaction.followup.send('Unknown action. Valid actions: check, add, remove, list, status, acc_age', ephemeral=True)

@bot.tree.command(name="shutdown", description="Shuts down the bot")
async def shutdown(interaction: discord.Interaction):
    await log_command(interaction, "shutdown")
    if not any(role.id in ADMINISTRATOR_ROLES for role in interaction.user.roles):
        return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)

    await interaction.response.send_message("kk bye :(")
    await bot.close()
    print(f'Script closed by {interaction.user}')
    

@bot.tree.command(name="rolepurge", description="Remove all roles except exceptions")
@discord.app_commands.choices(action=[
    discord.app_commands.Choice(name='user', value='user'),
    discord.app_commands.Choice(name='myroles', value='myroles'),
])
@discord.app_commands.describe(action='Action to perform (user/myroles)', user_id='User ID to purge roles from (required for user action)')
async def rolepurge(interaction: discord.Interaction, action: str, user_id: str | None = None):
    """Remove all roles from a user or requester, except those in ROLES_EXCEPTIONS."""
    await log_command(interaction, "rolepurge")
    
    action = action.lower() if action else 'myroles'
    
    # --- USER ACTION: requires admin role
    if action == 'user':
        if not any(role.id in ADMINISTRATOR_ROLES for role in interaction.user.roles):
            return await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        
        if not user_id:
            return await interaction.response.send_message('You must provide a user ID when using action `user`', ephemeral=True)
        
        try:
            target_user_id = int(user_id)
        except ValueError:
            return await interaction.response.send_message('Invalid user ID format. Please provide a numeric user ID.', ephemeral=True)
        
        try:
            member = await interaction.guild.fetch_member(target_user_id)
        except discord.NotFound:
            return await interaction.response.send_message(f'User with ID {target_user_id} not found in this server.', ephemeral=True)
        except Exception as e:
            return await interaction.response.send_message(f'Error fetching user: {str(e)}', ephemeral=True)
        
        await interaction.response.defer()
        
        # Remove all roles except those in ROLES_EXCEPTIONS
        roles_to_remove = [role for role in member.roles if role.id not in ROLES_EXCEPTIONS and role != interaction.guild.default_role]
        
        if not roles_to_remove:
            await interaction.followup.send(f'User {member.mention} has no removable roles.', ephemeral=True)
            return
        
        try:
            for role in roles_to_remove:
                await member.remove_roles(role, reason=f"Rolepurge executed by {interaction.user}")
            
            removed_names = ', '.join([role.name for role in roles_to_remove])
            await interaction.followup.send(
                f'✅ Removed {len(roles_to_remove)} role(s) from {member.mention}: {removed_names}',
                ephemeral=False
            )
        except Exception as e:
            await interaction.followup.send(f'❌ Error removing roles: {str(e)}', ephemeral=True)
        
        return
    
    # --- MYROLES ACTION: executable by anyone, only affects requester
    if action == 'myroles':
        member = interaction.user
        
        await interaction.response.defer()
        
        # Remove all roles except those in ROLES_EXCEPTIONS
        roles_to_remove = [role for role in member.roles if role.id not in ROLES_EXCEPTIONS and role != interaction.guild.default_role]
        
        if not roles_to_remove:
            await interaction.followup.send('You have no removable roles.', ephemeral=True)
            return
        
        try:
            for role in roles_to_remove:
                await member.remove_roles(role, reason="User executed rolepurge myroles")
            
            removed_names = ', '.join([role.name for role in roles_to_remove])
            await interaction.followup.send(
                f'✅ Removed {len(roles_to_remove)} role(s) from you: {removed_names}',
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f'❌ Error removing roles: {str(e)}', ephemeral=True)
        
        return
    
    await interaction.response.send_message('Unknown action. Valid actions: user, myroles', ephemeral=True)


@bot.tree.command(name="export", description="Export the current stats as an Excel file")
async def export_stats(interaction: discord.Interaction):
    await log_command(interaction, "export")
    if not any(role.id in ADMINISTRATOR_ROLES for role in interaction.user.roles):
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