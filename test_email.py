#!/usr/bin/env python3
"""
Test email notification setup
This script sends a test email to verify your SMTP configuration
"""

import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def test_email_config():
    """Test email configuration"""

    # Get environment variables
    smtp_server = os.environ.get('EMAIL_SMTP_SERVER')
    smtp_port = int(os.environ.get('EMAIL_SMTP_PORT', '587'))
    smtp_username = os.environ.get('EMAIL_USERNAME')
    smtp_password = os.environ.get('EMAIL_PASSWORD')
    from_email = os.environ.get('EMAIL_FROM_ADDRESS', smtp_username)
    to_email = "steven.feltner@gmail.com"

    # Check if all required variables are set
    print("📧 Email Configuration Test")
    print("=" * 60)
    print(f"SMTP Server: {smtp_server or 'NOT SET ❌'}")
    print(f"SMTP Port: {smtp_port}")
    print(f"Username: {smtp_username or 'NOT SET ❌'}")
    print(f"Password: {'***' + smtp_password[-4:] if smtp_password else 'NOT SET ❌'}")
    print(f"From: {from_email or 'NOT SET ❌'}")
    print(f"To: {to_email}")
    print("=" * 60)

    if not all([smtp_server, smtp_username, smtp_password]):
        print("\n❌ Error: Missing required environment variables!")
        print("\nPlease set the following environment variables:")
        print("  export EMAIL_SMTP_SERVER='smtp.gmail.com'")
        print("  export EMAIL_SMTP_PORT='587'")
        print("  export EMAIL_USERNAME='steven.feltner@gmail.com'")
        print("  export EMAIL_PASSWORD='your-app-password-here'")
        print("\n📚 See EMAIL_SETUP_GUIDE.md for instructions on generating Gmail App Password")
        return False

    # Create test message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = "🧪 Test Email from Docket Monitor"
    msg['From'] = from_email
    msg['To'] = to_email

    # Plain text version
    text_body = """
🧪 Test Email from Miami-Dade Docket Monitor

This is a test message to verify your email notification setup.

If you're reading this, your SMTP configuration is working correctly! ✅

Configuration Details:
- SMTP Server: smtp.gmail.com
- SMTP Port: 587
- From: steven.feltner@gmail.com
- To: steven.feltner@gmail.com

You can now use this email address for court docket notifications.

---
Miami-Dade Court Docket Monitor
    """

    # HTML version
    html_body = """
    <html>
      <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background-color: #4CAF50; color: white; padding: 20px; border-radius: 5px 5px 0 0; text-align: center;">
          <h1 style="margin: 0;">🧪 Test Email</h1>
          <p style="margin: 5px 0 0 0;">Miami-Dade Docket Monitor</p>
        </div>
        <div style="padding: 30px; background-color: #f5f5f5; border-radius: 0 0 5px 5px;">
          <div style="background-color: white; padding: 20px; border-radius: 5px; border-left: 4px solid #4CAF50;">
            <h2 style="color: #4CAF50; margin-top: 0;">✅ Configuration Test Successful!</h2>
            <p>If you're reading this, your SMTP configuration is working correctly.</p>
            <p>You can now receive email notifications for court docket updates.</p>
          </div>

          <div style="background-color: white; padding: 20px; margin-top: 15px; border-radius: 5px;">
            <h3 style="margin-top: 0; color: #666;">📋 Configuration Details</h3>
            <table style="width: 100%; border-collapse: collapse;">
              <tr>
                <td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>SMTP Server:</strong></td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">smtp.gmail.com</td>
              </tr>
              <tr>
                <td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>SMTP Port:</strong></td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">587 (TLS)</td>
              </tr>
              <tr>
                <td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>From:</strong></td>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">steven.feltner@gmail.com</td>
              </tr>
              <tr>
                <td style="padding: 8px;"><strong>To:</strong></td>
                <td style="padding: 8px;">steven.feltner@gmail.com</td>
              </tr>
            </table>
          </div>

          <div style="background-color: #fff3cd; padding: 15px; margin-top: 15px; border-radius: 5px; border-left: 4px solid #ffc107;">
            <p style="margin: 0;"><strong>⚠️ Next Steps:</strong></p>
            <ul style="margin: 10px 0 0 0; padding-left: 20px;">
              <li>You can now use <code>steven.json</code> config file</li>
              <li>Run: <code>python3 deuker-monitor.py -c steven.json --once</code></li>
              <li>You'll receive email notifications for new charges and dockets</li>
            </ul>
          </div>
        </div>
        <div style="text-align: center; padding: 15px; color: #999; font-size: 12px;">
          <p>Miami-Dade Court Docket Monitor • Test Email</p>
        </div>
      </body>
    </html>
    """

    # Attach both versions
    part1 = MIMEText(text_body, 'plain')
    part2 = MIMEText(html_body, 'html')
    msg.attach(part1)
    msg.attach(part2)

    # Send email
    try:
        print("\n📤 Attempting to send test email...")
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.set_debuglevel(0)  # Set to 1 for verbose output
            server.starttls()
            print("✓ TLS connection established")

            server.login(smtp_username, smtp_password)
            print("✓ Authentication successful")

            server.sendmail(from_email, to_email, msg.as_string())
            print("✓ Email sent successfully")

        print("\n✅ SUCCESS! Test email sent to steven.feltner@gmail.com")
        print("\nCheck your inbox (and spam folder) for the test email.")
        print("If you received it, your email notifications are working! 🎉")
        return True

    except smtplib.SMTPAuthenticationError as e:
        print("\n❌ Authentication Error!")
        print(f"   {e}")
        print("\n💡 Possible solutions:")
        print("   1. Make sure you're using a Gmail App Password (not your regular password)")
        print("   2. Generate one at: https://myaccount.google.com/apppasswords")
        print("   3. 2-Step Verification must be enabled on your Google account")
        return False

    except smtplib.SMTPException as e:
        print(f"\n❌ SMTP Error: {e}")
        return False

    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_email_config()
    sys.exit(0 if success else 1)
