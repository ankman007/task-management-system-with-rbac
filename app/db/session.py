import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()  

# 1. Fallback to local SQLite only if DATABASE_URL isn't found in the environment
DEFAULT_SQLITE_URL = "sqlite:///./test.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)

# 2. Dynamically configure engine arguments based on the database type
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

# 3. Create the engine safely
engine = create_engine(DATABASE_URL, connect_args=connect_args)

# 4. Create the session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# 5. Dependency injection generator for FastAPI endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()