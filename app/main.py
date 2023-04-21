import requests
import json
from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session, sessionmaker
from typing import List
from app.database import get_db
from app.models import SenatorTransactionModel
from app.models import Base
from app.database import engine
import re


app = FastAPI()

# Create a SQLite database
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Retrieve the data from the source and insert it into the database
@app.on_event("startup")
async def startup_event():
    response = requests.get('https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions_for_senators.json')
    data = json.loads(response.text)

    session = SessionLocal()
    for senator in data:
        for transaction in senator['transactions']:
            if 'scanned_pdf' not in transaction:
                session.add(SenatorTransactionModel(
                    first_name=senator['first_name'],
                    last_name=senator['last_name'],
                    office=senator['office'],
                    ptr_link=senator['ptr_link'],
                    date_received=senator['date_recieved'],
                    transaction_date=transaction['transaction_date'],
                    owner=transaction['owner'],
                    ticker=transaction['ticker'],
                    asset_description=transaction['asset_description'],
                    asset_type=transaction['asset_type'],
                    transaction_type=transaction['type'],
                    amount=transaction['amount'],
                    comment=transaction['comment'],
                    party=transaction['party'],
                    state=transaction['state'],
                    industry=transaction['industry'],
                    sector=transaction['sector']
                ))
    session.commit()

    # Insert ticker transactions into the database
    response = requests.get('https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_ticker_transactions.json')
    data = json.loads(response.text)

    for ticker_data in data:
        ticker_transactions = ticker_data['transactions']
        for transaction in ticker_transactions:
            ticker_match = re.search(r'>(\w+)<', transaction['ticker'])
            if ticker_match:
                ticker = ticker_match.group(1)
            else:
                ticker = None

            session.add(SenatorTransactionModel(
                first_name=transaction['senator'].split()[0],
                last_name=" ".join(transaction['senator'].split()[1:]),
                office=None,
                ptr_link=transaction['ptr_link'],
                date_received=None,
                transaction_date=transaction['transaction_date'],
                owner=transaction['owner'],
                ticker=ticker,
                asset_description=transaction['asset_description'],
                asset_type=transaction['asset_type'],
                transaction_type=transaction['type'],
                amount=transaction['amount'],
                comment=transaction['comment'],
                party=transaction['party'],
                state=transaction['state'],
                industry=transaction['industry'],
                sector=transaction['sector']
            ))
    session.commit()
    




# Define a GET endpoint that returns all the transactions for a given senator
@app.get('/transactions/senate/{first_name}-{last_name}')
def get_transactions(first_name: str, last_name: str, db: Session = Depends(get_db)):
    transactions = db.query(SenatorTransactionModel).filter_by(first_name=first_name, last_name=last_name).all()
    for transaction in transactions:
        if transaction.ticker is not None:
            ticker_match = re.search(r'>(\w+)<', transaction.ticker)
            if ticker_match:
                transaction.ticker = ticker_match.group(1)
    return [SenatorTransactionModel(**{k: v for k, v in transaction.__dict__.items() if k != '_sa_instance_state'}) for transaction in transactions]

@app.get('/transactions/ticker/{ticker}')
def get_transactions_by_ticker(ticker: str, db: Session = Depends(get_db)):
    transactions = db.query(SenatorTransactionModel).filter_by(ticker=ticker).all()
    return [
        SenatorTransactionModel(
            **{k: v for k, v in transaction.__dict__.items() if k != '_sa_instance_state'}
        )
        for transaction in transactions
    ]

#! Party endpoint
@app.get('/transactions/party/{party}')
def get_transactions_by_party(party: str, db: Session = Depends(get_db)):
    transactions = db.query(SenatorTransactionModel).filter_by(party=party).all()
    return [
        SenatorTransactionModel(
            **{k: v for k, v in transaction.__dict__.items() if k != '_sa_instance_state'}
        )
        for transaction in transactions
    ]

#! State endpoint  
@app.get('/transactions/state/{state}')
def get_transactions_by_state(state: str, db: Session = Depends(get_db)):
    transactions = db.query(SenatorTransactionModel).filter_by(state=state).all()
    return [
        SenatorTransactionModel(
            **{k: v for k, v in transaction.__dict__.items() if k != '_sa_instance_state'}
        )
        for transaction in transactions
    ]

#! Industry endpoint
@app.get('/transactions/party/{party}')
def get_transactions_by_party(party: str, db: Session = Depends(get_db)):
    transactions = db.query(SenatorTransactionModel).filter_by(party=party).all()
    return [
        SenatorTransactionModel(
            **{k: v for k, v in transaction.__dict__.items() if k != '_sa_instance_state'}
        )
        for transaction in transactions
    ]
    
#! Sector endpoint
@app.get('/transactions/sector/{sector}')
def get_transactions_by_sector(sector: str, db: Session = Depends(get_db)):
    transactions = db.query(SenatorTransactionModel).filter_by(sector=sector).all()
    return [
        SenatorTransactionModel(
            **{k: v for k, v in transaction.__dict__.items() if k != '_sa_instance_state'}
        )
        for transaction in transactions
    ]


def get_transactions(first_name: str, last_name: str, db: Session):
    transactions = db.query(SenatorTransactionModel).filter_by(first_name=first_name, last_name=last_name).all()
    for transaction in transactions:
        if transaction.ticker is not None:
            ticker_match = re.search(r'>(\w+)<', transaction.ticker)
            if ticker_match:
                transaction.ticker = ticker_match.group(1)
    return [transaction.__dict__ for transaction in transactions]

def fetch_senator_stock_transactions(first_name: str, last_name: str):
    with SessionLocal() as session:
        transactions = get_transactions(first_name, last_name, session)
    return transactions


@app.get('/transactions/all')
def get_all_transactions(limit: int = 100, db: Session = Depends(get_db)):
    transactions = db.query(SenatorTransactionModel).limit(limit).all()
    for transaction in transactions:
        if transaction.ticker is not None:
            ticker_match = re.search(r'>(\w+)<', transaction.ticker)
            if ticker_match:
                transaction.ticker = ticker_match.group(1)
    return [SenatorTransactionModel(**{k: v for k, v in transaction.__dict__.items() if k != '_sa_instance_state'}) for transaction in transactions]