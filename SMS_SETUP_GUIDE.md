# SMS Notification Setup Guide

## ✅ SMS Feature is Now Implemented!

The code has been updated to support SMS notifications via Twilio. Here's what you need to complete the setup:

---

## 📋 Requirements

### 1. **Install Twilio Library**
```bash
pip install twilio
# Or install all requirements:
pip install -r requirements.txt
```

### 2. **Create a Twilio Account**

1. Go to https://www.twilio.com/try-twilio
2. Sign up for a free account
3. Verify your phone number
4. **Free Trial includes:**
   - $15 credit (enough for ~1,900 SMS messages)
   - Can only send to verified phone numbers during trial
   - Messages will have "Sent from your Twilio trial account" prefix

### 3. **Get Your Twilio Credentials**

After signing up, you'll need these 3 values from the Twilio Console:

1. **Account SID** - Found on the dashboard (looks like: `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)
2. **Auth Token** - Found on the dashboard (click to reveal)
3. **Twilio Phone Number** - Get one from: Console → Phone Numbers → Buy a number
   - Choose a US number (free during trial)
   - Format: `+12345678900` (must include country code)

---

## ⚙️ Configuration

### **Step 1: Set Environment Variables**

Set these environment variables with your Twilio credentials:

```bash
# Linux/Mac (add to ~/.bashrc or ~/.zshrc for persistence)
export TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export TWILIO_AUTH_TOKEN="your_auth_token_here"
export TWILIO_PHONE_NUMBER="+12345678900"

# Or for one-time use:
TWILIO_ACCOUNT_SID="ACxxx..." TWILIO_AUTH_TOKEN="xxx..." TWILIO_PHONE_NUMBER="+1234..." python3 deuker-monitor.py -c ricardo.json
```

### **Step 2: Update Config File**

Add your recipient phone number to your config file:

**ricardo.json:**
```json
{
  "defendant_first_name": "Ricardo",
  "defendant_last_name": "Deuker",
  "defendant_sex": "Male",
  "poll_interval": 600,
  "notification_sms": "+12345678900",
  "notification_email": ""
}
```

**Important:**
- Phone number MUST be in E.164 format: `+[country code][number]`
- US example: `+12125551234`
- During trial: This number must be verified in your Twilio account

---

## 🚀 Usage

### **Run with SMS Notifications:**
```bash
# Make sure environment variables are set
export TWILIO_ACCOUNT_SID="ACxxx..."
export TWILIO_AUTH_TOKEN="xxx..."
export TWILIO_PHONE_NUMBER="+1234..."

# Run monitor
python3 deuker-monitor.py -c ricardo.json
```

### **Test SMS (without affecting tracking):**
```bash
# Clear tracking data to trigger new notifications
rm docket_monitor_deuker_ricardo.json

# Run once
python3 deuker-monitor.py -c ricardo.json --once
```

---

## 📱 Example SMS Messages

When new charges or dockets are found, you'll receive messages like:

```
🚨 Court Alert: Ricardo Deuker

⚖️  2 NEW CHARGE(S):
  • ORGANIZED FRD/0-20K
  • GRAND THEFT 3D/C/5K+

📄 7 NEW DOCKET(S):
  • Din 7: REPORT RE: NEBBIA HEARING SET FOR 11/18/2025
  • Din 6: CURRENT BOND STATUS PC FOUND CT1 1K CT2 1500...
  • Din 5: FIRST APPEARANCE/BOND HEARING - P.M.
  • ...and 4 more
```

---

## 💰 Cost

### **Twilio Pricing (as of 2024):**
- **SMS (US)**: ~$0.0079 per message
- **Free Trial**: $15 credit (~1,900 messages)
- **Pay-as-you-go**: Only charged when messages are sent

### **Example Monthly Cost:**
- Checking every 10 minutes (144 checks/day)
- If 1 new docket per day: ~30 SMS/month = **$0.24/month**
- If 10 new entries per week: ~40 SMS/month = **$0.32/month**

---

## 🛠️ Troubleshooting

### **Error: "Twilio library not installed"**
```bash
pip install twilio
```

### **Error: "Twilio credentials not found"**
```bash
# Check if environment variables are set:
echo $TWILIO_ACCOUNT_SID
echo $TWILIO_AUTH_TOKEN
echo $TWILIO_PHONE_NUMBER

# If empty, set them:
export TWILIO_ACCOUNT_SID="ACxxx..."
export TWILIO_AUTH_TOKEN="xxx..."
export TWILIO_PHONE_NUMBER="+1234..."
```

### **Error: "Unable to create record: The number +1234... is unverified"**
- During trial, you can only send to verified numbers
- Go to Twilio Console → Phone Numbers → Verified Caller IDs
- Add and verify your recipient phone number

### **No SMS Received:**
1. Check Twilio Console → Monitor → Logs → Messaging for delivery status
2. Verify phone number format (+1XXXXXXXXXX)
3. Check spam/blocked messages on your phone
4. Ensure environment variables are set correctly

---

## 🔄 Upgrade from Trial to Paid

To remove "trial account" message and send to any number:

1. Go to Twilio Console → Billing
2. Add payment method
3. Upgrade account (no monthly fees, pay-per-use only)

---

## 🔐 Security Best Practices

**Never commit credentials to Git!**

```bash
# Add to .gitignore:
echo ".env" >> .gitignore
echo "*.json" >> .gitignore  # If config contains sensitive data

# Use .env file (optional):
# Create .env file with:
TWILIO_ACCOUNT_SID=ACxxx...
TWILIO_AUTH_TOKEN=xxx...
TWILIO_PHONE_NUMBER=+1234...

# Load in shell:
export $(cat .env | xargs)
```

---

## ✨ What's Working Now

✅ SMS notifications via Twilio
✅ Configurable recipient per defendant
✅ Smart message formatting (limited to first 3 items for SMS)
✅ Automatic deduplication (only notifies on NEW entries)
✅ Error handling and logging
⏳ Email notifications (placeholder, not yet implemented)

---

## 📧 Email Notifications (Coming Soon)

Email support is planned but not yet implemented. To add:
- Use SMTP (Gmail, Outlook) or service (SendGrid, Mailgun)
- Configure `notification_email` in config.json
- Implementation needed in `_send_notification()` method

---

## Need Help?

Check logs for detailed error messages:
```bash
tail -f docket_monitor.log
```

Look for lines starting with:
- `📱 SMS sent to...` (success)
- `⚠️  Twilio credentials not found...` (missing env vars)
- `❌ Error sending SMS:...` (Twilio errors)
