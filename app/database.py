from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine


#Postgresql
# engine = create_engine('postgresql://hayden:Tigers07-@10.0.0.34:5432/gov_trades?client_encoding=utf8')
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# SQLite
engine = create_engine('sqlite:///senator_transactions.db')
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
