import sys
import os

# Add Sentinel-Access-V2 to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'Sentinel-Access-V2'))

# Now import and run the Streamlit app
from app import main

if __name__ == '__main__':
    main()