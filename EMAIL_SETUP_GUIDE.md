# Email Notification Setup Guide

## ✅ Email Feature is Now Implemented!

The code has been updated to support email notifications using SMTP. You can use Gmail, Outlook, Yahoo, or any SMTP-compatible email service.

---

## 📋 Overview

Email notifications send **beautiful HTML-formatted alerts** with:
- 📊 Full details of all new charges and dockets (no truncation like SMS)
- 🎨 Styled tables and color-coded sections
- 📱 Mobile-responsive design
- ✉️ Plain text fallback for email clients that don't support HTML

**Email and SMS work independently** - enable one, both, or neither!

---

## ⚙️ Setup Options

### **Option 1: Gmail (Recommended for Personal Use)**

#### **Step 1: Generate App Password**

Gmail requires an "App Password" (not your regular password):

1. Go to your Google Account: https://myaccount.google.com/
2. Navigate to **Security**
3. Enable **2-Step Verification** (required for app passwords)
4. Go to **App passwords**: https://myaccount.google.com/apppasswords
5. Select app: **Mail**, Select device: **Other** (name it "Docket Monitor")
6. Click **Generate**
7. Copy the 16-character password (format: `xxxx xxxx xxxx xxxx`)

#### **Step 2: Set Environment Variables**

```bash
export EMAIL_SMTP_SERVER="smtp.gmail.com"
export EMAIL_SMTP_PORT="587"
export EMAIL_USERNAME="your-email@gmail.com"
export EMAIL_PASSWORD="xxxx xxxx xxxx xxxx"  # App password from Step 1
export EMAIL_FROM_ADDRESS="your-email@gmail.com"  # Optional, defaults to EMAIL_USERNAME
```

---

### **Option 2: Outlook/Hotmail**

#### **Configuration:**

```bash
export EMAIL_SMTP_SERVER="smtp-mail.outlook.com"
export EMAIL_SMTP_PORT="587"
export EMAIL_USERNAME="your-email@outlook.com"
export EMAIL_PASSWORD="your-password"
export EMAIL_FROM_ADDRESS="your-email@outlook.com"
```

**Note:** Outlook allows regular passwords, but consider using an app-specific password for security.

---

### **Option 3: Yahoo Mail**

#### **Step 1: Generate App Password**

1. Go to: https://login.yahoo.com/myaccount/security/
2. Click **Generate app password**
3. Select **Other App** and name it "Docket Monitor"
4. Copy the generated password

#### **Step 2: Set Environment Variables**

```bash
export EMAIL_SMTP_SERVER="smtp.mail.yahoo.com"
export EMAIL_SMTP_PORT="587"
export EMAIL_USERNAME="your-email@yahoo.com"
export EMAIL_PASSWORD="app-password-here"
export EMAIL_FROM_ADDRESS="your-email@yahoo.com"
```

---

### **Option 4: Custom SMTP Server**

For other email providers or corporate email:

```bash
export EMAIL_SMTP_SERVER="smtp.yourdomain.com"
export EMAIL_SMTP_PORT="587"  # or 465 for SSL, 25 for unencrypted
export EMAIL_USERNAME="your-email@yourdomain.com"
export EMAIL_PASSWORD="your-password"
export EMAIL_FROM_ADDRESS="noreply@yourdomain.com"  # Optional custom sender
```

**Common SMTP Servers:**
- **ProtonMail**: `smtp.protonmail.com` (port 587)
- **iCloud**: `smtp.mail.me.com` (port 587)
- **Zoho**: `smtp.zoho.com` (port 587)
- **FastMail**: `smtp.fastmail.com` (port 587)

---

## 🚀 Configuration

### **Step 1: Update Config File**

Add your email address to the config:

**ricardo.json:**
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

### **Step 2: Set Environment Variables**

For Gmail (example):

