import requests
import json
from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session, sessionmaker
from typing import List
from app.database import get_db
from app.models import SenatorTransactionModel, AllSenateTransactionModel, AllHouseTransactionModel, TickerTransactionModel
from app.models import Base
from app.database import engine
import re
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func
import datetime

app = FastAPI()

origins = [
    "http://localhost",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
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
                # Check if transaction already exists in the database
                existing_transaction = session.query(SenatorTransactionModel).filter_by(
                    owner=transaction['owner'],
                    transaction_date=transaction['transaction_date'],
                    ticker=transaction['ticker']
                ).first()
                if existing_transaction is not None:
                    continue  # Skip this transaction if it already exists
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

    # Insert new ticker transactions into the database
    ticker_response = requests.get('https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_ticker_transactions.json')
    tdata = json.loads(ticker_response.text)

    for ticker_data in tdata:
        ticker_transactions = ticker_data['transactions']
        for transaction in ticker_transactions:
            ticker_match = re.search(r'>(\w+)<', transaction['ticker'])
            if ticker_match:
                ticker = ticker_match.group(1)
            else:
                ticker = None
            # Check if transaction already exists in the database
            existing_transaction = session.query(TickerTransactionModel).filter_by(
                owner=transaction['owner'],
                transaction_date=transaction['transaction_date'],
                ticker=ticker
            ).first()
            if existing_transaction is not None:
                continue  # Skip this transaction if it already exists
            session.add(TickerTransactionModel(
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
    
    senate_url = 'https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json'
    senate_response = requests.get(senate_url)
    senate_data = json.loads(senate_response.text)
    senate_sorted_transactions = sorted(senate_data, key=lambda x: datetime.datetime.strptime(x['transaction_date'], '%m/%d/%Y'), reverse=True)

    session = SessionLocal()

    for transaction in senate_sorted_transactions:
        if 'scanned_pdf' not in transaction:
            if session.query(AllSenateTransactionModel).filter_by(
                    senator=transaction['senator'],
                    ptr_link=transaction['ptr_link'],
                    transaction_date=transaction['transaction_date'],
                    owner=transaction['owner'],
                    ticker=transaction['ticker'],
                    asset_description=transaction['asset_description'],
                    asset_type=transaction['asset_type'],
                    transaction_type=transaction['type'],
                    amount=transaction['amount'],
                    comment=transaction.get('comment'),
                    party=transaction.get('party'),
                    state=transaction.get('state'),
                    industry=transaction.get('industry'),
                    sector=transaction.get('sector')
                ).count() == 0:
                session.add(AllSenateTransactionModel(
                    senator=transaction['senator'],
                    ptr_link=transaction['ptr_link'],
                    transaction_date=transaction['transaction_date'],
                    owner=transaction['owner'],
                    ticker=transaction['ticker'],
                    asset_description=transaction['asset_description'],
                    asset_type=transaction['asset_type'],
                    transaction_type=transaction['type'],
                    amount=transaction['amount'],
                    comment=transaction.get('comment'),
                    party=transaction.get('party'),
                    state=transaction.get('state'),
                    industry=transaction.get('industry'),
                    sector=transaction.get('sector')
                ))
    session.commit()

        
    house_url = 'https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json'
    house_response = requests.get(house_url)
    house_data = json.loads(house_response.text)
    house_sorted_transactions = []
    type_map = {'sale_partial': 'Sale (Partial)', 'sale_full': 'Sale (Full)', 'purchase': 'Purchase', 'exchange': 'Exchange'}

    with SessionLocal() as session:
        for transaction in house_data:
            try:
                transaction_date = datetime.datetime.strptime(transaction['transaction_date'], '%Y-%m-%d')
                transaction_type = transaction['type']
                if transaction_type in type_map:
                    transaction_type = type_map[transaction_type]
                else:
                    print(f"Warning: Unknown transaction type {transaction_type}. Saving as-is.")
                transaction['transaction_date'] = transaction_date.strftime('%m/%d/%Y')
                transaction['transaction_type'] = transaction_type
                house_sorted_transactions.append(transaction)
            except ValueError:
                print(f"Error: Invalid transaction date format: {transaction['transaction_date']}. Skipping transaction.")
                continue

        for transaction in house_sorted_transactions:
            if 'scanned_pdf' not in transaction:
                # Check if a record with the same transaction date and ticker already exists in the database
                existing_record = session.query(AllHouseTransactionModel).filter_by(transaction_date=transaction['transaction_date'], ticker=transaction['ticker']).first()
                if existing_record:
                    continue # Skip this transaction if it already exists in the database
                session.add(AllHouseTransactionModel(
                    transaction_date=transaction['transaction_date'],
                    representative=transaction['representative'],
                    owner=transaction['owner'],
                    ticker=transaction['ticker'],
                    asset_description=transaction['asset_description'],
                    district=transaction['district'],
                    transaction_type=transaction['transaction_type'],
                    amount=transaction['amount'],
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

@app.get('/transactions/senate/all')
def get_all_senate_transactions(db: Session = Depends(get_db)):
    transactions = db.query(AllSenateTransactionModel).all()
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

@app.get('/transactions/house/all')
def get_all_house_transactions(db: Session = Depends(get_db)):
    transactions = (
        db.query(AllHouseTransactionModel)
        .order_by(AllHouseTransactionModel.transaction_date.desc())
        .all()
    )
    
    for transaction in transactions:
        if transaction.ticker is not None:
            ticker_match = re.search(r'>(\w+)<', transaction.ticker)
            if ticker_match:
                transaction.ticker = ticker_match.group(1)
        transaction.transaction_date = datetime.datetime.strptime(transaction.transaction_date, '%m/%d/%Y').strftime('%m/%d/%Y')
    return [transaction.__dict__ for transaction in transactions]

@app.get('/transactions/senate/{ticker}')
def get_senate_transactions_by_ticker(ticker: str, db: Session = Depends(get_db)):
    transactions = db.query(AllSenateTransactionModel).filter_by(ticker=ticker.upper()).all()
    for transaction in transactions:
        if transaction.ticker is not None:
            ticker_match = re.search(r'>(\w+)<', transaction.ticker)
            if ticker_match:
                transaction.ticker = ticker_match.group(1)
    return [transaction.__dict__ for transaction in transactions]

@app.get('/transactions/house/{ticker}')
def get_house_transactions_by_ticker(ticker: str, db: Session = Depends(get_db)):
    transactions = db.query(AllHouseTransactionModel).filter_by(ticker=ticker.upper()).all()
    for transaction in transactions:
        if transaction.ticker is not None:
            ticker_match = re.search(r'>(\w+)<', transaction.ticker)
            if ticker_match:
                transaction.ticker = ticker_match.group(1)
        transaction.transaction_date = datetime.datetime.strptime(transaction.transaction_date, '%m/%d/%Y').strftime('%m/%d/%Y')
    return [transaction.__dict__ for transaction in transactions]
