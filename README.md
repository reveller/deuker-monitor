# Miami-Dade Court Docket Monitor

Automated monitoring system for Miami-Dade Clerk of Court case dockets. Get instant **SMS and/or email notifications** when new charges or docket entries are filed.

## ✨ Features

- 🔍 **Automated Defendant Search** - Monitors specific defendants in Miami-Dade court system
- ⚖️ **Dual Tracking** - Separately tracks charges and docket entries
- 📱 **SMS Notifications** - Instant text alerts via Twilio
- 📧 **Email Notifications** - Beautiful HTML emails with full details
- 👥 **Multi-Defendant Support** - Monitor multiple defendants in one run
- 💾 **Smart State Management** - Only notifies on NEW entries (no duplicates)
- 🤖 **Browser Automation** - Uses Playwright to handle JavaScript-heavy court website
- 📊 **Detailed Reporting** - Track charges, dockets, case counts, and more
- 🔄 **Continuous Monitoring** - Configurable polling intervals
- 📁 **Auto-Generated Filenames** - Separate tracking files per defendant

---

## 📋 Requirements

- Python 3.11+
- Playwright (for browser automation)
- Twilio account (optional, for SMS)
- Email account with SMTP access (optional, for email)

---

## 🚀 Quick Start

### **1. Install Dependencies**

```bash
# Install Python packages
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium
```

### **2. Create Configuration File**

Create `ricardo.json`:

```json
{
  "defendant_first_name": "Ricardo",
  "defendant_last_name": "Deuker",
  "defendant_sex": "Male",
  "poll_interval": 600,
  "notification_sms": "+12345678900",
  "notification_email": "your-email@gmail.com"
}
```

### **3. Set Environment Variables (Optional - for notifications)**

**For SMS (Twilio):**
```bash
export TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export TWILIO_AUTH_TOKEN="your_auth_token_here"
export TWILIO_PHONE_NUMBER="+12345678900"
```

**For Email:**
```bash
export EMAIL_SMTP_SERVER="smtp.gmail.com"
export EMAIL_SMTP_PORT="587"
export EMAIL_USERNAME="your-email@gmail.com"
export EMAIL_PASSWORD="your-app-password"
```

### **4. Run the Monitor**

```bash
# Run once
python3 deuker-monitor.py -c ricardo.json --once

# Continuous monitoring
python3 deuker-monitor.py -c ricardo.json
```

---

## 📖 Usage Examples

### **Monitor Single Defendant**
```bash
python3 deuker-monitor.py -c ricardo.json --once
```

### **Monitor Multiple Defendants**
```bash
python3 deuker-monitor.py -c ricardo.json -c sina.json --once
```

### **Get All Data Without Affecting Tracking**
```bash
# --all implies --once (single run mode)
python3 deuker-monitor.py -c ricardo.json --all
```

### **Continuous Monitoring (Every 10 Minutes)**
```bash
python3 deuker-monitor.py -c ricardo.json
```

### **Command-Line Only (No Config File)**
```bash
python3 deuker-monitor.py --first Ricardo --last Deuker --sex Male --once
```

---

## 📁 File Structure

```
deuker-monitor/
├── deuker-monitor.py              # Main script
├── requirements.txt                # Python dependencies
├── README.md                       # This file
├── USAGE_GUIDE.md                 # Detailed usage guide
├── SMS_SETUP_GUIDE.md             # SMS notification setup
├── EMAIL_SETUP_GUIDE.md           # Email notification setup
├── ricardo.json                    # Example config (defendant 1)
├── sina.json                       # Example config (defendant 2)
├── docket_monitor_deuker_ricardo.json  # Auto-generated tracking data
└── docket_monitor.log             # Log file
```

---

## ⚙️ Configuration Options

### **Config File Format (JSON)**

```json
{
  "defendant_first_name": "Ricardo",        // Required
  "defendant_last_name": "Deuker",          // Required
  "defendant_sex": "Male",                   // Required: Male or Female
  "poll_interval": 600,                      // Seconds between checks
  "notification_sms": "+12345678900",        // Optional: Phone for SMS
  "notification_email": "email@domain.com",  // Optional: Email address
  "data_file": "custom_data.json"            // Optional: Custom tracking file
}
```

