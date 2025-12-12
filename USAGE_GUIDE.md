# Miami-Dade Docket Monitor - Quick Start Guide

## What This Script Does

Monitors Ricardo Deuker's court cases in Miami-Dade County and alerts you when new documents are filed on the docket.

## Files Included

1. **deuker-monitor.py** - Main monitoring script
2. **config.json** - Configuration file with your search URL
3. **requirements.txt** - Python dependencies
4. **notification_examples.py** - Templates for email/SMS notifications
5. **quick_test.sh** - Quick test script
6. **README.md** - Full documentation

## Quick Start (5 Minutes)

### Step 1: Install Dependencies

```bash
pip install requests beautifulsoup4
```

### Step 2: Verify Configuration

The `config.json` file is already set up with Ricardo Deuker's search URL:

```json
{
  "search_url": "https://www2.miamidadeclerk.gov/cjis/casesearchinfo?qs=Bw1G3xngi4v...",
  "poll_interval": 600
}
```

### Step 3: Test Run

```bash
# Run once to see current status
python3 deuker-monitor.py -c config.json --once
```

You should see output like:

```
🔍 Running single check...

================================================================================
Check #1 - 2025-11-17 10:30:00
================================================================================
Fetching defendant search results...
Found 4 case(s)
Checking case: F-25-024957
Checking case: F-25-024652
Checking case: F-25-024556
Checking case: F-25-023686

================================================================================
📊 DOCKET SUMMARY
================================================================================
Total Cases Monitored: 4
Total Docket Entries: 48
New Entries This Check: 48

Per-Case Breakdown:
--------------------------------------------------------------------------------
  F-25-024957: 12 entries (12 NEW!)
    Charge: ORGANIZED FRD/O-20K
  F-25-024652: 12 entries (12 NEW!)
    Charge: ORGANIZED FRD/O-20K
  ...
```

**Note:** On first run, all entries are "new" because nothing has been tracked yet.

### Step 4: Start Continuous Monitoring

```bash
# Monitor continuously, check every 10 minutes (600 seconds)
python3 deuker-monitor.py -c config.json
```

The script will now:
- Check every 10 minutes (configurable)
- Alert you to new docket entries
- Save details to JSON files
- Log everything to `docket_monitor.log`

### Step 5: Stop Monitoring

Press `Ctrl+C` to stop the script.

## Understanding the Output

### When New Documents Are Found

```
================================================================================
🔔 FOUND 2 NEW DOCKET ENTRY/ENTRIES!
================================================================================

📋 Case: F-25-024652 (2 new entry/entries)
--------------------------------------------------------------------------------
  Docket #: 13
  Document: MOTION FOR CONTINUANCE
  Filed: 11/15/2025
  Found at: 2025-11-17T10:30:00

  Docket #: 14
  Document: ORDER GRANTING MOTION
  Filed: 11/16/2025
  Found at: 2025-11-17T10:30:00

================================================================================
💾 Details saved to: new_docket_entries_20251117_103000.json
```

### Normal Status Check (No New Documents)

```
Check #5 - 2025-11-17 11:20:00
✓ No new docket entries

📊 DOCKET SUMMARY
Total Cases Monitored: 4
Total Docket Entries: 48
New Entries This Check: 0

⏰ Next check at: 2025-11-17 11:30:00
```

## Customizing the Polling Interval

Edit `config.json`:

```json
{
  "search_url": "...",
  "poll_interval": 300    // 300 = 5 minutes, 600 = 10 minutes, 1800 = 30 minutes
}
```

Or use command line:

```bash
# Check every 5 minutes
python3 deuker-monitor.py -c config.json -i 300
```

## Setting Up Notifications

### Email Notifications

1. Open `notification_examples.py`
2. Find the `_send_email_notification` method
3. Copy it into `deuker-monitor.py` in the `MiamiDadeCourtMonitor` class
4. Update these values:

