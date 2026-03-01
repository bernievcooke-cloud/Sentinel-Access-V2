import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config.settings import EMAIL_FROM, EMAIL_PASSWORD, SMTP_PORT, SMTP_SERVER


def send_report_email(to_email, username, pdf_paths):
    """
    Send an email with PDF report attachments via SMTP.

    Args:
        to_email (str): Recipient email address.
        username (str): Recipient display name used in the email body.
        pdf_paths (list[str]): Absolute paths to PDF files to attach.

    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_FROM
        msg["To"] = to_email
        msg["Subject"] = "Your Sentinel Access Reports"

        body = (
            f"Hi {username},\n\n"
            "Please find your requested Sentinel Access reports attached.\n\n"
            "Regards,\nSentinel Access"
        )
        msg.attach(MIMEText(body, "plain"))

        for pdf_path in pdf_paths:
            with open(pdf_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{os.path.basename(pdf_path)}"',
                )
                msg.attach(part)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.send_message(msg)

        return True, None

    except Exception as e:
        return False, str(e)