### **Environment Variables**

**Twilio (SMS):**
- `TWILIO_ACCOUNT_SID` - Your Twilio Account SID
- `TWILIO_AUTH_TOKEN` - Your Twilio Auth Token
- `TWILIO_PHONE_NUMBER` - Your Twilio phone number (+1XXXXXXXXXX)

**Email (SMTP):**
- `EMAIL_SMTP_SERVER` - SMTP server (e.g., smtp.gmail.com)
- `EMAIL_SMTP_PORT` - SMTP port (587 for TLS, 465 for SSL)
- `EMAIL_USERNAME` - Your email address
- `EMAIL_PASSWORD` - Your email password or app password
- `EMAIL_FROM_ADDRESS` - (Optional) Custom sender address

---

## 📱 Notification Setup

### **SMS Notifications (Twilio)**

See [SMS_SETUP_GUIDE.md](SMS_SETUP_GUIDE.md) for complete instructions.

**Quick Setup:**
1. Sign up at https://www.twilio.com (free $15 credit)
2. Get a phone number
3. Set environment variables
4. Add `notification_sms` to config

**Cost:** ~$0.008 per SMS (~$0.24/month for daily alerts)

---

### **Email Notifications (SMTP)**

See [EMAIL_SETUP_GUIDE.md](EMAIL_SETUP_GUIDE.md) for complete instructions.

**Quick Setup:**
1. Generate app password (Gmail, Yahoo) or use regular password (Outlook)
2. Set environment variables
3. Add `notification_email` to config

**Cost:** FREE (unlimited)

**Supported Providers:**
- Gmail (recommended)
- Outlook/Hotmail
- Yahoo Mail
- ProtonMail
- Any SMTP server

---

## 🔔 Notification Examples

### **SMS (Twilio)**
```
🚨 Court Alert: Ricardo Deuker

⚖️  2 NEW CHARGE(S):
  • ORGANIZED FRD/0-20K
  • GRAND THEFT 3D/C/5K+

📄 7 NEW DOCKET(S):
  • Din 7: REPORT RE: NEBBIA HEARING...
  • Din 6: CURRENT BOND STATUS...
  • Din 5: FIRST APPEARANCE...
  • ...and 4 more
```

### **Email (HTML)**
Beautiful formatted email with:
- Red header with defendant name
- Orange section showing all charges
- Blue section with table of all dockets
- Fully responsive mobile design

---

## 📊 Output Examples

### **Console Output**
```
🔍 Running single check for 1 defendant(s)...

================================================================================
Defendant 1/1: Ricardo Deuker
================================================================================
2025-11-19 10:00:00,000 - INFO - Found 4 case(s)
2025-11-19 10:00:05,000 - INFO - Checking case: F-25-024957 (1/4)
2025-11-19 10:00:10,000 - INFO -   🆕 NEW CHARGE: Seq 1 - ORGANIZED FRD/0-20K
2025-11-19 10:00:10,000 - INFO -   🆕 NEW CHARGE: Seq 2 - GRAND THEFT 3D/C/5K+
2025-11-19 10:00:10,000 - INFO -   🆕 NEW DOCKET: Din 7 - REPORT RE: NEBBIA HEARING...

================================================================================
📊 CASE SUMMARY
================================================================================
Total Cases Monitored: 4
Total Charges: 9
Total Docket Entries: 73
New Charges This Check: 2
New Dockets This Check: 7

Per-Case Breakdown:
--------------------------------------------------------------------------------
  F-25-024957:
    Charges: 2 (2 NEW!)
    Dockets: 7 (7 NEW!)
    First Charge: ORGANIZED FRD/0-20K
================================================================================

✅ All checks complete.
```

---

## 🔧 Command-Line Options

