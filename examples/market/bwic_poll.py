#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bwic_poll.py

This script optimally uses the Empirasign API to pull down BWICs and associated
market data in real-time.

Full API Documentation: https://www.empirasign.com/market-api-docs/

API Usage Summary:
    HTTP METHOD     API ENDPOINT           QUOTA HIT                CLASS METHOD
    POST            /api/v1/bonds/         1 per bond               get_market_data
    GET             /api/v1/bwics/         None                     get_bwics

Sample Calls:
    ./bwic_poll.py -s cmbs -C       (watch CMBS sector, create new sqlite database)
    ./bwic_poll.py -s agcmo naresi  (query Agency CMO and Non-Ag resi, use existing database)
"""

import sys
import json
import sqlite3
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path

from empirasign import MarketDataClient
from empirasign.utils import get_logger, upsert, create_sqlite_table
from empirasign.constants import BWIC_SECTORS
from empirasign.market.schemas import MARKET_DATA_SCHEMA

# ------------ USER CONFIGURATION ------------

API_KEY = 'YOUR_EMPIRASIGN_API_KEY'
API_SECRET = 'YOUR_EMPIRASIGN_API_SECRET'
PROXY_SERVER = ""  # e.g. proxy.mycompany.net:8080
# if you get a 407 Proxy Authentication Required error, you need to set
# PROXY_SERVER to something like username:password@proxy.mycompany.net:8080

WORK_DIR = Path()  # where the sqlite and log files will be saved
DB_NAME = 'bwic_poll.sqlite'
LOG_NAME = 'bwic_poll.log'

# stop polling for new market data 21:30 UTC, or 5:30 EST
# this parameter needs to be adjusted when daylight savings time switches
STOP_HOUR = 21
STOP_MINUTE = 30

# ------------ END USER CONFIGURATION ------------

logger = get_logger(WORK_DIR / LOG_NAME)

# information about bwics
# subset of /bwics/ return schema
BWIC_SCHEMA = (
    ('list_id', 'TEXT'),
    ("num_bonds", 'INTEGER'),
    ("num_color", 'INTEGER'),
    ("num_talk", 'INTEGER'),
    ("uids", 'TEXT')  # json encoded list of cusips and/or isins
)
BWIC_FLDS = [fld for fld, _ in BWIC_SCHEMA]

MARKET_DATA_FLDS = [fld for fld, _ in MARKET_DATA_SCHEMA]


def get_bwic_data(api, dt, sectors):
    """
    performs request on the specified singular sector and return all relevant data
    """
    data = {}
    for sector in sectors:
        resp_json = api.get_bwics(sector, date_args=dt)
        if not resp_json or resp_json['meta']['results'] != "OK":
            logger.error("FAILURE while querying for %s", sector)
            return []

        for row in resp_json['data']:
            data[row['list_id']] = {
                'uids': row['uids'],
                'num_bonds': row['num_bonds'],
                'num_color': row['num_color'],
                'num_talk': row['num_talk'],
            }
    return data


def get_trade_data(api, dt, uids):
    """
    get trade data for a list of uids
    uids can be of any length
    requests are chunked in groups of 200 per call (current max api query size)
    """
    resp_json = api.get_market_data(uids, date_args=dt)
    if errors := resp_json['meta']['errors']:
        logger.warning(errors)
    if warnings := resp_json['meta']['warnings']:
        logger.warning(warnings)
    return resp_json['data']

#--------- Market Data Munging, Diffing and Database related functions ---------

def uids_from_bwics(bwics, items):
    """
    used to make sure we only query unique cusips/isins as a bond may
    appear on more than one bwic in a given day
    """
    uids = []
    for list_id in items:
        uids.extend(bwics[list_id]['uids'])
    return list(set(uids))


def update_bwics(cursor, bwics):
    """
    insert or update a group of bwics
    figure out which bwics are new, or have changes that need new data retrievals
    """
    new_bwics, changed_bwics = [], []
    for list_id, _obj in bwics.items():
        obj = {key: value for key, value in _obj.items() if key in BWIC_FLDS}
        obj['list_id'] = list_id
        obj['uids'] = json.dumps(_obj['uids'])  # so we can insert into sqlite
        pks = ('list_id',)
        res = upsert(cursor, 'bwics', pks, obj, ph="?")
        if res == 'INSERT':
            new_bwics.append(list_id)
        elif res == 'UPDATE':
            changed_bwics.append(list_id)
    return new_bwics, changed_bwics


def update_bonds(cursor, mkt_data):
    """
    insert or update a group of bonds
    figure out which bonds are new, or have changes that need new data retrievals
    """
    new_bonds, changed_bonds = [], []
    pks = {
        'bid': ('kind', 'bbg_ticker', 'trade_dt', 'dealer'),
        'offer': ('kind', 'bbg_ticker', 'trade_dt', 'dealer'),
        'market': ('kind', 'bbg_ticker', 'trade_dt', 'dealer'),
        'bwic': ('kind', 'bbg_ticker', 'list_id'),
        'pxtalk': ('kind', 'bbg_ticker', 'list_id', 'dealer')
    }
    for bond in mkt_data:
        curr_pks = pks[bond.get("kind", "bwic")]
        bond = {key: value for key, value in bond.items() if key in MARKET_DATA_FLDS or key in curr_pks}
        res = upsert(cursor, 'trade_data', curr_pks, bond, ph="?")
        if res == 'INSERT':
            new_bonds.append(bond['bbg_ticker'])
        elif res == 'UPDATE':
            changed_bonds.append(bond['bbg_ticker'])

    return new_bonds, changed_bonds


def main():
    """
    the main event
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--sectors", dest="sectors", nargs="+", type=str)
    parser.add_argument("-C", dest='create_db', action="store_true")
    parser.add_argument("-o",
                        "--one-shot",
                        action='store_true',
                        dest="one_shot",
                        help="run once, no looping")
    parser.add_argument("-d", dest="trade_dt", help="date as YYYY-MM-DD")
    parser.add_argument("-v", action="store_true", dest="verbose", help="log all debugging info")
    args = parser.parse_args()

    # authenticate
    api = MarketDataClient(API_KEY, API_SECRET, PROXY_SERVER)
    if args.verbose:
        api.verbose = True

    # the market trade date (UTC) that we are polling
    if args.trade_dt:
        trade_dt = datetime.strptime(args.trade_dt, "%Y-%m-%d").date()
    else:
        trade_dt = datetime.now(timezone.utc).date()
    logger.info('polling bwic quotes from %s', trade_dt)

    # set time when polling stops
    today = datetime.today()
    stop_time = datetime(today.year, today.month, today.day, STOP_HOUR, STOP_MINUTE, 00)
    stop_time = stop_time.replace(tzinfo=timezone.utc)

    sectors = args.sectors
    if not args.sectors or "ALL" in args.sectors:
        sectors = ('mtge',)

    invalid_sectors = set(sectors) - set(BWIC_SECTORS)
    if invalid_sectors:
        logger.error("Halting Execution: Invalid sector(s): %s", invalid_sectors)
        sys.exit()

    conn = sqlite3.connect(WORK_DIR / DB_NAME)
    if args.create_db:
        create_sqlite_table(conn, 'bwics', BWIC_SCHEMA, indices={'idx_bbg_ticker': 'list_id'})
        create_sqlite_table(conn, 'trade_data', MARKET_DATA_SCHEMA, indices={'idx_list_id': 'bbg_ticker'})

    try:
        cursor = conn.cursor()
        quota_left = 0
        while (dt := datetime.now(timezone.utc)) and dt < stop_time:

            quota_left = api.quota
            if quota_left == 0:
                logger.info('daily Empirasign API quota has been exhausted, stop polling')
                break

            # pull down new BWIC data
            bwics = get_bwic_data(api, trade_dt, sectors)
            new_bwics, changed_bwics = update_bwics(cursor, bwics)
            logger.info("%s new BWICs, %s changed BWICs", len(new_bwics), len(changed_bwics))

            if new_bwics or changed_bwics:
                conn.commit()
                uids = uids_from_bwics(bwics, set(new_bwics + changed_bwics))
                logger.info("retrieving market data on %s unique bonds", len(uids))
                mkt_data = get_trade_data(api, trade_dt, uids)
                new_bonds, changed_bonds = update_bonds(cursor, mkt_data)
                logger.info("%s new bonds, %s changed bonds", len(new_bonds), len(changed_bonds))
                if new_bonds or changed_bonds:
                    conn.commit()
                sleep_time = 60
            else:
                sleep_time = 120

            if args.one_shot:
                logger.info("ran sector(s) %s once, now exiting main loop", sectors)
                break
            logger.info("waiting %s seconds before next iteration", sleep_time)
            time.sleep(sleep_time)

        if quota_left and not args.one_shot:
            logger.info("it's after designated stop time {:02d}:{:02d} UTC, now exiting".format(STOP_HOUR, STOP_MINUTE))

    except KeyboardInterrupt:
        logger.warning("user hit CTRL-C, now exiting")
    except Exception:  # pylint: disable=broad-except
        logger.exception("fatal error", exc_info=True)
    finally:
        logger.info("closing sqlite connection")
        conn.close()


if __name__ == "__main__":
    main()
