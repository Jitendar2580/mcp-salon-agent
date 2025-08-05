# database/init.py

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.connection import engine
from database.model import Base

def init_db():
    Base.metadata.create_all(bind=engine)
    print("✅ Appointments table created!")

if __name__ == "__main__":
    init_db()
