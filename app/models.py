from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
import re

Base = declarative_base()


class SenatorTransactionModel(Base):
    __tablename__ = 'senator_transactions'

    id = Column(Integer, primary_key=True)
    first_name = Column(String)
    last_name = Column(String)
    office = Column(String)
    ptr_link = Column(String)
    date_received = Column(String)
    transaction_date = Column(String)
    owner = Column(String)
    ticker = Column(String)
    asset_description = Column(String)
    asset_type = Column(String)
    transaction_type = Column(String)
    amount = Column(String)
    comment = Column(String)
    party = Column(String)
    state = Column(String)
    industry = Column(String)
    sector = Column(String)
    option_type = Column(String)
    strike_price = Column(String)
    expiration_date = Column(String)

    def __init__(self, **kwargs):
        if kwargs.get('asset_type') == 'Stock Option':
            asset_description = kwargs.get('asset_description')
            option_type_match = re.search(
                r'Option Type: (\w+)', asset_description)
            if option_type_match:
                kwargs['option_type'] = option_type_match.group(1)
            strike_price_match = re.search(
                r'Strike price:</em> (\d+\.\d+)', asset_description)
            if strike_price_match:
                kwargs['strike_price'] = strike_price_match.group(1)
            expiration_date_match = re.search(
                r'Expires:</em> (\d{2}/\d{2}/\d{4})', asset_description)
            if expiration_date_match:
                kwargs['expiration_date'] = expiration_date_match.group(1)
        super().__init__(**kwargs)


class AllSenateTransactionModel(Base):
    __tablename__ = 'all_senate_transactions'

    id = Column(Integer, primary_key=True)
    senator = Column(String)
    ptr_link = Column(String)
    transaction_date = Column(String)
    disclosure_date = Column(String)
    owner = Column(String)
    ticker = Column(String)
    asset_description = Column(String)
    asset_type = Column(String)
    transaction_type = Column(String)
    amount = Column(String)
    comment = Column(String)
    party = Column(String)
    state = Column(String)
    industry = Column(String)
    sector = Column(String)
    option_type = Column(String)
    strike_price = Column(String)
    expiration_date = Column(String)
    transaction_date_dt = Column(DateTime, index=True)
    disclosure_date_dt = Column(DateTime, index=True)
    disclosure_delay = Column(Integer)


    def __init__(self, **kwargs):
        # Concatenate the first_name and last_name columns to create the politician column
        if kwargs.get('asset_type') == 'Stock Option':
            asset_description = kwargs.get('asset_description')
            option_type_match = re.search(
                r'Option Type: (\w+)', asset_description)
            if option_type_match:
                kwargs['option_type'] = option_type_match.group(1)
            strike_price_match = re.search(
                r'Strike price:</em> (\d+\.\d+)', asset_description)
            if strike_price_match:
                kwargs['strike_price'] = strike_price_match.group(1)
            expiration_date_match = re.search(
                r'Expires:</em> (\d{2}/\d{2}/\d{4})', asset_description)
            if expiration_date_match:
                kwargs['expiration_date'] = expiration_date_match.group(1)
        super().__init__(**kwargs)


class AllHouseTransactionModel(Base):
    __tablename__ = 'all_house_transactions'

    id = Column(Integer, primary_key=True)
    representative = Column(String)
    office = Column(String)
    ptr_link = Column(String)
    transaction_date = Column(String)
    owner = Column(String)
    ticker = Column(String)
    asset_description = Column(String)
    district = Column(String)
    transaction_type = Column(String)
    amount = Column(String)
    party = Column(String)
    state = Column(String)
    industry = Column(String)
    sector = Column(String)
    option_type = Column(String)
    strike_price = Column(String)
    expiration_date = Column(String)
    disclosure_date = Column(String)
    transaction_date_dt = Column(DateTime, index=True)
    disclosure_date_dt = Column(DateTime, index=True)
    disclosure_delay = Column(Integer)



    def __init__(self, **kwargs):
        if kwargs.get('asset_type') == 'Stock Option':
            asset_description = kwargs.get('asset_description')
            option_type_match = re.search(
                r'Option Type: (\w+)', asset_description)
            if option_type_match:
                kwargs['option_type'] = option_type_match.group(1)
            strike_price_match = re.search(
                r'Strike price:</em> (\d+\.\d+)', asset_description)
            if strike_price_match:
                kwargs['strike_price'] = strike_price_match.group(1)
            expiration_date_match = re.search(
                r'Expires:</em> (\d{2}/\d{2}/\d{4})', asset_description)
            if expiration_date_match:
                kwargs['expiration_date'] = expiration_date_match.group(1)
        super().__init__(**kwargs)


class TickerTransactionModel(Base):
    __tablename__ = 'ticker_transactions'

    id = Column(Integer, primary_key=True)
    first_name = Column(String)
    last_name = Column(String)
    office = Column(String)
    ptr_link = Column(String)
    date_received = Column(String)
    transaction_date = Column(String)
    owner = Column(String)
    ticker = Column(String)
    asset_description = Column(String)
    asset_type = Column(String)
    transaction_type = Column(String)
    amount = Column(String)
    comment = Column(String)
    party = Column(String)
    state = Column(String)
    industry = Column(String)
    sector = Column(String)
    option_type = Column(String)
    strike_price = Column(String)
    expiration_date = Column(String)

    def __init__(self, **kwargs):
        if kwargs.get('asset_type') == 'Stock Option':
            asset_description = kwargs.get('asset_description')
            option_type_match = re.search(
                r'Option Type: (\w+)', asset_description)
            if option_type_match:
                kwargs['option_type'] = option_type_match.group(1)
            strike_price_match = re.search(
                r'Strike price:</em> (\d+\.\d+)', asset_description)
            if strike_price_match:
                kwargs['strike_price'] = strike_price_match.group(1)
            expiration_date_match = re.search(
                r'Expires:</em> (\d{2}/\d{2}/\d{4})', asset_description)
            if expiration_date_match:
                kwargs['expiration_date'] = expiration_date_match.group(1)
        super().__init__(**kwargs)

class TopRepresentativeModel(Base):
    __tablename__ = 'top_representatives'
    
    id = Column(Integer, primary_key=True)
    representative = Column(String)
    trade_frequency = Column(Integer)
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<TopRepresentativeModel(representative={self.representative}, trade_frequency={self.trade_frequency})>"
    
class TopSenatorModel(Base):
    __tablename__ = 'top_senator'

    id = Column(Integer, primary_key=True)
    senator = Column(String)
    trade_frequency = Column(Integer)
    last_updated = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<TopSenatorModel(senator={self.senator}, trade_frequency={self.trade_frequency})>"