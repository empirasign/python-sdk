# -*- coding: utf-8 -*-
"""
market/schemas.py

Return schemas and their sqlite data types for Empirasign Market Data API
Refer to /examples/market for use patterns
"""

# all possible columns across /bonds/ market observations
MARKET_DATA_SCHEMA = (
    ('kind', 'TEXT'),  # 'bid', 'offer', 'market', 'bwic', 'pxtalk'
    ('cusip', 'TEXT'),
    ('isin', 'TEXT'),
    ('figi', 'TEXT'),
    ('bbg_ticker', 'TEXT'),
    ('list_id', 'TEXT'),
    ('of', 'REAL'),
    ('cf', 'REAL'),
    ('of_bid', 'REAL'),
    ('of_offer', 'REAL'),
    ('cf_bid', 'REAL'),
    ('cf_offer', 'REAL'),
    ('color', 'TEXT'),
    ('price_raw', 'TEXT'),
    ('price', 'TEXT'),
    ('price_bid', 'TEXT'),
    ('price_offer', 'TEXT'),
    ('price32', 'TEXT'),
    ('price32_bid', 'TEXT'),
    ('price32_offer', 'TEXT'),
    ('spread_raw', 'TEXT'),
    ('spread', 'TEXT'),
    ('spread_bid', 'TEXT'),
    ('spread_offer', 'TEXT'),
    ('curve', 'TEXT'),
    ('speed', 'REAL'),
    ('speed_type', 'TEXT'),
    ('cf_scenario', 'TEXT'),
    ('group', 'REAL'),
    ('dealer', 'TEXT'),
    ("bsym_sec_type", "TEXT"),
    ('trade_dt', 'TEXT'),  #ISO 8601 FORMAT
    ('trade_datetime_utc', 'TEXT'),  #ISO 8601 FORMAT
    ('settle_dt', 'TEXT'),  #ISO 8601 FORMAT
    ('dealer_notes', 'TEXT')
)

# /offers/
RUNS_SCHEMA = (
    ("kind", "TEXT"),  # bid, offer, market
    ("bbg_ticker", "TEXT"),
    ("cusip", "TEXT"),
    ("isin", "TEXT"),
    ("figi", "TEXT"),
    ("of_offer", "REAL"),
    ("cf_offer", "REAL"),
    ("price_offer", "TEXT"),
    ("price32_offer", "TEXT"),
    ("spread_offer", "TEXT"),
    ("curve", "TEXT"),
    ("speed", "TEXT"),
    ("speed_type", "TEXT"),
    ("cf_scenario", "TEXT"),
    ("of_bid", "REAL"),
    ("cf_bid", "REAL"),
    ("price_bid", "TEXT"),
    ("price32_bid", "TEXT"),
    ("spread_bid", "TEXT"),
    ("dealer", "TEXT"),
    ("bsym_sec_type", "TEXT"),
    ("trade_dt", "TEXT"),  #ISO 8601 FORMAT
    ("settle_dt", "TEXT"),  #ISO 8601 FORMAT
    ("dealer_notes", "TEXT"),
)

# /corp-bonds/ & /corp-runs/
CORP_SCHEMA = (
    ("cusip", "TEXT"),
    ("isin", "TEXT"),
    ("figi", "TEXT"),
    ("bbg_ticker", "TEXT"),
    ("size_bid", "REAL"),
    ("size_offer", "REAL"),
    ("price_bid", "REAL"),
    ("price_offer", "REAL"),
    ("spread_bid", "REAL"),
    ("spread_offer", "REAL"),
    ("curve", "TEXT"),
    ("yield_bid", "REAL"),
    ("yield_offer", "REAL"),
    ("axe_bid", "REAL"),
    ("axe_offer", "REAL"),
    ("trade_dt", "TEXT"),  # ISO 8601 FORMAT
    ("settle_dt", "TEXT"),  # ISO 8601 FORMAT
    ("dealer", "TEXT"),
    ("dealer_notes", "TEXT"),
    ("msg_received", "TEXT"),  # ISO 8601 FORMAT
)
