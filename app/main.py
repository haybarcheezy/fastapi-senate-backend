from collections import Counter, defaultdict
import requests
import json
from fastapi import Depends, FastAPI, HTTPException
import asyncio
import httpx
from sqlalchemy.orm import Session, sessionmaker
from typing import List
from app.database import get_db
from app.models import SenatorTransactionModel, AllSenateTransactionModel, AllHouseTransactionModel, TopRepresentativeModel, TopSenatorModel
from app.models import Base
from app.database import engine
import re
from starlette.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func, create_engine
import datetime
from datetime import timedelta
from typing import Optional
import pytz
import urllib.parse




app = FastAPI()

origins = [
    "http://localhost",
    "http://localhost:3000",
    "https://bukuviral.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_cors_header(request, call_next):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

#SQLite database
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Retrieve the data from the source and insert it into the database
@app.on_event("startup")
async def startup_event():
    async with httpx.AsyncClient() as client:
        response = await client.get('https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions_for_senators.json')
    data = json.loads(response.text)

    session = SessionLocal()
    for senator in data:
        for transaction in senator['transactions']:
            if 'scanned_pdf' not in transaction:
                # Check if transaction already exists in the database
                existing_mysql_transaction = session.query(SenatorTransactionModel).filter_by(
                    owner=transaction['owner'],
                    transaction_date=transaction['transaction_date'],
                    ticker=transaction['ticker']
                ).first()
                if existing_mysql_transaction is not None:
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

    async with httpx.AsyncClient() as client:
        senate_response = await client.get('https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json')
    senate_data = json.loads(senate_response.text)
    senate_sorted_transactions = sorted(senate_data, key=lambda x: datetime.datetime.strptime(
        x['transaction_date'], '%m/%d/%Y'), reverse=True)

    session = SessionLocal()
    eastern = pytz.timezone('America/New_York')

    for transaction in senate_sorted_transactions:
        if 'scanned_pdf' not in transaction:
            try:
                transaction_date_dt = datetime.datetime.strptime(transaction['transaction_date'], '%m/%d/%Y').replace(tzinfo=eastern)
                disclosure_date_dt = datetime.datetime.strptime(transaction['disclosure_date'], '%m/%d/%Y').replace(tzinfo=eastern)
                disclosure_delay = (disclosure_date_dt - transaction_date_dt).days
            except ValueError:
                continue
            if session.query(AllSenateTransactionModel).filter_by(
                senator=transaction['senator'],
                ptr_link=transaction['ptr_link'],
                transaction_date=transaction['transaction_date'],
                disclosure_date=transaction['disclosure_date'],
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
                    transaction_date_dt=transaction_date_dt,
                    disclosure_date=transaction['disclosure_date'],
                    disclosure_date_dt=disclosure_date_dt,
                    disclosure_delay=disclosure_delay,
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
        
    # The following code calculates the top senators with the most trades in the last 60 days and stores the result in the TopSenatorModel table.
    # Get the current date
    current_date = datetime.date.today()

    # Get the date 60 days ago
    days_ago_60 = current_date - datetime.timedelta(days=60)

    # Query the database for all transactions
    all_transactions = session.query(AllSenateTransactionModel).all()

    # Filter transactions in the last 60 days
    recent_transactions = [transaction for transaction in all_transactions if datetime.datetime.strptime(transaction.transaction_date, '%m/%d/%Y').date() >= days_ago_60]
    print(f"Number of recent transactions: {len(recent_transactions)}")  # Debug print
    # Create a Counter object to count the frequency of each senators
    sen_counter = Counter([transaction.senator for transaction in recent_transactions])

    # Get the 5 most common senators
    top_sens = sen_counter.most_common(5)
    print(f"Top senators: {top_sens}")  # Debug print

    # Delete the old records from the TopSenatorModel table
    session.query(TopSenatorModel).delete()

    # Add the new top senators to the TopSenatorModel table
    for sen, freq in top_sens:
        new_sen = TopSenatorModel(senator=sen, trade_frequency=freq)
        session.add(new_sen)
        print(f"Adding: {new_sen}")  # Debug print
        
    session.commit()


    async with httpx.AsyncClient() as client:
        house_response = await client.get('https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json')
    house_data = json.loads(house_response.text)
    house_lambda_sorted_transactions = sorted(house_data, key=lambda x: datetime.datetime.strptime(
        x['disclosure_date'], '%m/%d/%Y'), reverse=True)
    house_sorted_transactions = []
    type_map = {'sale_partial': 'Sale (Partial)', 'sale_full': 'Sale (Full)',
                'purchase': 'Purchase', 'exchange': 'Exchange'}

    with SessionLocal() as session:
        for transaction in house_lambda_sorted_transactions:
            try:
                transaction_date = datetime.datetime.strptime(
                    transaction['transaction_date'], '%Y-%m-%d')
                transaction_type = transaction['type']
                if transaction_type in type_map:
                    transaction_type = type_map[transaction_type]
                else:
                    print(
                        f"Warning: Unknown transaction type {transaction_type}. Saving as-is.")
                transaction['transaction_date'] = transaction_date.strftime(
                    '%m/%d/%Y')
                transaction['transaction_type'] = transaction_type
                house_sorted_transactions.append(transaction)
            except ValueError:
                print(
                    f"Error: Invalid transaction date format: {transaction['transaction_date']}. Skipping transaction.")
                continue

        eastern = pytz.timezone('America/New_York')
        
        for transaction in house_sorted_transactions:
            if 'scanned_pdf' not in transaction:
                # Check if a record with the same transaction date and ticker already exists in the database
                existing_record = session.query(AllHouseTransactionModel).filter_by(
                    transaction_date=transaction['transaction_date'], ticker=transaction['ticker']).first()
                if existing_record:
                    continue  # Skip this transaction if it already exists in the database
                try:
                    transaction_date_dt = datetime.datetime.strptime(transaction['transaction_date'], '%m/%d/%Y').replace(tzinfo=eastern)
                    disclosure_date_dt = datetime.datetime.strptime(transaction['disclosure_date'], '%m/%d/%Y').replace(tzinfo=eastern)
                    disclosure_delay = (disclosure_date_dt - transaction_date_dt).days
                except ValueError:
                    continue
                session.add(AllHouseTransactionModel(
                    transaction_date=transaction['transaction_date'],
                    disclosure_date=transaction['disclosure_date'],
                    transaction_date_dt=transaction_date_dt,
                    disclosure_date_dt=disclosure_date_dt,
                    disclosure_delay=disclosure_delay,
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
        
        # The following code calculates the top representatives with the most trades in the last 60 days and stores the result in the TopRepresentativeModel table.
        # Get the current date
        current_date = datetime.date.today()

        # Get the date 60 days ago
        days_ago_60 = current_date - datetime.timedelta(days=60)

        # Query the database for all transactions
        all_transactions = session.query(AllHouseTransactionModel).all()

        # Filter transactions in the last 60 days
        recent_transactions = []
        for transaction in all_transactions:
            try:
                transaction_date = datetime.datetime.strptime(transaction.transaction_date, '%m/%d/%Y').date()
                if transaction_date >= days_ago_60:
                    recent_transactions.append(transaction)
            except ValueError:
                # Skip transactions with invalid date format
                continue
        print(f"Number of recent transactions: {len(recent_transactions)}")  # Debug print

        # Create a Counter object to count the frequency of each representative
        rep_counter = Counter([transaction.representative for transaction in recent_transactions])

        # Get the 5 most common representatives
        top_reps = rep_counter.most_common(5)
        print(f"Top representatives: {top_reps}")  # Debug print

        # Delete the old records from the TopRepresentativeModel table
        session.query(TopRepresentativeModel).delete()

        # Add the new top representatives to the TopRepresentativeModel table
        for rep, freq in top_reps:
            new_rep = TopRepresentativeModel(representative=rep, trade_frequency=freq)
            session.add(new_rep)
            print(f"Adding: {new_rep}")  # Debug print
        session.commit()

    
@app.get('/transactions/senate/{first_name}-{last_name}')
async def get_transactions(first_name: str, last_name: str, db: Session = Depends(get_db)):
    transactions = await run_in_threadpool(db.query(AllSenateTransactionModel).filter_by(first_name=first_name, last_name=last_name).all)
    for transaction in transactions:
        if transaction.ticker is not None:
            ticker_match = re.search(r'>(\w+)<', transaction.ticker)
            if ticker_match:
                transaction.ticker = ticker_match.group(1)
    return [SenatorTransactionModel(**{k: v for k, v in transaction.__dict__.items() if k != '_sa_instance_state'}) for transaction in transactions]

@app.get('/transactions/senate/senator/{senator}')
async def get_transactions(senator: str, db: Session = Depends(get_db)):
    transactions = await run_in_threadpool(db.query(AllSenateTransactionModel).filter_by(senator=senator).all)
    for transaction in transactions:
        if transaction.ticker is not None:
            ticker_match = re.search(r'>(\w+)<', transaction.ticker)
            if ticker_match:
                transaction.ticker = ticker_match.group(1)
    return [SenatorTransactionModel(**{k: v for k, v in transaction.__dict__.items() if k != '_sa_instance_state'}) for transaction in transactions]



@app.get('/transactions/house/party/{party}')
async def get_transactions_by_party(party: str, db: Session = Depends(get_db)):
    transactions = await run_in_threadpool(db.query(AllHouseTransactionModel).filter_by(party=party).all)
    return [
        AllHouseTransactionModel(
            **{k: v for k, v in transaction.__dict__.items() if k != '_sa_instance_state'}
        )
        for transaction in transactions
    ]

#! State endpoint


@app.get('/transactions/house/state/{state}')
async def get_transactions_by_state(state: str, db: Session = Depends(get_db)):
    transactions = await run_in_threadpool(db.query(SenatorTransactionModel).filter_by(state=state).all)
    return [
        SenatorTransactionModel(
            **{k: v for k, v in transaction.__dict__.items() if k != '_sa_instance_state'}
        )
        for transaction in transactions
    ]


@app.get('/transactions/senate/party/{party}')
async def get_transactions_by_party(party: str, db: Session = Depends(get_db)):
    transactions = await run_in_threadpool(db.query(SenatorTransactionModel).filter_by(party=party).all)
    return [
        SenatorTransactionModel(
            **{k: v for k, v in transaction.__dict__.items() if k != '_sa_instance_state'}
        )
        for transaction in transactions
    ]


@app.get('/transactions/senate/sector/{sector}')
async def get_transactions_by_sector(sector: str, db: Session = Depends(get_db)):
    transactions = await run_in_threadpool(db.query(SenatorTransactionModel).filter_by(sector=sector).all)
    return [
        SenatorTransactionModel(
            **{k: v for k, v in transaction.__dict__.items() if k != '_sa_instance_state'}
        )
        for transaction in transactions
    ]


async def get_transactions(first_name: str, last_name: str, db: Session):
    transactions = await run_in_threadpool(db.query(SenatorTransactionModel).filter_by(first_name=first_name, last_name=last_name).all)
    for transaction in transactions:
        if transaction.ticker is not None:
            ticker_match = re.search(r'>(\w+)<', transaction.ticker)
            if ticker_match:
                transaction.ticker = ticker_match.group(1)
    return [transaction.__dict__ for transaction in transactions]


@app.get('/transactions/senate/all')
async def get_all_senate_transactions(page: Optional[int] = None, items_per_page: Optional[int] = None, senator: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(AllSenateTransactionModel).filter(
        AllSenateTransactionModel.ticker != None,
        AllSenateTransactionModel.ticker.notin_(["--", "N/A"])
    )

    if senator is not None:
        senator = urllib.parse.unquote(senator)
        query = query.filter(func.lower(AllSenateTransactionModel.senator).contains(func.lower(senator)))

    query = query.order_by(desc(AllSenateTransactionModel.transaction_date_dt))

    # Apply pagination if provided
    if page is not None and items_per_page is not None:
        offset = page * items_per_page
        query = query.offset(offset).limit(items_per_page)

    transactions = await run_in_threadpool(query.all)

    for transaction in transactions:
        # Convert transaction date to desired format
        transaction_date = transaction.transaction_date_dt.strftime('%m/%d/%Y')
        transaction.transaction_date = transaction_date

    return [transaction.__dict__ for transaction in transactions]

@app.get('/transactions/senate/senators')
async def get_all_senate_senators(db: Session = Depends(get_db)):
    query = db.query(AllSenateTransactionModel).filter(
        AllSenateTransactionModel.ticker != None,
        AllSenateTransactionModel.ticker.notin_(["--", "N/A"])
    ).order_by(desc(AllSenateTransactionModel.transaction_date_dt))

    transactions = await run_in_threadpool(query.all)

    senator_data = defaultdict(lambda: {"senator": "", "first_name": "", "last_name": "", "party": "", "transaction_count": 0})

    for transaction in transactions:
        senator = transaction.senator
        if senator is not None:
            first_name, last_name = split_senator_name(senator)
            senator_data[senator]["senator"] = senator
            senator_data[senator]["first_name"] = first_name
            senator_data[senator]["last_name"] = last_name
            senator_data[senator]["party"] = transaction.party
            senator_data[senator]["transaction_count"] += 1

    sorted_senators = sorted(senator_data.values(), key=lambda x: x['first_name'])

    return sorted_senators

def split_senator_name(senator: str):
    names = senator.split()
    first_name = names[0]
    last_name_parts = names[2:] if len(names) > 2 else names[1:]
    last_name = ' '.join(last_name_parts)
    last_name = re.sub(r'[,.]', '', last_name)  # Remove comma or period from the last name if present
    return first_name, last_name

@app.get('/transactions/senate/search')
async def get_all_senate_by_senator(page: Optional[int] = None, items_per_page: Optional[int] = None, senator: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(AllSenateTransactionModel).filter(
        AllSenateTransactionModel.ticker != None,
        AllSenateTransactionModel.ticker.notin_(["--", "N/A"])
    ).order_by(desc(AllSenateTransactionModel.transaction_date_dt))

    # Apply pagination if provided
    if page is not None and items_per_page is not None:
        offset = page * items_per_page
        query = query.offset(offset).limit(items_per_page)

    if senator is not None:
        # Split the senator parameter into individual words
        search_words = re.split(r'\s+', senator.strip())

        # Apply case-insensitive search for each word
        for word in search_words:
            query = query.filter(func.lower(AllSenateTransactionModel.senator).contains(func.lower(word)))

    transactions = await run_in_threadpool(query.all)

    for transaction in transactions:
        # Convert transaction date to desired format
        transaction_date = transaction.transaction_date_dt.strftime('%m/%d/%Y')
        transaction.transaction_date = transaction_date

    return [transaction.__dict__ for transaction in transactions]

@app.get('/transactions/house/all')
async def get_all_house_transactions(page: Optional[int] = None, items_per_page: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(AllHouseTransactionModel).filter(
        AllHouseTransactionModel.ticker != None, 
        AllHouseTransactionModel.ticker.notin_(["--", "N/A"])
    ).order_by(desc(AllHouseTransactionModel.transaction_date_dt))

    # Apply pagination if provided
    if page is not None and items_per_page is not None:
        offset = page * items_per_page
        query = query.offset(offset).limit(items_per_page)

    transactions = await run_in_threadpool(query.all)

    for transaction in transactions:
        # Convert transaction date to desired format
        transaction_date = transaction.transaction_date_dt.strftime('%m/%d/%Y')
        transaction.transaction_date = transaction_date

    return [transaction.__dict__ for transaction in transactions]

@app.get('/transactions/senate/{party}/all')
async def get_all_senate_transactions_by_party(party: str, page: Optional[int] = None, items_per_page: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(AllSenateTransactionModel).filter(
        AllSenateTransactionModel.ticker != None,
        AllSenateTransactionModel.ticker.notin_(["--", "N/A"]),
        AllSenateTransactionModel.party == party.capitalize()
    ).order_by(desc(AllSenateTransactionModel.transaction_date_dt))

    # Apply pagination if provided
    if page is not None and items_per_page is not None:
        offset = page * items_per_page
        query = query.offset(offset).limit(items_per_page)

    transactions = await run_in_threadpool(query.all)

    for transaction in transactions:
        # Convert transaction date to desired format
        transaction_date = transaction.transaction_date_dt.strftime('%m/%d/%Y')
        transaction.transaction_date = transaction_date

    return [transaction.__dict__ for transaction in transactions]

@app.get('/transactions/house/{party}/all')
async def get_all_house_transactions_by_party(party: str, page: Optional[int] = None, items_per_page: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(AllHouseTransactionModel).filter(
        AllHouseTransactionModel.ticker != None, 
        AllHouseTransactionModel.ticker.notin_(["--", "N/A"]),
        AllHouseTransactionModel.party == party.capitalize()
    ).order_by(desc(AllHouseTransactionModel.transaction_date_dt))

    # Apply pagination if provided
    if page is not None and items_per_page is not None:
        offset = page * items_per_page
        query = query.offset(offset).limit(items_per_page)

    transactions = await run_in_threadpool(query.all)

    for transaction in transactions:
        # Convert transaction date to desired format
        transaction_date = transaction.transaction_date_dt.strftime('%m/%d/%Y')
        transaction.transaction_date = transaction_date

    return [transaction.__dict__ for transaction in transactions]

 # @app.get('/transactions/house/all')
# async def get_all_house_transactions(page: Optional[int] = None, items_per_page: Optional[int] = None, db: Session = Depends(get_db)):
#     # generate cache key
#     cache_key = f"all_house_transactions-{page}-{items_per_page}"
#     # check if results are already cached
#     if cache_key in cache:
#         return cache[cache_key]

#     query = db.query(AllHouseTransactionModel)

#     # Apply pagination if provided
#     if page is not None and items_per_page is not None:
#         offset = page * items_per_page
#         query = query.offset(offset).limit(items_per_page)

#     transactions = await run_in_threadpool(query.all)

#     for transaction in transactions:
#         if transaction.ticker is not None:
#             ticker_match = re.search(r'>(\w+)<', transaction.ticker)
#             if ticker_match:
#                 transaction.ticker = ticker_match.group(1)

#         # Convert transaction date to datetime object
#         try:
#             transaction_date = datetime.datetime.strptime(
#                 transaction.transaction_date, '%m/%d/%Y')
#         except ValueError:
#             continue

#         # Update transaction date in desired format
#         transaction.transaction_date = transaction_date.strftime('%m/%d/%Y')

#     # cache results
#     cache[cache_key] = [transaction.__dict__ for transaction in transactions]

#     return cache[cache_key]


# @app.get('/transactions/senate/all')
# async def get_all_senate_transactions(page: Optional[int] = None, items_per_page: Optional[int] = None, db: Session = Depends(get_db)):
#     # generate cache key
#     cache_key = f"all_senate_transactions-{page}-{items_per_page}"
#     # check if results are already cached
#     if cache_key in cache:
#         return cache[cache_key]

#     query = db.query(AllSenateTransactionModel)

#     # Apply pagination if provided
#     if page is not None and items_per_page is not None:
#         offset = page * items_per_page
#         query = query.offset(offset).limit(items_per_page)

#     transactions = await run_in_threadpool(query.all)

#     for transaction in transactions:
#         if transaction.ticker is not None:
#             ticker_match = re.search(r'>(\w+)<', transaction.ticker)
#             if ticker_match:
#                 transaction.ticker = ticker_match.group(1)

#         # Convert transaction date to datetime object
#         try:
#             transaction_date = datetime.datetime.strptime(
#                 transaction.transaction_date, '%m/%d/%Y')
#         except ValueError:
#             continue

#         # Update transaction date in desired format
#         transaction.transaction_date = transaction_date.strftime('%m/%d/%Y')

#     # cache results
#     cache[cache_key] = [transaction.__dict__ for transaction in transactions]

#     return cache[cache_key]

@app.get('/transactions/senate/ticker/{ticker}')
async def get_senate_transactions_by_ticker(
        ticker: str,
        page: Optional[int] = 0,
        items_per_page: Optional[int] = 25,
        db: Session = Depends(get_db)
):
    query = db.query(AllSenateTransactionModel).filter(
        AllSenateTransactionModel.ticker == ticker.upper(),
        AllSenateTransactionModel.ticker != None,
        AllSenateTransactionModel.ticker.notin_(["--", "N/A"])
    ).order_by(desc(AllSenateTransactionModel.transaction_date_dt))

    # Apply pagination if provided
    if page is not None and items_per_page is not None:
        offset = page * items_per_page
        query = query.offset(offset).limit(items_per_page)

    transactions = await run_in_threadpool(query.all)

    for transaction in transactions:
        # Convert transaction date to desired format
        transaction_date = transaction.transaction_date_dt.strftime('%m/%d/%Y')
        transaction.transaction_date = transaction_date

    return [transaction.__dict__ for transaction in transactions]
# ? done


@app.get('/transactions/house/ticker/{ticker}')
async def get_house_transactions_by_ticker(ticker: str, page: Optional[int] = 0, items_per_page: Optional[int] = 25, db: Session = Depends(get_db)):
    query = db.query(AllHouseTransactionModel).filter(
        AllHouseTransactionModel.ticker == ticker.upper(),
        AllHouseTransactionModel.ticker != None,
        AllHouseTransactionModel.ticker.notin_(["--", "N/A"])
    ).order_by(desc(AllHouseTransactionModel.transaction_date_dt))

    # Apply pagination if provided
    if page is not None and items_per_page is not None:
        offset = page * items_per_page
        query = query.offset(offset).limit(items_per_page)

    transactions = await run_in_threadpool(query.all)

    for transaction in transactions:
        # Update transaction date in desired format
        transaction_date = transaction.transaction_date_dt.strftime('%m/%d/%Y')
        transaction.transaction_date = transaction_date

    return [transaction.__dict__ for transaction in transactions]



@app.get('/transactions/senator/top', response_model=List[dict])
async def get_top_senator_transactions(db: Session = Depends(get_db)):
    query = db.query(TopSenatorModel)
    transactions = await run_in_threadpool(query.all)

    result = []
    for transaction in transactions:
        transaction_dict = transaction.__dict__
        transaction_dict['last_updated'] = transaction.last_updated.strftime('%m/%d/%Y %H:%M:%S')
        result.append(transaction_dict)

    return result

@app.get('/transactions/house/top', response_model=List[dict])
async def get_top_house_transactions(db: Session = Depends(get_db)):
    query = db.query(TopRepresentativeModel)
    transactions = await run_in_threadpool(query.all)

    result = []
    for transaction in transactions:
        transaction_dict = transaction.__dict__
        transaction_dict['last_updated'] = transaction.last_updated.strftime('%m/%d/%Y %H:%M:%S')
        result.append(transaction_dict)

    return result
# uvicorn app.main:app --reload
