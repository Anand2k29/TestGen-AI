import sys
import os

# Add root folder to sys.path so api folder is resolvable
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.index import app