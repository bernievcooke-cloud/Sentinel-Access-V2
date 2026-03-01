# config/settings.py
import os
from dotenv import load_dotenv

load_dotenv()

# File Paths
BASE_PATH = os.getenv("BASE_OUTPUT_PATH", r"C:\OneDrive\Sentinel-Access-v2")
BASE_OUTPUT = os.getenv("BASE_OUTPUT_PATH", r"C:\OneDrive\Sentinel-Access-v2\storage\reports")
BASE_OUTPUT_PATH = os.getenv("BASE_OUTPUT_PATH", r"C:\OneDrive\Sentinel-Access-v2\storage\reports")

# GitHub Configuration
GITHUB_USERNAME=bernievcooke-cloud
GITHUB_REPO=Sentinel2-Access
GITHUB_TOKEN=y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

# Report Types
REPORT_TYPES = os.getenv("REPORT_TYPES", "Surf, Sky, Weather").split(",")

# Email Configuration
SENDER_EMAIL=bernievcooke@gmail.com
SENDER_PASSWORD=kmoaifjbaufxnksf
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587

# Debug mode

DEBUG = os.getenv("DEBUG", "True") == "True"
