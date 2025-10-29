#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
corp_poll.py

The goal of this script is to optimize usage of the Empiriasign API to pull down
corporate quotes in real-time.

Full API Documentation: https://www.empirasign.com/market-api-docs/

API Usage Summary:
    HTTP METHOD     API ENDPOINT           QUOTA HIT                CLASS METHOD
    POST            /api/v1/corp-bonds/    1 per bond, per page     get_corp_market_data
    GET             /api/v1/corp-runs/     None                     get_corp_available_runs

Sample Calls:
    ./corp_poll.py -C -s60  (poll quotes in 60 sec intervals, create new database)
    ./corp_poll.py -s300    (poll quotes in 5 min intervals, use existing database)
"""

import time
import argparse
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from empirasign import MarketDataClient
from empirasign.market.schemas import CORP_SCHEMA
from empirasign.utils import get_logger, make_insertp, chunker, create_sqlite_table

# ------------ USER CONFIGURATION ------------

API_KEY = 'YOUR_EMPIRASIGN_API_KEY'
API_SECRET = 'YOUR_EMPIRASIGN_API_SECRET'
PROXY_SERVER = ""  # e.g. proxy.mycompany.net:8080
# if you get a 407 Proxy Authentication Required error, you need to set
# PROXY_SERVER to something like username:password@proxy.mycompany.net:8080

WORK_DIR = Path()  # where the sqlite and log files will be saved
DB_NAME = 'corp_poll.sqlite'
LOG_NAME = 'corp_poll.log'
TBL_NAME = 'corp_quotes'

ISINS = set()  # the ISINs we care about
DEALERS = set()  # the dealers we care about

# ------------ END USER CONFIGURATION ------------

logger = get_logger(WORK_DIR / LOG_NAME)

CORP_FLDS = [fld for fld, _ in CORP_SCHEMA]


def _filter_available_quotes(available, dealers, isins):
    """
    filter down available quotes to isins that we care about
    """
    filtered_isins = set()
    for dealer, dealer_meta in available.items():
        if dealers and dealer not in dealers:
            continue
        dealer_isins = set(dealer_meta['isins'])
        if isins:
            dealer_isins = dealer_isins & isins
        filtered_isins.update(dealer_isins)

    return filtered_isins


def _filter_quotes(quotes, dealers):
    """
    filter down to quotes by dealers that we care about
    """
    quotes = [quote for quote in quotes if quote.get('dealer') in dealers]
    return quotes


def _insert_quotes(cursor, tbl_name, records):
    """
    insert quotes into SQLite tbl
    """
    for record in records:
        q = make_insertp(tbl_name, CORP_FLDS)
        cursor.execute(q, tuple(record.get(k) for k in CORP_FLDS))


def main():
    """
    the main event
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("-C", dest="create_db", action="store_true", help="build sqlite database")
    parser.add_argument("-s", dest="delay", type=int, help="poll delay, in seconds")
    parser.add_argument("-d", dest="trade_dt", help="date as YYYY-MM-DD")
    args = parser.parse_args()

    # authenticate
    api = MarketDataClient(API_KEY, API_SECRET, PROXY_SERVER)
    api.verbose = True

    # the market trade date (UTC) that we are polling
    if args.trade_dt:
        trade_dt = datetime.strptime(args.trade_dt, "%Y-%m-%d").date()
    else:
        trade_dt = datetime.now(timezone.utc).date()

    # lower and upper bounds of our polling window
    start_time = datetime(trade_dt.year, trade_dt.month, trade_dt.day, 0, 0, 0)
    stop_time = datetime(trade_dt.year, trade_dt.month, trade_dt.day, 23, 59, 59)
    start_time = start_time.replace(tzinfo=timezone.utc)
    stop_time = stop_time.replace(tzinfo=timezone.utc)
    logger.info('polling corporate quotes from %s to %s (UTC)', start_time, stop_time)

    if ISINS or DEALERS:
        logger.info('filtering new quotes from %s specific ISINs, %s specific dealers', len(ISINS), len(DEALERS))

    conn = sqlite3.connect(WORK_DIR / DB_NAME)
    if args.create_db:
        create_sqlite_table(conn, TBL_NAME, CORP_SCHEMA)

    try:
        cursor = conn.cursor()
        d0 = start_time
        while (d1 := datetime.now(timezone.utc)) and d1 < stop_time:

            if api.quota == 0:
                logger.info('daily Empirasign API quota has been exhausted, stop polling')
                break

            d0_fmt, d1_fmt = d0.strftime("%Y-%m-%dT%H:%M:%S"), d1.strftime("%Y-%m-%dT%H:%M:%S")
            logger.info("polling for new quotes within adjusted timeframe [%s, %s)", d0_fmt, d1_fmt)

            # get meta data about new quotes in our timeframe
            available = api.get_corp_available_runs((d0, d1))['available']
            # filter out ISINs and/or dealers we are not interested in
            query_isins = _filter_available_quotes(available, DEALERS, ISINS)
            logger.info('%s isins with new quotes available within our constraints', len(query_isins))

            # pull down new quotes, 100 ISINs at a time (max per request)
            new_quotes = []
            for isins_chunk in chunker(query_isins, 100):
                results = api.get_corp_market_data(isins_chunk, (d0, d1))
                new_quotes.extend(results['data'])

            logger.info('pulled down %s new quotes', len(new_quotes))
            new_quotes = _filter_quotes(new_quotes, DEALERS)
            logger.info('%s new quotes within our constraints', len(new_quotes))
            # store new quotes any way you please
            _insert_quotes(cursor, TBL_NAME, new_quotes)

            conn.commit()
            logger.info('inserted %s new quotes', len(new_quotes))

            if args.delay:  # optional poll delay
                next_poll = d1 + timedelta(seconds=args.delay)
                sleep_secs = max((next_poll - datetime.now(timezone.utc)).total_seconds(), 0)
                logger.info('waiting %s seconds until next poll', sleep_secs)
                time.sleep(sleep_secs)

            # adjust search timeframe, ensuring we miss nothing new
            d0 = d1

        logger.info('our polling window has completed, exiting...')

    except KeyboardInterrupt:
        logger.warning("user hit CTRL-C, now exiting")
    except Exception:  # pylint: disable=broad-except
        logger.exception("fatal error", exc_info=True)
    finally:
        logger.info("closing sqlite connection")
        conn.close()


if __name__ == "__main__":
    main()
