from collections import Counter, defaultdict
from sqlalchemy.sql.expression import case, desc
import requests
import json
from fastapi import Depends, FastAPI, HTTPException, BackgroundTasks
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
from sqlalchemy import func, create_engine, not_
from sqlalchemy.sql import label
import datetime
from datetime import timedelta
from typing import Optional, Dict, List, Union
import os
import pytz
import urllib.parse
from decimal import Decimal
from app.data_downloads import download_tickers_data, download_event
from fastapi.staticfiles import StaticFiles

# from apscheduler.schedulers.background import BackgroundScheduler




#https://github.com/rreichel3/US-Stock-Symbols/blob/main/nyse/nyse_full_tickers.json

app = FastAPI()
# scheduler = BackgroundScheduler()
app.mount("/senator_photo", StaticFiles(directory="app/senator_photos"), name='senator_photos')

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

#Postgresql
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

#SQLite database
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    
@app.on_event("startup")
async def startup_event():
    await download_event()
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
    session.close()

    async with httpx.AsyncClient() as client:
        senate_response = await client.get('https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json', headers={"Cache-Control": "no-cache"})
    senate_data = json.loads(senate_response.text)
    senate_sorted_transactions = sorted(senate_data, key=lambda x: datetime.datetime.strptime(
        x['transaction_date'], '%m/%d/%Y'), reverse=True)

    session = SessionLocal()
    eastern = pytz.timezone('America/New_York')

    with open("app/senators.json", "r") as f:
        senators_data = json.load(f)
        print("Senators data:", senators_data)  # print to console

    with open("app/transactions_with_closing_prices.json", "r") as f:
        transactions_data = json.load(f)
        


    for transaction in senate_sorted_transactions:
        if 'scanned_pdf' not in transaction:
            try:
                names = transaction['senator'].split(' ', 1)
                first_name = names[0]
                last_name = names[1] if len(names) > 1 else ''
                transaction_date_dt = datetime.datetime.strptime(transaction['transaction_date'], '%m/%d/%Y').replace(tzinfo=eastern)
                disclosure_date_dt = datetime.datetime.strptime(transaction['disclosure_date'], '%m/%d/%Y').replace(tzinfo=eastern)
                disclosure_delay = (disclosure_date_dt - transaction_date_dt).days
                
                senator = next((s for s in senators_data if s['first_name'] == first_name and s['last_name'] == last_name), None)
                amount_match = re.match(r"\$(\d+(?:,\d+)?) - \$(\d+(?:,\d+)?)", transaction['amount'])
                if amount_match:
                    low_amount = float(amount_match.group(1).replace(",", ""))
                    high_amount = float(amount_match.group(2).replace(",", ""))
                else:
                    continue
                if senator is None:
                    # Handle the case where the senator is not found in your data
                    continue

            except ValueError:
                continue
            

            matching_transaction = next(
                (t for t in transactions_data if t['transaction_date'] == transaction['transaction_date']),
                None
            )
            if matching_transaction is not None:
                closing_price_str = matching_transaction['closing_price']
                closing_price_str = closing_price_str.replace(',', '') if closing_price_str else None
                closing_price = float(closing_price_str) if closing_price_str is not None else None
            else:
                closing_price = None
                  
            if session.query(AllSenateTransactionModel).filter_by(
                ptr_link=transaction['ptr_link'],
                transaction_date=transaction['transaction_date'],       
            ).count() == 0:
                session.add(AllSenateTransactionModel(
                    senator=transaction['senator'],
                    bio_id = senator['bio_id'],
                    first_name=first_name,
                    last_name=last_name,
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
                    sector=transaction.get('sector'),
                    high_amount=high_amount,
                    low_amount=low_amount,
                    closing_price=closing_price,
                ))

    session.commit()
    session.close()
        
    # The following code calculates the top senators with the most trades in the last 60 days and stores the result in the TopSenatorModel table.
    # Get the current date
    current_date = datetime.date.today()

    # Get the date 60 days ago
    days_ago_60 = current_date - datetime.timedelta(days=60)
    session = SessionLocal()
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
    session.close()


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
        
        
@app.get('/transactions/senate/senators/holdings')
async def get_senators_holdings(db: Session = Depends(get_db)):
    # Query the database to retrieve all transactions for senators
    transactions = db.query(AllSenateTransactionModel).all()

    # Calculate the holdings and the total dollar value of holdings for each senator
    holdings_by_senator = {}

    for transaction in transactions:
        senator = transaction.senator
        ticker = transaction.ticker
        transaction_type = transaction.transaction_type
        low_amount = transaction.low_amount
        high_amount = transaction.high_amount
        purchase_price = transaction.closing_price

        if senator not in holdings_by_senator:
            holdings_by_senator[senator] = {}

        holdings = holdings_by_senator[senator]

        if transaction_type == "Purchase":
            if ticker not in holdings:
                holdings[ticker] = 0
            holdings[ticker] += calculate_holding_amount(low_amount, high_amount, purchase_price)
        elif transaction_type == "Sale (Full)":
            if ticker in holdings:
                del holdings[ticker]

    # Calculate the total holdings and the estimated dollar value of holdings for each senator
    senators_holdings = []

    for senator, holdings in holdings_by_senator.items():
        holdings_data = []
        for ticker, total_holdings in holdings.items():
            holdings_data.append({"ticker": ticker, "amount_held": total_holdings})
        senators_holdings.append({"senator": senator, "holdings": holdings_data})

    return {"senators_holdings": senators_holdings}

