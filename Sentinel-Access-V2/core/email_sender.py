import os
import logging
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config.settings import EMAIL_FROM, EMAIL_PASSWORD, SMTP_PORT, SMTP_SERVER

# Configure logging
logger = logging.getLogger(__name__)

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
    # Input validation
    if not to_email or not isinstance(to_email, str):
        error_msg = "Invalid recipient email address"
        logger.error(error_msg)
        return False, error_msg

    if not pdf_paths or not isinstance(pdf_paths, list):
        error_msg = "pdf_paths must be a non-empty list"
        logger.error(error_msg)
        return False, error_msg

    # Validate PDF files exist
    for pdf_path in pdf_paths:
        if not os.path.isfile(pdf_path):
            error_msg = f"PDF file not found: {pdf_path}"
            logger.error(error_msg)
            return False, error_msg

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
            try:
                with open(pdf_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f'attachment; filename="{os.path.basename(pdf_path)}"',
                    )
                    msg.attach(part)
            except IOError as io_err:
                error_msg = f"Failed to read PDF file {pdf_path}: {str(io_err)}"
                logger.error(error_msg)
                return False, error_msg

        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_FROM, EMAIL_PASSWORD)
                server.send_message(msg)
            logger.info(f"Email successfully sent to {to_email}")
            return True, None

        except smtplib.SMTPAuthenticationError as auth_err:
            error_msg = "SMTP authentication failed - check EMAIL_FROM and EMAIL_PASSWORD"
            logger.error(f"{error_msg}: {str(auth_err)}")
            return False, error_msg
        except smtplib.SMTPException as smtp_err:
            error_msg = f"SMTP error occurred: {str(smtp_err)}"
            logger.error(error_msg)
            return False, error_msg

    except Exception as e:
        error_msg = f"Unexpected error sending email: {str(e)}"
        logger.exception(error_msg)  # Logs full traceback
        return False, error_msg