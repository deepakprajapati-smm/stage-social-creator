"""Run this once to create the database tables"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.models import init_db
engine = init_db()
print("✅ Database initialized")