def calculate_holding_amount(low_amount: Optional[int], high_amount: Optional[int], closing_price: Optional[float]) -> float:
    if low_amount is None or high_amount is None or closing_price is None:
        return 0.0
    return (low_amount + high_amount) / 2 * closing_price

# Disclaimer: Holdings and Estimated Amounts Calculation

# The holdings and estimated amounts displayed are calculated based on the available transaction data and certain assumptions. Please note the following:

# 1. Holdings Calculation:
#    - When a senator makes a purchase transaction for a specific ticker, it is considered as holding that ticker.
#    - When a senator makes a sale (full) transaction for a specific ticker, it is considered as no longer holding that ticker.

# 2. Estimated Amount Calculation:
#    - The estimated amount of holdings is calculated based on the initial purchase price and the provided transaction amount range.
#    - The provided transaction amount range represents the senator's disclosed investment amount for the ticker.
#    - The estimated amount assumes an equal distribution within the given range.
#    - The closing price at the time of the transaction is used to estimate the current value of the holdings.
#    - If the closing price is not available, the estimated amount will be set to 0.

# 3. Partial Sales:
#    - If a senator makes multiple partial sales for a specific ticker, the estimated amount will be adjusted accordingly.
#    - The estimated amount will reflect the remaining holdings after deducting the partial sale amounts.

# Please note that the displayed holdings and estimated amounts are based on the available data and may not represent the exact current holdings or investment values. The calculations are provided for informational purposes only and should not be considered as financial advice.

# For more detailed information, please refer to the individual transaction records and consult with a qualified financial professional.


@app.get('/transactions/house/representatives/holdings')
async def get_senators_holdings(db: Session = Depends(get_db)):
    # Query the database to retrieve all transactions
    transactions = db.query(AllHouseTransactionModel).all()

    # Calculate the current holdings for each senator
    holdings_by_representative = defaultdict(set)

    for transaction in transactions:
        representative = transaction.representative
        ticker = transaction.ticker
        transaction_type = transaction.transaction_type

        if transaction_type == "Purchase":
            holdings_by_representative[representative].add(ticker)
        elif transaction_type == "Sale (Full)":
            holdings_by_representative[representative].discard(ticker)

    # Convert the holdings to a list of dictionaries for each senator
    representatives_holdings = [{"representative": representative, "holdings": list(holdings)} for representative, holdings in holdings_by_representative.items()]

    return {"senators_holdings": representatives_holdings}

# ^^^ Disclosure: Estimated Stock Holdings

# The following information provides an estimate of the current stock holdings for senators based on available transaction data. Please note the following:

# 1. Calculation Method: The estimated stock holdings are calculated based on the transaction history of senators as reported in publicly available data. We consider purchase transactions as indications of stock holdings, and sale (full) transactions as indications of stocks no longer held. This estimation method assumes that senators have not made any additional transactions outside of the available data.

# 2. Limitations of Accuracy: The estimated stock holdings are provided for informational purposes only and should not be considered as definitive or guaranteed. The accuracy of the estimated holdings may be affected by factors such as incomplete or inaccurate transaction data, variations in reporting formats, and potential delays in disclosure. Therefore, the estimated holdings may not reflect the senators' current actual stock holdings.

# 3. Ticker Symbols: The provided list of ticker symbols represents the stocks that senators are estimated to be holding based on available transaction data. It does not indicate the exact number of shares held or the specific financial value of the holdings.

