from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

# SQLite
engine = create_engine('sqlite:///senator_transactions.db')
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
