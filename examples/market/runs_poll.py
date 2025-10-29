#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runs_poll.py

This script optimally uses the Empirasign API to monitor and store active Dealer Runs
in real-time for selected sectors.

Full API Documentation: https://www.empirasign.com/v1/market-api-docs/

API Usage Summary:
    HTTP METHOD     API ENDPOINT           QUOTA HIT                CLASS METHOD
    GET             /api/v1/offers/        None                     get_available_runs
    GET             /api/v1/offers/        1 per offer              get_dealer_runs

Sample Calls:
    ./runs_watcher.py -s cmbs -C
    (watch CMBS sector, create new sqlite databse)

    ./runs_watcher.py -s agcmo naresi
    (watch Agency CMO and Non-Ag resi sectors, use existing DB)

    ./runs_watcher.py -s abs -o
    (check ABS sector once, use existing DB)
"""

import sys
import sqlite3
import argparse
from time import sleep
from datetime import datetime, time, timezone
from pathlib import Path

from empirasign import MarketDataClient
from empirasign.market.schemas import RUNS_SCHEMA
from empirasign.utils import get_logger, upsert, create_sqlite_table
from empirasign.constants import RUNS_SECTORS

# ------------ USER CONFIGURATION ------------

API_KEY = "YOUR_EMPIRASIGN_API_KEY"
API_SECRET = "YOUR_EMPIRASIGN_API_SECRET"
PROXY_SERVER = ""  #e.g. proxy.mycompany.net:8080
# if you get a 407 Proxy Authentication Required error, you need to set
# PROXY_SERVER to something like username:password@proxy.mycompany.net:8080

WORK_DIR = Path()  # where the sqlite and log files will be saved
DB_NAME = "runs_poll.sqlite"  # name of sqlite database file (all tables live here)
TBL_NAME = "runs_records"
LOG_NAME = "runs_poll.log"

# time of day to stop polling for new market data (in UTC)
# preconfigured here to stop polling at 21:30 UTC, or 5:30 EST
# this parameter needs to be adjusted for daylight savings time
STOP_HOUR = 21
STOP_MINUTE = 30

# ------------ END USER CONFIGURATION ------------

RUNS_FLDS = [fld for fld, _ in RUNS_SCHEMA]

logger = get_logger(WORK_DIR / LOG_NAME)


def validate_sectors(sectors):
    """
    check that user-entered sectors are valid
    """
    if "ALL" in sectors:
        return RUNS_SECTORS

    if not sectors:
        logger.error("Halting Execution: You must select one or more of the following sectors: %s",
                     RUNS_SECTORS)
        sys.exit(1)

    sectors = [sector.lower() for sector in sectors]
    invalid_sectors = set(sectors) - set(RUNS_SECTORS)
    if invalid_sectors:
        logger.error("Halting Execution: Invalid sector(s): %s", invalid_sectors)
        sys.exit(1)

    return sectors


def get_active_runs(api, sectors, date_args):
    """
    get active dealer runs in sectors of interest
    """
    resp = api.get_available_runs(date_args)
    if resp["meta"]["results"] != "OK":
        logger.error("FAILURE! searching for active runs, errors: %s", resp["meta"]["errors"])
        sys.exit(1)

    active_runs = [run for run in resp["available"] if run["sector"] in sectors]
    return active_runs


def get_runs_records(api, runs, date_args, quota):
    """
    get dealer bids, offers, and markets on given runs
    """
    records = []
    record_types = ("offers", "bids", "markets")
    low_quota = False
    for run in runs:
        if quota < run['num_records']:
            logger.warning("not enough quota, ending active runs search early")
            low_quota = True
            break

        resp = api.get_dealer_runs(run["dealer"], run["sector"], date_args)
        if resp["meta"]["errors"]:
            logger.error("FAILURE! fetching runs data, errors: %s", resp["meta"]["errors"])
            sys.exit(1)
        for record_type in record_types:
            records.extend(resp.get(record_type, []))
        quota = resp["meta"]["requests_left"]

    return records, low_quota


def get_updated_records(cursor, runs_records):
    """
    update db with new and updated dealer runs records
    """
    pks = ("kind", "bbg_ticker", "trade_dt", "dealer")
    new_records, updated_records = 0, 0
    for record in runs_records:
        record = {key: value for key, value in record.items() if key in RUNS_FLDS}
        res = upsert(cursor, "runs_records", pks, record, ph="?")
        if res == "INSERT":
            new_records += 1
        elif res == "UPDATE":
            updated_records += 1
    return new_records, updated_records


def main():
    """
    the main event
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("-s",
                        "--sectors",
                        dest="sectors",
                        nargs="+",
                        type=str,
                        help=("sectors to watch, separated by space. "
                              "enter 'ALL' to monitor all sectors. "
                              f"sectors: {RUNS_SECTORS}"))
    parser.add_argument("-C", dest="create_db", action="store_true")
    parser.add_argument("-o",
                        "--one-shot",
                        action="store_true",
                        dest="one_shot",
                        help="run once, no looping")
    parser.add_argument("-v", action="store_true", dest="verbose", help="log all debugging info")
    parser.add_argument("-t", dest="start_time", type=str,
                        help=("the hour and minute (HH:MM) in UTC from which to start "
                              "retrieving runs data. only runs records that were created or "
                              "updated after will be returned."))
    args = parser.parse_args()

    sectors = validate_sectors(args.sectors)

    trade_dt = datetime.now(timezone.utc).date()
    logger.info('polling dealer runs from %s', trade_dt)

    if args.start_time:
        start_time = datetime.strptime(args.start_time, '%H:%M').time()
    else:
        start_time = time(0, 0)
    start_time = datetime.combine(trade_dt, start_time, timezone.utc)
    stop_time = datetime.combine(trade_dt, time(STOP_HOUR, STOP_MINUTE), tzinfo=timezone.utc)

    api = MarketDataClient(API_KEY, API_SECRET, PROXY_SERVER)
    api.verbose = bool(args.verbose)

    conn = sqlite3.connect(WORK_DIR / DB_NAME)
    if args.create_db:
        create_sqlite_table(conn, TBL_NAME, RUNS_SCHEMA, {'idx_bbg_ticker': 'bbg_ticker'})

    try:
        cursor = conn.cursor()
        low_quota = False
        exec_count = 1
        d0 = start_time
        while (d1 := datetime.now(timezone.utc)) and d1 < stop_time:
            quota = api.quota
            logger.info("starting execution #%s, watching sector(s): %s, queries remaining: %s",
                        exec_count, ", ".join(sectors), quota)

            # get all dealers with runs in specified sectors
            active_runs = get_active_runs(api, sectors, (d0, d1))
            logger.info("%s active dealer runs since %s in %s ",
                        len(active_runs), d0.strftime('%H:%M'), ", ".join(sectors))
            if active_runs:
                logger.info("retrieving records now...")
                # bids, offers, markets
                runs_records, low_quota = get_runs_records(api, active_runs, (d0, d1), quota)
                new_records, updated_records = get_updated_records(cursor, runs_records)
                if new_records or updated_records:
                    conn.commit()
                    logger.info("%s new, %s updated dealer runs records", new_records,
                                updated_records)
                sleep_time = 60 # DO NOT POLL SERVER MORE THAN ONCE PER MINUTE
            else:
                sleep_time = 120 # IF NO ACTIVE BONDS, WAIT TWO MINUTES BEFORE NEXT POLL

            if args.one_shot:
                logger.info("dealer runs watcher executed once, now exiting")
                break
            if low_quota:
                logger.warning("running low on queries, now exiting")
                break
            logger.info("waiting %s seconds before next iteration", sleep_time)
            sleep(sleep_time)
            exec_count += 1
            d0 = d1
        if not args.one_shot and not low_quota:
            logger.info("it's after designated stop time {:02d}:{:02d} UTC, now exiting".format(
                STOP_HOUR, STOP_MINUTE))
    except KeyboardInterrupt:
        logger.warning("user hit CTRL-C, now exiting")
    except Exception:  # pylint: disable=broad-except
        logger.exception("fatal error", exc_info=True)
    finally:
        logger.info("closing sqlite connection")
        conn.close()


if __name__ == "__main__":
    main()
