#!/usr/bin/env python3
"""
Notification Examples for Miami-Dade Docket Monitor

Add these methods to the MiamiDadeCourtMonitor class to enable notifications.
"""

# ============================================================================
# EMAIL NOTIFICATION (Gmail Example)
# ============================================================================

def _send_email_notification(self, new_entries):
    """Send email notification using Gmail SMTP"""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    # Configuration
    SMTP_SERVER = 'smtp.gmail.com'
    SMTP_PORT = 587
    SENDER_EMAIL = 'your-email@gmail.com'
    SENDER_PASSWORD = 'your-app-password'  # Use App Password, not regular password
    RECIPIENT_EMAIL = 'recipient@example.com'
    
    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'🔔 {len(new_entries)} New Court Docket Entry/Entries'
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECIPIENT_EMAIL
        
        # Create text body
        text_parts = ['New Court Docket Entries Found:\n\n']
        for entry in new_entries:
            text_parts.append(f"Case: {entry.case_number}\n")
            text_parts.append(f"Docket #: {entry.sequence_number}\n")
            text_parts.append(f"Document: {entry.document_name}\n")
            text_parts.append(f"Filed: {entry.filing_date}\n")
            text_parts.append('-' * 60 + '\n\n')
        
        text_body = ''.join(text_parts)
        
        # Create HTML body
        html_parts = ['<html><body><h2>New Court Docket Entries</h2>']
        for entry in new_entries:
            html_parts.append('<div style="border: 1px solid #ccc; padding: 10px; margin: 10px 0;">')
            html_parts.append(f'<strong>Case:</strong> {entry.case_number}<br>')
            html_parts.append(f'<strong>Docket #:</strong> {entry.sequence_number}<br>')
            html_parts.append(f'<strong>Document:</strong> {entry.document_name}<br>')
            html_parts.append(f'<strong>Filed:</strong> {entry.filing_date}<br>')
            html_parts.append('</div>')
        html_parts.append('</body></html>')
        
        html_body = ''.join(html_parts)
        
        # Attach both versions
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        
        # Send email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        
        self.logger.info(f"📧 Email sent to {RECIPIENT_EMAIL}")
        
    except Exception as e:
        self.logger.error(f"Error sending email: {e}")


# ============================================================================
# SMS NOTIFICATION (Twilio Example)
# ============================================================================

def _send_sms_notification(self, new_entries):
    """Send SMS notification using Twilio"""
    from twilio.rest import Client
    
    # Configuration
    TWILIO_ACCOUNT_SID = 'your_account_sid'
    TWILIO_AUTH_TOKEN = 'your_auth_token'
    TWILIO_PHONE = '+1234567890'  # Your Twilio number
    RECIPIENT_PHONE = '+1234567890'  # Recipient number
    
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Create message text (SMS has character limits)
        if len(new_entries) == 1:
            entry = new_entries[0]
            message_text = (f"New docket entry in {entry.case_number}: "
                          f"#{entry.sequence_number} - {entry.document_name[:50]}")
        else:
            message_text = f"Found {len(new_entries)} new docket entries. Check email for details."
        
        # Send SMS
        message = client.messages.create(
            body=message_text,
            from_=TWILIO_PHONE,
            to=RECIPIENT_PHONE
        )
        
        self.logger.info(f"📱 SMS sent: {message.sid}")
        
    except Exception as e:
        self.logger.error(f"Error sending SMS: {e}")


# ============================================================================
# WEBHOOK NOTIFICATION (Generic HTTP POST)
# ============================================================================

def _send_webhook_notification(self, new_entries):
    """Send notification via webhook (e.g., Slack, Discord, IFTTT)"""
    import requests
    
    # Configuration
    WEBHOOK_URL = 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
    
    try:
        # Format for Slack
        text = f"🔔 *{len(new_entries)} New Court Docket Entry/Entries*\n\n"
        for entry in new_entries:
            text += f"*Case:* {entry.case_number}\n"
            text += f"*Docket #:* {entry.sequence_number}\n"
            text += f"*Document:* {entry.document_name}\n"
            text += f"*Filed:* {entry.filing_date}\n"
            text += "─" * 40 + "\n\n"
        
        payload = {
            "text": text,
            "username": "Docket Monitor",
            "icon_emoji": ":bell:"
        }
        
        response = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        
        self.logger.info(f"🌐 Webhook sent successfully")
        
    except Exception as e:
        self.logger.error(f"Error sending webhook: {e}")


