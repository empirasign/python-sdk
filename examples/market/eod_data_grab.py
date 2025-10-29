#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eod_data_grab.py (End-of-Day Data Grab)

Pull down all market observations for a specific date.
Narrow down your search space by sector information or bond identifiers using _is_match function

Full API Documentation: https://www.empirasign.com/v1/market-api-docs/

API Usage Summary:
    HTTP METHOD     API ENDPOINT           QUOTA HIT                CLASS METHOD
    POST            /api/v1/bonds/         1 per bond               get_market_data
    GET             /api/v1/all-bonds/     None                     get_active_bonds

Sample Calls:
    ./eod_data_grab.py empirasign_20240717.sqlite -d2024-07-17
"""

import argparse
import datetime
import sqlite3
from pathlib import Path

from empirasign import MarketDataClient
from empirasign.utils import get_logger, create_sqlite_table, make_insertp
from empirasign.market.schemas import MARKET_DATA_SCHEMA

# ------------ USER CONFIGURATION ------------

# configurable constants
API_KEY = 'YOUR_EMPIRASIGN_API_KEY'
API_SECRET = 'YOUR_EMPIRASIGN_API_SECRET'
PROXY_SERVER = ""  # e.g. proxy.mycompany.net:8080
# if you get a 407 Proxy Authentication Required error, you need to set
# PROXY_SERVER to something like username:password@proxy.mycompany.net:8080

WORK_DIR = Path('')  # where the sqlite and log files will be saved
DB_NAME = 'eod_data_grab.sqlite'
LOG_NAME = 'eod_data_grab.log'

# ------------ END USER CONFIGURATION ------------

BONDS_IDX = {
    'idx_bbg_ticker': 'bbg_ticker',
    'idx_cusip': 'cusip',
    'idx_isin': 'isin'
}

MARKET_DATA_FLDS = [fld for fld, _ in MARKET_DATA_SCHEMA]

logger = get_logger(WORK_DIR / LOG_NAME)


def _is_match(bond):
    """
    customize your own filter rules to capture the securities you are interested in
    using specific identifiers or sector data from OpenFIGI

    figi_securitytype2: empirasign.utils.SECTYPES2
    figi_securitytype:  empirasign.utils.SECTYPES

    This particular example is filtering for CLOs using security types
    """
    sectype2, sectype = bond['figi_securitytype2'], bond['figi_securitytype']
    return sectype2 in ('LL', 'MML') or (sectype2 == 'ABS Other' and
                                         sectype in ('CF', 'MV', 'HB', 'SN'))


def main():
    """
    the main event
    """
    parser = argparse.ArgumentParser(description='pull all market data for a given date')
    parser.add_argument('-d', dest='dt', help='trade date as YYYY-MM-DD')
    args = parser.parse_args()

    if args.dt:
        trade_dt = datetime.datetime.strptime(args.dt, r"%Y-%m-%d")
    else:
        trade_dt = datetime.date.today()

    # create SQLite database and table
    conn = sqlite3.connect(WORK_DIR / DB_NAME)
    create_sqlite_table(conn, 'trade_data', MARKET_DATA_SCHEMA, BONDS_IDX)
    logger.info("made table at SQLite database file: %s", str(WORK_DIR / DB_NAME))

    # create API object with my credentials
    api = MarketDataClient(API_KEY, API_SECRET, PROXY_SERVER)

    # Step 1: get all bonds that appeared on BWICs or Dealer Runs on specified trade date
    all_active_bonds = api.get_active_bonds(trade_dt, "Mtge")['bonds']
    logger.info("%s ISINs have market data for date: %s", len(all_active_bonds), trade_dt)

    # Step 2: filter down active ISINs to those that pass our requirements
    active_isins = [bond['isin'] for bond in all_active_bonds if _is_match(bond)]
    logger.info("%s ISINs match our requirements: %s", len(active_isins), trade_dt)

    # Step 3: pull down all market observations for filtered ISINs
    resp = api.get_market_data(active_isins, date_args=trade_dt)
    logger.info("%s errors, %s warnings, %s results",
                 len(resp['meta']['errors']), len(resp['meta']['warnings']), len(resp['data']))

    # store market observations in SQLite table
    cursor = conn.cursor()
    insert_query = make_insertp("trade_data", MARKET_DATA_FLDS)
    insert_rows = [[row.get(field) for field in MARKET_DATA_FLDS] for row in resp['data']]
    cursor.executemany(insert_query, insert_rows)
    conn.commit()
    cursor.close()

    logger.info("inserted %s market data records", len(resp['data']))

    conn.close()
    logger.info("job done, db: %s closed", str(WORK_DIR / DB_NAME))


if __name__ == "__main__":
    main()