```
usage: deuker-monitor.py [-h] [--first FIRST] [--last LAST] [--sex SEX]
                         [-c CONFIG] [-i INTERVAL] [-d DATA_FILE]
                         [--once] [--all]

Monitor Miami-Dade court dockets for new entries

optional arguments:
  -h, --help            Show help message
  --first FIRST         Defendant first name
  --last LAST           Defendant last name
  --sex SEX             Defendant sex (Male/Female, default: Male)
  -c CONFIG, --config CONFIG
                        JSON config file (can specify multiple)
  -i INTERVAL, --interval INTERVAL
                        Polling interval in seconds (default: 300)
  -d DATA_FILE, --data-file DATA_FILE
                        Data file for tracking (default: auto-generated)
  --once                Run once and exit (no continuous monitoring)
  --all                 Fetch all data without loading/saving state
                        (implies --once, prevents continuous monitoring)
```

---

## 📚 Detailed Guides

- **[USAGE_GUIDE.md](USAGE_GUIDE.md)** - Complete usage documentation
- **[SMS_SETUP_GUIDE.md](SMS_SETUP_GUIDE.md)** - SMS notification setup with Twilio
- **[EMAIL_SETUP_GUIDE.md](EMAIL_SETUP_GUIDE.md)** - Email notification setup with SMTP

---

## 🔒 Security Best Practices

1. **Never commit credentials to Git**
   ```bash
   echo ".env" >> .gitignore
   echo "*.json" >> .gitignore
   ```

2. **Use environment variables for sensitive data**
   - TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
   - EMAIL_USERNAME, EMAIL_PASSWORD

3. **Use app-specific passwords**
   - Gmail: App Passwords (required)
   - Yahoo: App Passwords (recommended)
   - Outlook: App Passwords or regular password

4. **Store configs securely**
   - Don't share config files containing phone numbers/emails
   - Use separate configs per environment (dev, prod)

---

## 🐛 Troubleshooting

### **No cases found**
- Verify defendant name spelling
- Check sex is correct (Male/Female)
- Ensure defendant has active cases in Miami-Dade

### **SMS not working**
- Check Twilio credentials are set correctly
- Verify phone number format: +1XXXXXXXXXX
- Check Twilio Console logs
- See [SMS_SETUP_GUIDE.md](SMS_SETUP_GUIDE.md)

### **Email not working**
- Verify SMTP credentials
- Check spam/junk folder
- Try app-specific password
- See [EMAIL_SETUP_GUIDE.md](EMAIL_SETUP_GUIDE.md)

### **Browser errors**
- Run: `playwright install chromium`
- Check Python version (3.11+ required)

### **Check logs**
```bash
tail -f docket_monitor.log
```

---

## 📊 Data Files

Each defendant gets their own auto-generated tracking file:

**Format:** `docket_monitor_{lastname}_{firstname}.json`

**Example:**
- Ricardo Deuker → `docket_monitor_deuker_ricardo.json`
- Sina Deuker → `docket_monitor_deuker_sina.json`

**Contents:**
```json
{
  "seen_charges": ["hash1", "hash2", ...],
  "seen_dockets": ["hash1", "hash2", ...],
  "case_info": {
    "F-25-024957": {
      "case_number": "F-25-024957",
      "filed_date": "11/17/2025",
      "charge_count": 2,
      "docket_count": 7,
      "last_checked": "2025-11-19T10:00:00.000000"
    }
  },
  "last_updated": "2025-11-19T10:00:00.000000"
}
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

---

## 📄 License

MIT License - See LICENSE file for details

---

## ⚖️ Legal Disclaimer

This tool is for monitoring publicly available court records. Users are responsible for:
- Complying with Miami-Dade Clerk of Court terms of service
- Using reasonable polling intervals to avoid excessive load
- Ensuring legal use of obtained information

**Recommended polling interval:** 10 minutes (600 seconds) or longer

---

## 🆘 Support

For issues or questions:
1. Check the detailed guides (USAGE_GUIDE.md, SMS_SETUP_GUIDE.md, EMAIL_SETUP_GUIDE.md)
2. Review logs: `tail -f docket_monitor.log`
3. Submit an issue on GitHub

---

## 🎯 Roadmap

- ✅ SMS notifications via Twilio
- ✅ Email notifications via SMTP
- ✅ Multi-defendant monitoring
- ✅ Smart state management
- ⏳ Web dashboard
- ⏳ Webhook notifications
- ⏳ Database backend option
- ⏳ Docker containerization

---

**Built with ❤️ for monitoring court cases**