# Please exercise caution and verify the information independently for any investment or decision-making purposes. We recommend consulting official financial disclosures and other reliable sources for the most up-to-date and accurate information regarding senators' stock holdings.
#! 60 Day Breakdown
@app.get('/transactions/senate/ticker/breakdown')
async def get_ticker_breakdown(ticker: str, db: Session = Depends(get_db)):
    # Query the database to retrieve the transactions for the specified ticker in the last 60 days
    ticker_transactions = db.query(AllSenateTransactionModel).filter(
        AllSenateTransactionModel.ticker == ticker,
        AllSenateTransactionModel.transaction_date_dt >= datetime.datetime.now() - datetime.timedelta(days=60)
    ).all()

    # Calculate the breakdown by party and transaction type
    party_breakdown = defaultdict(int)
    type_breakdown = defaultdict(int)
    total_transactions = len(ticker_transactions)

    for transaction in ticker_transactions:
        party_breakdown[transaction.party] += 1
        type_breakdown[transaction.transaction_type] += 1

    # Calculate the percentages
    party_percentages = {
        "Republican": party_breakdown["Republican"] / total_transactions * 100,
        "Democrat": party_breakdown["Democrat"] / total_transactions * 100,
        "Other": party_breakdown["Other"] / total_transactions * 100,
    }

    type_percentages = {
        "Sale (Partial)": type_breakdown["Sale (Partial)"] / total_transactions * 100,
        "Sale (Full)": type_breakdown["Sale (Full)"] / total_transactions * 100,
        "Purchase": type_breakdown["Purchase"] / total_transactions * 100,
        "Other": type_breakdown["Other"] / total_transactions * 100,
    }

    breakdown_data = {
        "ticker": ticker,
        "total_transactions": total_transactions,
        "party_breakdown": dict(party_breakdown),
        "party_percentages": party_percentages,
        "type_breakdown": dict(type_breakdown),
        "type_percentages": type_percentages
    }

    return breakdown_data

#! 60 Day Breakdown
@app.get('/transactions/house/ticker/breakdown')
async def get_tickerHouse_breakdown(ticker: str, db: Session = Depends(get_db)):
    # Query the database to retrieve the transactions for the specified ticker in the last 60 days
    ticker_transactions = db.query(AllHouseTransactionModel).filter(
        AllHouseTransactionModel.ticker == ticker,
        AllHouseTransactionModel.transaction_date_dt >= datetime.datetime.now() - datetime.timedelta(days=60)
    ).all()

    # Calculate the breakdown by party and transaction type
    party_breakdown = defaultdict(int)
    type_breakdown = defaultdict(int)
    total_transactions = len(ticker_transactions)

    for transaction in ticker_transactions:
        party_breakdown[transaction.party] += 1
        type_breakdown[transaction.transaction_type] += 1

    # Calculate the percentages
    party_percentages = {
        "Republican": party_breakdown["Republican"] / total_transactions * 100,
        "Democrat": party_breakdown["Democrat"] / total_transactions * 100,
        "Other": party_breakdown["Other"] / total_transactions * 100,
    }

    type_percentages = {
        "Sale (Partial)": type_breakdown["Sale (Partial)"] / total_transactions * 100,
        "Sale (Full)": type_breakdown["Sale (Full)"] / total_transactions * 100,
        "Purchase": type_breakdown["Purchase"] / total_transactions * 100,
        "Other": type_breakdown["Other"] / total_transactions * 100,
    }

    breakdown_data = {
        "ticker": ticker,
        "total_transactions": total_transactions,
        "party_breakdown": dict(party_breakdown),
        "party_percentages": party_percentages,
        "type_breakdown": dict(type_breakdown),
        "type_percentages": type_percentages
    }

    return breakdown_data


#! Ticker Search/Totals/Summary
@app.get('/transactions/senate/tickers/all')
async def get_unique_tickers_with_transaction_count(db: Session = Depends(get_db)):
    # Query the database to retrieve unique tickers and their transaction counts
    ticker_counts = (
        db.query(AllSenateTransactionModel.ticker, label('transaction_count', func.count()))
        .group_by(AllSenateTransactionModel.ticker)
        .order_by(AllSenateTransactionModel.ticker)
        .all()
    )

    # Create a list of dictionaries containing ticker and transaction count
    tickers = [{"ticker": ticker, "transaction_count": count} for ticker, count in ticker_counts]

    return {"tickers": tickers}


    
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


with open('app/nyse_full_tickers.json') as file:
    ticker_data = json.load(file)
    
with open('app/nasdaq_full_tickers.json') as nasdaq_file:
    nasdaq_ticker_data = json.load(nasdaq_file)

