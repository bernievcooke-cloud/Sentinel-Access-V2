# config/settings.py
import os
from dotenv import load_dotenv

load_dotenv()

# File Paths
BASE_PATH = os.getenv("BASE_OUTPUT_PATH", r"C:\OneDrive\Sentinel-Access-v2")
BASE_OUTPUT = os.getenv("BASE_OUTPUT_PATH", r"C:\OneDrive\Sentinel-Access-v2\storage\reports")
BASE_OUTPUT_PATH = os.getenv("BASE_OUTPUT_PATH", r"C:\OneDrive\Sentinel-Access-v2\storage\reports")

# GitHub Configuration
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Report Types
REPORT_TYPES = os.getenv("REPORT_TYPES", "Surf, Sky, Weather").split(",")

# Email Configuration
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

# Debug mode
DEBUG = os.getenv("DEBUG", "True") == "True"