# ============================================================================
# DISCORD WEBHOOK
# ============================================================================

def _send_discord_notification(self, new_entries):
    """Send notification to Discord channel"""
    import requests
    
    # Configuration
    DISCORD_WEBHOOK_URL = 'https://discord.com/api/webhooks/YOUR/WEBHOOK'
    
    try:
        # Create embed
        embeds = []
        for entry in new_entries:
            embed = {
                "title": f"New Docket Entry - {entry.case_number}",
                "color": 0xFF5733,  # Orange color
                "fields": [
                    {"name": "Docket #", "value": entry.sequence_number, "inline": True},
                    {"name": "Filed Date", "value": entry.filing_date, "inline": True},
                    {"name": "Document", "value": entry.document_name, "inline": False}
                ],
                "timestamp": entry.timestamp_found
            }
            embeds.append(embed)
        
        payload = {
            "content": f"🔔 **{len(new_entries)} New Court Docket Entry/Entries**",
            "embeds": embeds[:10]  # Discord limits to 10 embeds
        }
        
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        
        self.logger.info(f"💬 Discord notification sent")
        
    except Exception as e:
        self.logger.error(f"Error sending Discord notification: {e}")


# ============================================================================
# PUSHOVER NOTIFICATION
# ============================================================================

def _send_pushover_notification(self, new_entries):
    """Send push notification via Pushover"""
    import requests
    
    # Configuration
    PUSHOVER_TOKEN = 'your_app_token'
    PUSHOVER_USER = 'your_user_key'
    
    try:
        message = f"Found {len(new_entries)} new docket entry/entries:\n\n"
        for entry in new_entries[:3]:  # Limit to first 3
            message += f"{entry.case_number} #{entry.sequence_number}: {entry.document_name}\n"
        
        if len(new_entries) > 3:
            message += f"\n...and {len(new_entries) - 3} more"
        
        payload = {
            "token": PUSHOVER_TOKEN,
            "user": PUSHOVER_USER,
            "message": message,
            "title": "New Court Docket Entries",
            "priority": 1,  # High priority
            "sound": "pushover"
        }
        
        response = requests.post('https://api.pushover.net/1/messages.json', 
                                data=payload, timeout=10)
        response.raise_for_status()
        
        self.logger.info(f"📲 Pushover notification sent")
        
    except Exception as e:
        self.logger.error(f"Error sending Pushover notification: {e}")


# ============================================================================
# COMBINED NOTIFICATION METHOD
# ============================================================================

def _send_notification(self, new_entries):
    """
    Master notification method - calls all enabled notification methods
    
    Replace the stub _send_notification method in the main script with this.
    """
    if not new_entries:
        return
    
    self.logger.info(f"Sending notifications for {len(new_entries)} new entries")
    
    # Uncomment the methods you want to use:
    
    # self._send_email_notification(new_entries)
    # self._send_sms_notification(new_entries)
    # self._send_webhook_notification(new_entries)
    # self._send_discord_notification(new_entries)
    # self._send_pushover_notification(new_entries)
    
    pass


# ============================================================================
# INSTALLATION NOTES
# ============================================================================
"""
To use these notifications:

1. Install additional dependencies as needed:
   pip install twilio          # For SMS
   pip install requests         # For webhooks (usually already installed)

2. Copy the desired notification method(s) into the MiamiDadeCourtMonitor class

3. Update the configuration values (API keys, webhooks, etc.)

4. Replace the _send_notification stub with the combined method above

5. Uncomment the notification methods you want to use

For Gmail:
- Use an "App Password" not your regular password
- Enable 2FA and create app password at: https://myaccount.google.com/apppasswords

For Twilio:
- Sign up at https://www.twilio.com
- Get your Account SID and Auth Token
- Purchase a phone number

For Slack:
- Create an incoming webhook: https://api.slack.com/messaging/webhooks

For Discord:
- Server Settings → Integrations → Webhooks → New Webhook
"""
