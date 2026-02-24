# LOTR Vanity Tracker Bot

## Description

This is a Discord bot that tracks vanity metrics and manages user roles based on achievement thresholds. The bot monitors user activity, logs commands, and performs avatar MD5 checking for security purposes.

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Steps

1. Clone the repository or download the project files

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

3. Configure the bot token in `.env` and channel/role IDs in `.conf` with your Discord server settings

4. Run the bot:
```bash
python bot.py
```

## Configuration (`.conf`)

The `.conf` file is a JSON configuration file that contains the following settings:

- `PING_LOG_CHANNEL_ID`: Channel ID for ping notifications
- `LFG_CHANNEL_IDS`: Array of LFG (Looking For Group) channel IDs to monitor
- `ADMINISTRATOR_ROLES`: Array of role IDs with administrator permissions
- `LOG_CHANNEL_ID`: Channel ID for logging avatar MD5 matches
- `ROLE_THRESHOLDS`: Dictionary defining role categories and ping thresholds
- `ROLES_EXCEPTIONS`: Array of role IDs that should not be removed by rolepurge
- `MD5_CHECK_STATUS`: Boolean to enable/disable avatar MD5 checking (default: `true`)
- `MD5_ACC_AGE_NOTIFICATION_LIMIT`: Number of days - only accounts younger than this will trigger notifications (default: `365`)

## Commands

### Ping Tracking
- `/makereport` - Generate the current ping report
- `/checkstats <member>` - View ping statistics for a specific user
- `/mystats` - View your own ping statistics

### MD5 Avatar Utilities
- `/md5 check <member>` - Get the MD5 hash of a user's avatar
- `/md5 add <value>` - Add an MD5 hash to the blocklist
- `/md5 remove <value>` - Remove an MD5 hash from the blocklist
- `/md5 list` - Export the current MD5 blocklist as a file
- `/md5 status [on/off]` - Toggle MD5 checking or view current status
- `/md5 acc_age [days]` - Set account age notification limit or view current limit

### Role Management
- `/rolepurge user <user_id>` - Remove all non-exception roles from a user
- `/rolepurge myroles` - Remove all of your non-exception roles

### Utility
- `/uptime` - Show how long the bot has been running
- `/viewlogs` - View recent command usage logs
- `/export` - Export current stats as an Excel file
- `/shutdown` - Shut down the bot (admin only)

## Avatar MD5 Checking

The bot automatically checks new members' avatars against a blocklist (`list.txt`). When a match is found:

1. The bot posts a notification to the configured `LOG_CHANNEL_ID`
2. Only accounts younger than `MD5_ACC_AGE_NOTIFICATION_LIMIT` days trigger notifications
3. Moderators can respond with:
   - **Positive - Ban** (🔴): Bans the user and logs the action
   - **Negative** (✅): Marks as false positive and logs the action

The feature can be toggled on/off using `/md5 status` and the age limit can be configured with `/md5 acc_age`.

## Future Improvements

Configurable metrics (right now it's all manual .conf setup in the root directory, wanna at some point streamline it but ¯\(°_o)/¯ yolo)
Custom bot status for funzies (maybe with uptime as a game time, i dunno..)