@app.get('/transactions/senate/all')
async def get_all_senate_transactions(page: Optional[int] = None, items_per_page: Optional[int] = None, senator: Optional[str] = None, bio_id: Optional[str] = None, ticker: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(AllSenateTransactionModel).filter(
        AllSenateTransactionModel.ticker != None,
        AllSenateTransactionModel.ticker.notin_(["--", "N/A"])
    )

    if senator is not None:
        senator = urllib.parse.unquote(senator)
        query = query.filter(func.lower(AllSenateTransactionModel.senator).contains(func.lower(senator)))
    
    if bio_id is not None:
        query = query.filter(AllSenateTransactionModel.bio_id == bio_id)
        
    if ticker is not None:
        ticker = urllib.parse.unquote(ticker)
        query = query.filter(func.lower(AllSenateTransactionModel.ticker) == func.lower(ticker))

    query = query.order_by(desc(AllSenateTransactionModel.transaction_date_dt))

    total = await run_in_threadpool(query.count)  # get total count

    # Apply pagination if provided
    if page is not None and items_per_page is not None:
        offset = page * items_per_page
        query = query.offset(offset).limit(items_per_page)

    transactions = await run_in_threadpool(query.all)

    for transaction in transactions:
        ticker = transaction.ticker

        matching_ticker = next((item for item in ticker_data if item['symbol'] == ticker), None)

        if matching_ticker:
            company_name = matching_ticker['name']
            current_price_str = matching_ticker['lastsale']
        else:
            matching_ticker = next((item for item in nasdaq_ticker_data if item['symbol'] == ticker), None)

            if matching_ticker:
                company_name = matching_ticker['name']
                current_price_str = matching_ticker['lastsale']
            else:
                company_name = None
                current_price_str = None

        if current_price_str:
            current_price = float(current_price_str.replace('$', ''))
            current_price_int = round(current_price, 2)
        else:
            current_price = None
            current_price_int = None

        transaction.company = company_name
        transaction.current_price = current_price
        transaction.current_price_int = current_price_int

        closing_price = transaction.closing_price

        if closing_price is not None and current_price_int is not None:
            percentage_return = ((current_price_int - closing_price) / closing_price) * 100
        else:
            percentage_return = None

        transaction.percentage_return = percentage_return

        # Convert transaction date to desired format (e.g., Apr 04, 2023)
        transaction_date = transaction.transaction_date_dt.strftime('%b %d, %Y')
        transaction.transaction_date_formatted = transaction_date

        # Convert disclosure date to desired format (e.g., May 19, 2021)
        disclosure_date = datetime.datetime.strptime(transaction.disclosure_date, '%m/%d/%Y').strftime('%b %d, %Y')
        transaction.disclosure_date_formatted = disclosure_date

    return {"total": total, "transactions": [transaction.__dict__ for transaction in transactions]}

@app.get('/transactions/senate/all_by_disclosure_date')
async def get_all_senate_by_disclosure_transactions(page: Optional[int] = None, items_per_page: Optional[int] = None, senator: Optional[str] = None, bio_id: Optional[str] = None, ticker: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(AllSenateTransactionModel).filter(
        AllSenateTransactionModel.ticker != None,
        AllSenateTransactionModel.ticker.notin_(["--", "N/A"])
    )

    if senator is not None:
        senator = urllib.parse.unquote(senator)
        query = query.filter(func.lower(AllSenateTransactionModel.senator).contains(func.lower(senator)))
    
    if bio_id is not None:
        query = query.filter(AllSenateTransactionModel.bio_id == bio_id)
        
    if ticker is not None:
        ticker = urllib.parse.unquote(ticker)
        query = query.filter(func.lower(AllSenateTransactionModel.ticker) == func.lower(ticker))

    query = query.order_by(desc(AllSenateTransactionModel.disclosure_date_dt))


    if page is not None and items_per_page is not None:
        offset = page * items_per_page
        query = query.offset(offset).limit(items_per_page)

    transactions = await run_in_threadpool(query.all)

    for transaction in transactions:
        ticker = transaction.ticker

        matching_ticker = next((item for item in ticker_data if item['symbol'] == ticker), None)

        if matching_ticker:
            company_name = matching_ticker['name']
            current_price_str = matching_ticker['lastsale']
        else:
            matching_ticker = next((item for item in nasdaq_ticker_data if item['symbol'] == ticker), None)

            if matching_ticker:
                company_name = matching_ticker['name']
                current_price_str = matching_ticker['lastsale']
            else:
                company_name = None
                current_price_str = None

        if current_price_str:
            current_price = float(current_price_str.replace('$', ''))
            current_price_int = round(current_price, 2)
        else:
            current_price = None
            current_price_int = None

        transaction.company = company_name
        transaction.current_price = current_price
        transaction.current_price_int = current_price_int

        closing_price = transaction.closing_price

        if closing_price is not None and current_price_int is not None:
            percentage_return = ((current_price_int - closing_price) / closing_price) * 100
        else:
            percentage_return = None

        transaction.percentage_return = percentage_return

        # Convert transaction date to desired format (e.g., Apr 04, 2023)
        transaction_date = transaction.transaction_date_dt.strftime('%b %d, %Y')
        transaction.transaction_date_formatted = transaction_date

        # Convert disclosure date to desired format (e.g., May 19, 2021)
        disclosure_date = datetime.datetime.strptime(transaction.disclosure_date, '%m/%d/%Y').strftime('%b %d, %Y')
        transaction.disclosure_date_formatted = disclosure_date

    return [transaction.__dict__ for transaction in transactions]

@app.get('/transactions/senate/senators')
async def get_all_senate_senators(db: Session = Depends(get_db)):
    query = db.query(AllSenateTransactionModel).filter(
        AllSenateTransactionModel.ticker != None,
        AllSenateTransactionModel.ticker.notin_(["--", "N/A"])
    ).order_by(desc(AllSenateTransactionModel.transaction_date_dt))

    transactions = await run_in_threadpool(query.all)

    senator_data = defaultdict(lambda: {"bio_id": "", "senator": "", "first_name": "", "last_name": "", "party": "", "transaction_count": 0})

    for transaction in transactions:
        senator = transaction.senator
        if senator is not None:
            first_name, last_name = split_senator_name(senator)
            senator_data[senator]["bio_id"] = transaction.bio_id
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

@app.get('/transactions/senate/all_old')
async def get_all_house_transactions(page: Optional[int] = None, items_per_page: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(AllSenateTransactionModel).filter(
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
    )

    total = await run_in_threadpool(query.count)  # Get total count of transactions

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

    return {"total": total, "transactions": [transaction.__dict__ for transaction in transactions]}


@app.get('/transactions/house/ticker/{ticker}')
async def get_house_transactions_by_ticker(
        ticker: str,
        page: Optional[int] = 0,
        items_per_page: Optional[int] = 25,
        db: Session = Depends(get_db)
):
    query = db.query(AllHouseTransactionModel).filter(
        AllHouseTransactionModel.ticker == ticker.upper(),
        AllHouseTransactionModel.ticker != None,
        AllHouseTransactionModel.ticker.notin_(["--", "N/A"])
    )

    total = await run_in_threadpool(query.count)  # Get total count of transactions

    query = query.order_by(desc(AllHouseTransactionModel.transaction_date_dt))

    # Apply pagination if provided
    if page is not None and items_per_page is not None:
        offset = page * items_per_page
        query = query.offset(offset).limit(items_per_page)

    transactions = await run_in_threadpool(query.all)

    for transaction in transactions:
        # Update transaction date in desired format
        transaction_date = transaction.transaction_date_dt.strftime('%m/%d/%Y')
        transaction.transaction_date = transaction_date

    return {"total": total, "transactions": [transaction.__dict__ for transaction in transactions]}



@app.get('/transactions/senator/top', response_model=List[dict])
async def get_top_senator_transactions(db: Session = Depends(get_db)):
    # Calculate the date range for the past 60 days
    start_date = datetime.datetime.now() - timedelta(days=60)

    query = (
        db.query(TopSenatorModel)
        .filter(TopSenatorModel.last_updated >= start_date)
        .order_by(desc(TopSenatorModel.trade_frequency))
    )
    transactions = await run_in_threadpool(query.all)

    result = []
    for transaction in transactions:
        transaction_dict = transaction.__dict__
        transaction_dict['last_updated'] = transaction.last_updated.strftime('%m/%d/%Y %H:%M:%S')
        senator_name = transaction_dict['senator']
        
        # Retrieve bio_id, party, and state for the senator
        senator_info_query = (
            db.query(AllSenateTransactionModel.bio_id, AllSenateTransactionModel.party, AllSenateTransactionModel.state)
            .filter(func.lower(AllSenateTransactionModel.senator) == senator_name.lower())
            .first()
        )

        if senator_info_query:
            bio_id, party, state = senator_info_query
            transaction_dict.update({
                'bio_id': bio_id,
                'party': party,
                'state': state
            })

        result.append(transaction_dict)

    return result



@app.get('/transactions/house/top', response_model=List[dict])
async def get_top_house_transactions(db: Session = Depends(get_db)):
    # Calculate the date range for the past 60 days
    start_date = datetime.datetime.now() - timedelta(days=60)

    query = (
        db.query(TopRepresentativeModel)
        .filter(TopRepresentativeModel.last_updated >= start_date)
        .order_by(desc(TopRepresentativeModel.trade_frequency))
    )
    transactions = await run_in_threadpool(query.all)

    result = []
    for transaction in transactions:
        transaction_dict = transaction.__dict__
        transaction_dict['last_updated'] = transaction.last_updated.strftime('%m/%d/%Y %H:%M:%S')
        result.append(transaction_dict)

    return result



@app.get('/transactions/senate/tickers/high_count_picks')
async def get_unique_tickers_with_transaction_count_high_count_picks(db: Session = Depends(get_db)):
    # Calculate the date range for the past 60 days
    start_date = datetime.datetime.now() - timedelta(days=60)

    # Query the database to retrieve unique tickers and their transaction counts for the past 60 days, excluding tickers with values "N/A" or "—"
    ticker_counts = (
        db.query(AllSenateTransactionModel.ticker, label('transaction_count', func.count()))
        .filter(
            AllSenateTransactionModel.transaction_date_dt >= start_date,
            AllSenateTransactionModel.ticker.notin_(["N/A", "—-"])
        )
        .group_by(AllSenateTransactionModel.ticker)
        .order_by(desc('transaction_count'))
        .all()
    )

    # Create a list of dictionaries containing ticker and transaction count
    tickers = []
    for ticker, count in ticker_counts:
        matching_ticker = next((item for item in ticker_data if item['symbol'] == ticker), None)
        if matching_ticker:
            company_name = matching_ticker['name']
            current_price_str = matching_ticker['lastsale']
        else:
            matching_ticker = next((item for item in nasdaq_ticker_data if item['symbol'] == ticker), None)
            if matching_ticker:
                company_name = matching_ticker['name']
                current_price_str = matching_ticker['lastsale']
            else:
                company_name = None
                current_price_str = None
        if current_price_str:
            current_price = float(current_price_str.replace('$', ''))
            current_price_int = round(current_price, 2)
        else:
            current_price = None
            current_price_int = None

        tickers.append({"ticker": ticker, "transaction_count": count, "company": company_name, "current_price": current_price, "current_price_int": current_price_int})

    return {"tickers": tickers}



@app.get('/transactions/house/tickers/high_count_picks')
async def get_unique_tickers_house_with_transaction_count_high_count_picks(db: Session = Depends(get_db)):
    # Calculate the date range for the past 60 days
    start_date = datetime.datetime.now() - timedelta(days=60)

    # Query the database to retrieve unique tickers and their transaction counts for the past 60 days, excluding tickers with values "N/A" or "—"
    ticker_counts = (
        db.query(AllHouseTransactionModel.ticker, label('transaction_count', func.count()))
        .filter(
            AllHouseTransactionModel.transaction_date_dt >= start_date,
            AllHouseTransactionModel.ticker.notin_(["N/A", "—-"])
        )
        .group_by(AllSenateTransactionModel.ticker)
        .order_by(desc('transaction_count'))
        .all()
    )

    # Create a list of dictionaries containing ticker and transaction count
    tickers = []
    for ticker, count in ticker_counts:
        matching_ticker = next((item for item in ticker_data if item['symbol'] == ticker), None)
        if matching_ticker:
            company_name = matching_ticker['name']
            current_price_str = matching_ticker['lastsale']
        else:
            matching_ticker = next((item for item in nasdaq_ticker_data if item['symbol'] == ticker), None)
            if matching_ticker:
                company_name = matching_ticker['name']
                current_price_str = matching_ticker['lastsale']
            else:
                company_name = None
                current_price_str = None
        if current_price_str:
            current_price = float(current_price_str.replace('$', ''))
            current_price_int = round(current_price, 2)
        else:
            current_price = None
            current_price_int = None

        tickers.append({"ticker": ticker, "transaction_count": count, "company": company_name, "current_price": current_price, "current_price_int": current_price_int})

    return {"tickers": tickers}


@app.get('/transactions/senate/tickers/hot_buys')
async def get_unique_tickers_with_transaction_count_hot_buys_picks(db: Session = Depends(get_db)):
    # Calculate the date range for the past 60 days
    start_date = datetime.datetime.now() - timedelta(days=60)

    # Query the database to retrieve unique tickers and their transaction counts for the past 60 days, sorted by count
    ticker_counts = (
        db.query(AllSenateTransactionModel.ticker, label('transaction_count', func.count()))
        .filter(AllSenateTransactionModel.transaction_date_dt >= start_date)
        .filter(AllSenateTransactionModel.transaction_type == 'Purchase')
        .group_by(AllSenateTransactionModel.ticker)
        .order_by(desc('transaction_count'))
        .all()
    )

    # Create a list of dictionaries containing ticker and transaction count
    tickers = [{"ticker": ticker, "transaction_count": count} for ticker, count in ticker_counts]

    return {"tickers": tickers}


@app.get('/transactions/house/tickers/hot_buys')
async def get_unique_tickers_house_with_transaction_count_hot_buys_picks(db: Session = Depends(get_db)):
    # Calculate the date range for the past 60 days
    start_date = datetime.datetime.now() - timedelta(days=60)

    # Query the database to retrieve unique tickers and their transaction counts for the past 60 days, sorted by count
    ticker_counts = (
        db.query(AllHouseTransactionModel.ticker, label('transaction_count', func.count()))
        .filter(
            AllHouseTransactionModel.transaction_date_dt >= start_date,
            AllHouseTransactionModel.ticker != "--",
            AllHouseTransactionModel.transaction_type == 'Purchase'
        )
        .group_by(AllHouseTransactionModel.ticker)
        .order_by(desc('transaction_count'))
        .all()
    )

    # Create a list of dictionaries containing ticker and transaction count
    tickers = [{"ticker": ticker, "transaction_count": count} for ticker, count in ticker_counts]

    return {"tickers": tickers}


@app.get('/transactions/senate/tickers/highest_sold')
async def get_unique_tickers_senate_highest_sold(db: Session = Depends(get_db)):
    # Calculate the date range for the past 60 days
    start_date = datetime.datetime.now() - timedelta(days=60)

    # Query the database to retrieve unique tickers and their transaction counts for the past 60 days, sorted by count
    ticker_counts = (
        db.query(AllSenateTransactionModel.ticker, label('transaction_count', func.count()))
        .filter(
            AllSenateTransactionModel.transaction_date_dt >= start_date,
            AllSenateTransactionModel.transaction_type.in_(['Sale (Full)', 'Sale (Partial)'])
        )
        .group_by(AllSenateTransactionModel.ticker)
        .order_by(desc('transaction_count'))
        .all()
    )

    # Create a list of dictionaries containing ticker, transaction count, company name, and current price
    tickers = []
    for ticker, count in ticker_counts:
        matching_ticker = next((item for item in ticker_data if item['symbol'] == ticker), None)
        if matching_ticker:
            company_name = matching_ticker['name']
            current_price_str = matching_ticker['lastsale']
        else:
            matching_ticker = next((item for item in nasdaq_ticker_data if item['symbol'] == ticker), None)
            if matching_ticker:
                company_name = matching_ticker['name']
                current_price_str = matching_ticker['lastsale']
            else:
                company_name = None
                current_price_str = None
        if current_price_str:
            current_price = float(current_price_str.replace('$', ''))
            current_price_int = round(current_price, 2)
        else:
            current_price = None
            current_price_int = None

        tickers.append({"ticker": ticker, "transaction_count": count, "company": company_name, "current_price": current_price, "current_price_int": current_price_int})

    return {"tickers": tickers}



@app.get('/transactions/house/tickers/highest_sold')
async def get_unique_tickers_house_highest_sold(db: Session = Depends(get_db)):
    # Calculate the date range for the past 60 days
    start_date = datetime.datetime.now() - timedelta(days=60)

    # Query the database to retrieve unique tickers and their transaction counts for the past 60 days, sorted by count
    ticker_counts = (
        db.query(AllHouseTransactionModel.ticker, label('transaction_count', func.count()))
        .filter(
            AllHouseTransactionModel.transaction_date_dt >= start_date,
            AllHouseTransactionModel.transaction_type.in_(['Sale (Full)', 'Sale (Partial)'])
        )
        .group_by(AllHouseTransactionModel.ticker)
        .order_by(desc('transaction_count'))
        .all()
    )

    # Create a list of dictionaries containing ticker, transaction count, company name, and current price
    tickers = []
    for ticker, count in ticker_counts:
        matching_ticker = next((item for item in ticker_data if item['symbol'] == ticker), None)
        if matching_ticker:
            company_name = matching_ticker['name']
            current_price_str = matching_ticker['lastsale']
        else:
            matching_ticker = next((item for item in nasdaq_ticker_data if item['symbol'] == ticker), None)
            if matching_ticker:
                company_name = matching_ticker['name']
                current_price_str = matching_ticker['lastsale']
            else:
                company_name = None
                current_price_str = None
        if current_price_str:
            current_price = float(current_price_str.replace('$', ''))
            current_price_int = round(current_price, 2)
        else:
            current_price = None
            current_price_int = None

        tickers.append({"ticker": ticker, "transaction_count": count, "company": company_name, "current_price": current_price, "current_price_int": current_price_int})

    return {"tickers": tickers}


@app.get('/transactions/senate/dashboard/party-breakdown')
async def get_party_breakdown(db: Session = Depends(get_db)):
    # Calculate the total number of transactions in the past 60 days
    total_transactions = (
        db.query(func.count(AllSenateTransactionModel.id))
        .filter(AllSenateTransactionModel.transaction_date_dt >= datetime.datetime.now() - datetime.timedelta(days=60))
        .scalar()
    )

    # Calculate the number of transactions for each party in the past 60 days
    party_transactions = (
        db.query(AllSenateTransactionModel.party, func.count(AllSenateTransactionModel.id))
        .filter(AllSenateTransactionModel.transaction_date_dt >= datetime.datetime.now() - datetime.timedelta(days=60))
        .group_by(AllSenateTransactionModel.party)
        .all()
    )

    # Calculate the percentage of transactions for each party
    party_breakdown = []
    for party, count in party_transactions:
        percentage = (count / total_transactions) * 100
        party_breakdown.append({"party": party, "percentage": percentage})

    return {"party_breakdown": party_breakdown}

@app.get('/transactions/senate/dashboard/transaction-type-breakdown')
async def get_transaction_type_breakdown(db: Session = Depends(get_db)):
    # Calculate the total number of transactions in the past 60 days
    total_transactions = (
        db.query(func.count(AllSenateTransactionModel.id))
        .filter(AllSenateTransactionModel.transaction_date_dt >= datetime.datetime.now() - datetime.timedelta(days=60))
        .scalar()
    )

    # Calculate the number of transactions for each transaction type in the past 60 days
    type_transactions = (
        db.query(AllSenateTransactionModel.transaction_type, func.count(AllSenateTransactionModel.id))
        .filter(AllSenateTransactionModel.transaction_date_dt >= datetime.datetime.now() - datetime.timedelta(days=60))
        .group_by(AllSenateTransactionModel.transaction_type)
        .all()
    )

    # Calculate the percentage of transactions for each transaction type
    type_breakdown = []
    for transaction_type, count in type_transactions:
        percentage = (count / total_transactions) * 100
        type_breakdown.append({"transaction_type": transaction_type, "percentage": percentage})

    return {"type_breakdown": type_breakdown}

@app.get('/transactions/senate/senator/returns')
async def get_senate_transactions_by_senator_returns(
    senator: str,
    page: Optional[int] = None,
    items_per_page: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(AllSenateTransactionModel).filter_by(senator=senator)

    open_positions = {}
    closed_positions = []
    partial_sales = []

    for transaction in query:
        ticker = transaction.ticker
        transaction_type = transaction.transaction_type
        closing_price = transaction.closing_price

        if transaction_type == 'Purchase':
            open_positions[ticker] = {
                'purchase_price': closing_price,
                'sell_price': None,
                'partial_sale_amount': 0
            }
        elif transaction_type == 'Sale (Full)':
            if ticker in open_positions:
                open_position = open_positions.pop(ticker)
                open_position['sell_price'] = closing_price
                closed_positions.append(open_position)
        elif transaction_type == 'Sale (Partial)':
            if ticker in open_positions:
                open_position = open_positions[ticker]
                partial_sale_amount = float(transaction.amount)  # Convert to float
                open_position['partial_sale_amount'] += partial_sale_amount
                partial_sales.append({
                    'ticker': ticker,
                    'purchase_price': open_position['purchase_price'],
                    'partial_sale_amount': open_position['partial_sale_amount'],
                    'sell_price': closing_price
                })

    returns = []

    for position in closed_positions:
        purchase_price = position['purchase_price']
        sell_price = position['sell_price']
        profit = sell_price - purchase_price
        returns.append({
            'ticker': ticker,
            'purchase_price': purchase_price,
            'sell_price': sell_price,
            'profit': profit
        })

    for partial_sale in partial_sales:
        purchase_price = partial_sale['purchase_price']
        partial_sale_amount = partial_sale['partial_sale_amount']
        sell_price = partial_sale['sell_price']
        profit = sell_price - purchase_price
        returns.append({
            'ticker': ticker,
            'purchase_price': purchase_price,
            'partial_sale_amount': partial_sale_amount,
            'sell_price': sell_price,
            'profit': profit
        })

    # Apply pagination if provided
    if page is not None and items_per_page is not None:
        start = (page - 1) * items_per_page
        end = start + items_per_page
        returns = returns[start:end]

    return returns



# uvicorn app.main:app --reload
