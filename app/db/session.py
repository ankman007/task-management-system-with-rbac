from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Change this to your actual production database URL (e.g., PostgreSQL) if needed
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

# connect_args={"check_same_thread": False} is ONLY needed for SQLite
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# This is the 'get_db' dependency function you are missing!
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()