```bash
# Add to ~/.bashrc or ~/.zshrc for persistence:
export EMAIL_SMTP_SERVER="smtp.gmail.com"
export EMAIL_SMTP_PORT="587"
export EMAIL_USERNAME="your-email@gmail.com"
export EMAIL_PASSWORD="xxxx xxxx xxxx xxxx"

# Then reload:
source ~/.bashrc
```

**Or** set for one-time use:

```bash
EMAIL_SMTP_SERVER="smtp.gmail.com" \
EMAIL_SMTP_PORT="587" \
EMAIL_USERNAME="your@gmail.com" \
EMAIL_PASSWORD="xxxx xxxx xxxx xxxx" \
python3 deuker-monitor.py -c ricardo.json
```

### **Step 3: Run the Monitor**

```bash
python3 deuker-monitor.py -c ricardo.json
```

---

## 📧 Example Email

When new charges or dockets are found, you'll receive a beautifully formatted email:

### **Email Subject:**
```
🚨 Court Alert: Ricardo Deuker
```

### **Email Body (HTML):**

![Email Preview](https://via.placeholder.com/600x400/f44336/ffffff?text=Court+Alert)

**Features:**
- 🔴 Red header with defendant name
- ⚖️ Orange section for new charges (full list, no truncation)
- 📄 Blue section with table of new dockets
- 📱 Responsive design (looks great on mobile)
- ✉️ Plain text fallback for basic email clients

---

## 🔐 Security Best Practices

### **1. Never Commit Credentials**

```bash
# Add to .gitignore:
echo ".env" >> .gitignore
echo "*.json" >> .gitignore
```

### **2. Use Environment Variables**

Create a `.env` file (not committed to Git):

```bash
# .env
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=your-email@gmail.com
EMAIL_PASSWORD=xxxx xxxx xxxx xxxx
EMAIL_FROM_ADDRESS=your-email@gmail.com
```

Load it before running:

```bash
export $(cat .env | xargs)
python3 deuker-monitor.py -c ricardo.json
```

### **3. Use App-Specific Passwords**

- ✅ **Gmail**: Use App Passwords (required)
- ✅ **Yahoo**: Use App Passwords (recommended)
- ✅ **Outlook**: Use App Passwords or regular password
- ⚠️ **Never** use your main account password in scripts

---

## 🔄 Using Both Email AND SMS

You can enable both notification methods:

**config.json:**
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

**Set all environment variables:**
```bash
# Twilio (SMS)
export TWILIO_ACCOUNT_SID="ACxxx..."
export TWILIO_AUTH_TOKEN="xxx..."
export TWILIO_PHONE_NUMBER="+1234..."

# Email
export EMAIL_SMTP_SERVER="smtp.gmail.com"
export EMAIL_SMTP_PORT="587"
export EMAIL_USERNAME="your@gmail.com"
export EMAIL_PASSWORD="xxxx xxxx xxxx xxxx"

# Run
python3 deuker-monitor.py -c ricardo.json
```

**Result**: You'll get **both** SMS and email for every new charge/docket!

---

## 🛠️ Troubleshooting

### **Error: "Email credentials not found"**

```bash
# Check if variables are set:
echo $EMAIL_SMTP_SERVER
echo $EMAIL_USERNAME
echo $EMAIL_PASSWORD

# If empty, set them:
export EMAIL_SMTP_SERVER="smtp.gmail.com"
export EMAIL_SMTP_PORT="587"
export EMAIL_USERNAME="your@gmail.com"
export EMAIL_PASSWORD="your-app-password"
```

---

### **Error: "Authentication failed" (Gmail)**

**Common causes:**
1. **Not using App Password** - Gmail requires app-specific passwords
2. **2-Step Verification not enabled** - Required for app passwords
3. **Incorrect password format** - Remove spaces: `xxxx xxxx xxxx xxxx` → `xxxxxxxxxxxxxxxx`

**Fix:**
1. Go to: https://myaccount.google.com/apppasswords
2. Generate new app password
3. Use it without spaces in `EMAIL_PASSWORD`

---

### **Error: "SMTPAuthenticationError: Username and Password not accepted"**

**For Gmail:**
- Make sure you're using an **App Password**, not your regular password
- Check that 2-Step Verification is enabled

**For Outlook:**
- Try enabling "Less secure app access" in account settings
- Or use an app-specific password

---

### **Error: "Connection refused" or "Connection timed out"**

**Possible causes:**
1. **Wrong SMTP server or port**
   - Gmail: `smtp.gmail.com:587`
   - Outlook: `smtp-mail.outlook.com:587`
   - Yahoo: `smtp.mail.yahoo.com:587`

2. **Firewall blocking outgoing SMTP**
   - Check firewall settings
   - Try port 465 (SSL) instead of 587 (TLS)

3. **ISP blocks port 25/587**
   - Some ISPs block SMTP ports
   - Use port 465 or contact ISP

---

### **No Email Received**

1. **Check spam/junk folder**
2. **Verify email address is correct** in config.json
3. **Check logs** for errors:
   ```bash
   tail -f docket_monitor.log
   ```
4. **Look for success message**:
   ```
   📧 Email sent to your-email@gmail.com
   ```

---

### **Email Looks Wrong (No Styling)**

- Email client may not support HTML
- Plain text version will be used automatically
- Gmail, Outlook, Apple Mail all support HTML

---

## 💰 Cost

**Email notifications are FREE!**
- No per-message charges
- No subscription fees
- Unlimited emails (within your email provider's limits)

**Gmail limits:**
- 500 emails per day (personal accounts)
- 2,000 emails per day (Google Workspace)

---

## 📊 Comparison: SMS vs Email

| Feature | SMS | Email |
|---------|-----|-------|
| **Cost** | ~$0.008/message | FREE |
| **Speed** | Instant | ~1-5 seconds |
| **Character Limit** | Limited (shows first 3 items) | Unlimited |
| **Formatting** | Plain text | Beautiful HTML |
| **Phone Required** | Yes | No |
| **Setup Complexity** | Twilio account needed | Use existing email |
| **Best For** | Critical instant alerts | Detailed reports |

**Recommendation**: Use **both** for important monitoring!
- SMS: Instant awareness
- Email: Full details and records

---

## ✨ What's Working Now

✅ Email notifications via SMTP
✅ HTML and plain text versions
✅ Beautiful formatting with colors and tables
✅ Configurable per defendant
✅ Works independently or with SMS
✅ Support for Gmail, Outlook, Yahoo, and custom SMTP
✅ Secure app password support
✅ Full error handling and logging

---

## 📝 Example Complete Configuration

**ricardo.json:**
```json
{
  "defendant_first_name": "Ricardo",
  "defendant_last_name": "Deuker",
  "defendant_sex": "Male",
  "poll_interval": 600,
  "notification_sms": "+12345678900",
  "notification_email": "alerts@yourdomain.com"
}
```

**Environment variables:**
```bash
# Email (Gmail)
export EMAIL_SMTP_SERVER="smtp.gmail.com"
export EMAIL_SMTP_PORT="587"
export EMAIL_USERNAME="your@gmail.com"
export EMAIL_PASSWORD="app-password-here"

# SMS (Twilio) - Optional
export TWILIO_ACCOUNT_SID="ACxxx..."
export TWILIO_AUTH_TOKEN="xxx..."
export TWILIO_PHONE_NUMBER="+1234..."
```

**Run:**
```bash
python3 deuker-monitor.py -c ricardo.json
```

---

## Need Help?

Check logs for detailed error messages:
```bash
tail -f docket_monitor.log
```

Look for lines starting with:
- `📧 Email sent to...` (success)
- `⚠️  Email credentials not found...` (missing env vars)
- `❌ Error sending email:...` (SMTP errors)
