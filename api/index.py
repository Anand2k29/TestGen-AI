import sys
import os

# Add project root directory to the sys.path so main can be imported cleanly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
