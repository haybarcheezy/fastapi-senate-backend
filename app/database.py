from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

engine = create_engine('sqlite:///senator_transactions.db')
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# prod
# engine = create_engine('postgresql://postgres:Tigers07-@10.0.0.34:5432/fastapi_senate_prod')
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()