```python
SENDER_EMAIL = 'your-email@gmail.com'
SENDER_PASSWORD = 'your-gmail-app-password'  # Not your regular password!
RECIPIENT_EMAIL = 'where-to-send@example.com'
```

5. In the `_send_notification` stub, add:

```python
def _send_notification(self, new_entries):
    if new_entries:
        self._send_email_notification(new_entries)
```

**Important for Gmail:**
- You need to use an "App Password", not your regular password
- Enable 2FA first: https://myaccount.google.com/security
- Create app password: https://myaccount.google.com/apppasswords

### SMS Notifications (Twilio)

1. Sign up at https://www.twilio.com (free trial available)
2. Get your Account SID and Auth Token
3. Get a Twilio phone number
4. Copy the `_send_sms_notification` method from `notification_examples.py`
5. Update the configuration values

## Running as a Background Service

### Option 1: Using screen (Simple)

```bash
# Start a screen session
screen -S docket-monitor

# Run the monitor
python3 deuker-monitor.py -c config.json

# Detach from screen: Press Ctrl+A, then D

# Later, reattach to see status
screen -r docket-monitor
```

### Option 2: Using nohup (Simplest)

```bash
# Run in background
nohup python3 deuker-monitor.py -c config.json &

# View output
tail -f nohup.out

# Stop the process
ps aux | grep deuker-monitor.py
kill <PID>
```

### Option 3: As a System Service (Most Robust)

See README.md for systemd service setup instructions.

## Troubleshooting

### "No cases found"

Your search URL may have expired. To get a fresh one:

1. Go to https://www2.miamidadeclerk.gov/cjis/
2. Click "Defendant Search"
3. Search for: Ricardo Deuker
4. Copy the URL from the results page
5. Update `config.json` with the new URL

### Script stops after a while

The search URL has a session token that may expire. Re-run the search on the website and update your config.json.

### Can't see any output

Check the log file:

```bash
tail -f docket_monitor.log
```

### Want to reset and see all entries as "new" again

```bash
rm docket_monitor_data.json
```

Then run the script again.

## File Locations

- **docket_monitor.log** - All activity logs here
- **docket_monitor_data.json** - Tracks what has been seen (don't delete while running)
- **new_docket_entries_TIMESTAMP.json** - Each new finding saved here
- **config.json** - Your configuration

## Best Practices

1. **Check Interval**: 10 minutes (600 seconds) is reasonable for most cases
2. **Log Rotation**: Archive old JSON files monthly
3. **Monitoring**: Run as a service or in screen/tmux for 24/7 monitoring
4. **Notifications**: Set up at least one notification method

## Example Scenarios

### Scenario 1: Monitor During Business Hours Only

Use cron:

```bash
# Edit crontab
crontab -e

# Add: Run Mon-Fri, 8 AM to 5 PM, every 10 minutes
*/10 8-17 * * 1-5 cd /path/to/script && python3 deuker-monitor.py -c config.json --once
```

### Scenario 2: Get Alerted Immediately for New Filings

1. Set poll interval to 5 minutes (300 seconds)
2. Enable SMS notifications via Twilio
3. Run as a background service

### Scenario 3: Daily Summary Email

Modify the script to send a daily summary instead of immediate alerts, or use cron to run once daily and email results.

## Getting Help

1. Check `docket_monitor.log` for detailed error messages
2. Run with `--once` to test without continuous monitoring
3. Verify your search URL is still valid on the website
4. Ensure Python 3.11.9 is installed: `python3 --version`

## Summary

**To start monitoring:**

```bash
python3 deuker-monitor.py -c config.json
```

**To test:**

```bash
python3 deuker-monitor.py -c config.json --once
```

**To run in background:**

```bash
screen -S docket-monitor
python3 deuker-monitor.py -c config.json
# Press Ctrl+A, then D to detach
```

That's it! The script will now monitor all of Ricardo Deuker's cases and alert you when new documents are filed.
