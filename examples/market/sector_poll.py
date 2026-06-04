#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sector_poll.py

This script optimally uses the Empirasign API to monitor and store active BWICs & Dealer Runs
in real-time for selected sectors.

This script is meant to outline a combined use-case for the separate bwic_poll.py and runs_poll.py
example scripts.

Full API Documentation: https://www.empirasign.com/v1/market-api-docs/

API Usage Summary:
    HTTP METHOD     API ENDPOINT           QUOTA HIT                CLASS METHOD
    GET             /api/v1/bwics/         None                     get_bwics
    GET             /api/v1/offers/        None                     get_available_runs
    POST            /api/v1/bonds/         1 per bond               get_market_data

Sample Calls:

    ./sector_poll.py -B -R -C
            (poll BWICs & Runs for all sectors, overwrite new SQLite database)
    ./sector_poll.py -B -C
            (poll BWICs for all sectors, overwrite new SQLite database)
    ./sector_poll.py -B cmbs -R cmbs -C
            (poll BWICs & Runs for specific sectors, overwrite new SQLite database)
    ./sector_poll.py -B agcmo naresi -R nonag
            (poll specific BWIC & Runs sectors, use existing SQLite database)
    ./sector_poll.py -B abs --one-shot
            (poll for ABS BWICs once, use existing SQLite database)
"""
import sys
import sqlite3
import argparse
from time import sleep
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict, namedtuple

from empirasign import MarketDataClient
from empirasign.market.schemas import BWIC_SCHEMA, MARKET_DATA_SCHEMA
from empirasign.utils import get_logger, upsert, create_sqlite_table, chunker
from empirasign.constants import RUNS_SECTORS, BWIC_SECTORS

# ------------ USER CONFIGURATION ------------

API_KEY = 'YOUR_EMPIRASIGN_API_KEY'
API_SECRET = 'YOUR_EMPIRASIGN_API_SECRET'
PROXY_SERVER = ""  #e.g. proxy.mycompany.net:8080
# if you get a 407 Proxy Authentication Required error, you need to set
# PROXY_SERVER to something like username:password@proxy.mycompany.net:8080

WORK_DIR = Path()  # where the sqlite and log files will be saved
DB_NAME = "sector_poll.sqlite"  # name of sqlite database file (all tables live here)
LOG_NAME = "sector_poll.log"

# poll for new market data between 06:00 and 22:30 UTC, or 02:00 AM and 6:30 PM EST
DEFAULT_START_UTC = "06:00"
DEFAULT_END_UTC = "22:30"  # needs to be adjusted when daylight savings time switches

# ------------ END USER CONFIGURATION ------------

logger = get_logger(WORK_DIR / LOG_NAME)

# Define the named tuple structure
Sectors = namedtuple('Sectors', ['bwic', 'runs'])

BWIC_FLDS = [fld for fld, _ in BWIC_SCHEMA]
BWIC_INDICES = {'idx_list_id': 'list_id'}
MARKET_DATA_FLDS = [fld for fld, _ in MARKET_DATA_SCHEMA]
MARKET_DATA_INDICES = {'idx_bbg_ticker': 'bbg_ticker'}

# map a few major BWIC sectors to available Dealer Runs sectors for consistency
RUNS_SECTORS_MAP = {
    "clo": ("us-clo", "eu-clo"),
    "agency": ("agarm", "agcmo", "spec")
}
VALID_RUNS_ARGS = tuple(RUNS_SECTORS_MAP) + RUNS_SECTORS


# ------------ Argument Handlers ------------

def _validate_sectors(args):
    """
    check that user-entered sectors are valid
    """
    if args.bwic_sectors is None and args.runs_sectors is None:
        logger.error('Halting Execution: You must use --bwic or --runs flag, otherwise you are polling for nothing!')
        sys.exit(1)

    if args.bwic_sectors is None:
        bwic_sectors = []
    elif not args.bwic_sectors:  # flag present, defaults to all
        bwic_sectors = ['mtge']
    else:
        bwic_sectors = [sector.lower() for sector in args.bwic_sectors]

    if args.runs_sectors is None:
        runs_sectors = []
    elif not args.runs_sectors:  # flag present, defaults to all
        runs_sectors = RUNS_SECTORS
    else:
        runs_sectors = [sector.lower() for sector_arg in args.runs_sectors
                        for sector in RUNS_SECTORS_MAP.get(sector_arg, [sector_arg])]

    if invalid_sectors := set(bwic_sectors) - set(BWIC_SECTORS):
        logger.error("Halting Execution: Invalid BWIC sector(s): %s", invalid_sectors)
        sys.exit(1)
    if invalid_sectors := set(runs_sectors) - set(RUNS_SECTORS):
        logger.error("Halting Execution: Invalid Dealer Runs sector(s): %s", invalid_sectors)
        sys.exit(1)

    return Sectors(bwic_sectors, runs_sectors)


def _handle_time_args(market_date, args):
    """
    fall back on some sensible default arguments
    """
    start_time = datetime.strptime(args.start_time, '%H:%M').time()
    start_time = datetime.combine(market_date, start_time, tzinfo=timezone.utc)
    end_time = datetime.strptime(args.end_time, '%H:%M').time()
    end_time = datetime.combine(market_date, end_time, tzinfo=timezone.utc)
    return start_time, end_time

# ------------ Helpers ------------

def _get_active_runs(api, sectors, date_args):
    """
    get active Dealer Runs in provided sectors
    """
    if not sectors:
        return set()

    resp = api.get_available_runs(date_args)
    if resp["meta"]["results"] != "OK":
        logger.error("FAILURE! searching for active runs, errors: %s", resp["meta"]["errors"])
        return set()

    active_runs = [run for run in resp["available"] if run["sector"] in sectors]
    active_dealers = {run["dealer"] for run in active_runs}
    active_isins = {isin for run in active_runs for isin in run["isins"]}

    logger.info("%s active %s ISINs across %s dealer runs between [%s, %s)",
                len(active_isins), sectors, len(active_dealers),
                date_args[0].strftime('%H:%M'), date_args[1].strftime('%H:%M'))

    return active_isins


def _get_active_bwics(conn, api, sectors, dt):
    """
    get active BWICs in provided sectors
    """
    if not sectors:
        return set()

    bwics = {}
    for sector in sectors:
        resp_json = api.get_bwics(sector, date_args=dt)
        if not resp_json or resp_json['meta']['results'] != "OK":
            logger.error("FAILURE while querying for %s", sector)
            continue
        for row in resp_json["data"]:
            bwics[row["list_id"]] = {key: value for key, value in row.items() if key in BWIC_FLDS}

    # maintain state to determine new or updated BWICs
    list_ids = defaultdict(set)
    for list_id, _obj in bwics.items():
        obj = {key: value for key, value in _obj.items()}
        obj["isins"] = json.dumps(_obj["isins"])  # so we can insert into sqlite
        res = upsert(conn, "bwics_meta", ("list_id",), obj, ph="?")
        list_ids[res].add(list_id)
    if list_ids['INSERT'] or list_ids['UPDATE']:
        conn.commit()

    # get all ISINs on active BWICs
    active_isins = set()
    for list_id in list_ids['INSERT'] | list_ids['UPDATE']:
        active_isins |= set(bwics[list_id]['isins'])

    logger.info("%s active %s ISINs across (%s) new and (%s) updated BWICs",
                len(active_isins), sectors, len(list_ids['INSERT']), len(list_ids['UPDATE']))

    return active_isins


def _poll_active_isins(conn, api, sectors, trade_dt, d0, d1):
    """
    1. polls for new dealer runs in the provided time slice
    2. polls for new BWIC updates by checking state against SQLite backend
    3. returns a comprehensive set of ISINs that need to be queried
    """
    active_runs_isins = _get_active_runs(api, sectors.runs, (d0, d1))
    active_bwic_isins = _get_active_bwics(conn, api, sectors.bwic, trade_dt)
    return active_runs_isins | active_bwic_isins


def _pull_market_data(api, query_isins, trade_dt):
    """
    queries market data for active ISINs
    """
    logger.info("retrieving market data on %s unique bonds", len(query_isins))
    market_data = []
    quota_left = None
    # pull down new quotes, 100 ISINs at a time (max per request)
    for isins_chunk in chunker(query_isins, 100):
        resp_json = api.get_market_data(isins_chunk, date_args=trade_dt)
        if errors := resp_json['meta']['errors']:
            logger.warning(errors)
        if warnings := resp_json['meta']['warnings']:
            logger.warning(warnings)
        market_data.extend(resp_json['data'])
        quota_left = resp_json['meta']['requests_left']

    return market_data, quota_left


def _store_market_data(conn, market_data):
    """
    inserts and/or updates market observations according to record-type specific primary keys
    """
    pks = {
        'bid': ('kind', 'bbg_ticker', 'trade_dt', 'dealer'),
        'offer': ('kind', 'bbg_ticker', 'trade_dt', 'dealer'),
        'market': ('kind', 'bbg_ticker', 'trade_dt', 'dealer'),
        'bwic': ('kind', 'bbg_ticker', 'list_id'),
        'pxtalk': ('kind', 'bbg_ticker', 'list_id', 'dealer')
    }
    insert_logs, update_logs = defaultdict(int), defaultdict(int)
    for record in market_data:
        if record.get('kind') in pks:
            tmp_pks = pks[record['kind']]
            # conditionally add OF as PK, Spec pools can appear on same list twice w/ different OFs
            figi_securitytype = record.get('bsym_sec_type') or ''
            if record['kind'] in ('bwic', 'pxtalk') and figi_securitytype.startswith('MBS '):
                tmp_pks += ('of',)
            bond = {key: value for key, value in record.items() if key in MARKET_DATA_FLDS}
            res = upsert(conn, 'market_data', tmp_pks, bond, ph="?")
            if res == 'INSERT':
                insert_logs[bond['kind']] += 1
            elif res == 'UPDATE':
                update_logs[bond['kind']] += 1

    # log updates to our market data table
    logger.info('inserted: %s', ', '.join([f'{insert_logs[kind]} {kind}' for kind in pks]))
    logger.info('updated: %s', ', '.join([f'{update_logs[kind]} {kind}' for kind in pks]))

    if sum(insert_logs.values()) or sum(update_logs.values()):
        conn.commit()


def main():
    """
    the main event
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--bwics", dest="bwic_sectors", nargs="*", default=None,
                        metavar="abs",
                        help=("BWIC sectors to poll (space-separated). Using this flag without "
                              "specifying sector(s) will default to all sectors. Available BWIC "
                              f"sectors: {BWIC_SECTORS}"))
    parser.add_argument("-r", "--runs", dest="runs_sectors", nargs="*", default=None,
                        metavar="abs",
                        help=("Dealer Runs sectors to poll (space-separated). Using this flag "
                              "without specifying sector(s) will default to all sectors. Available"
                              f" Dealer Runs sectors: {VALID_RUNS_ARGS}"))
    parser.add_argument("-s", "--start", dest="start_time", type=str, metavar="06:00",
                        default=DEFAULT_START_UTC,
                        help="start of polling window (HH:MM) in UTC, defaults to 06:00")
    parser.add_argument("-e", "--end", dest="end_time", type=str, metavar="22:30",
                        default=DEFAULT_END_UTC,
                        help="end of polling window (HH:MM) in UTC, defaults to 22:30")
    parser.add_argument("-C", "--create-table", dest="create_db", action="store_true",
                        help="creates/overwrites new SQLite tables for demo backend")
    parser.add_argument("-O", "--one-shot", dest="one_shot", action="store_true",
                        help="poll once, no looping")
    parser.add_argument("-v", action="store_true", dest="verbose", help="log all debugging info")
    args = parser.parse_args()

    # configure client
    api = MarketDataClient(API_KEY, API_SECRET, PROXY_SERVER)
    api.verbose = bool(args.verbose)

    # handle script arguments
    market_date = datetime.now(timezone.utc).date()
    start_time, end_time = _handle_time_args(market_date, args)
    sectors = _validate_sectors(args)

    conn = sqlite3.connect(WORK_DIR / DB_NAME)
    if args.create_db:
        create_sqlite_table(conn, 'bwics_meta', BWIC_SCHEMA, indices=BWIC_INDICES)
        create_sqlite_table(conn, 'market_data', MARKET_DATA_SCHEMA, indices=MARKET_DATA_INDICES)

    logger.info('polling BWICS: %s, Runs: %s from %s between %s and %s',
                sectors.bwic, sectors.runs, market_date, start_time.time(), end_time.time())

    # poll for sector market data
    try:
        exec_count = 1
        poll_buffer = timedelta(minutes=2)  # prevents race conditions
        d0 = start_time
        quota = api.quota

        wait_secs = (start_time - (datetime.now(timezone.utc) - poll_buffer)).total_seconds()
        if wait_secs > 0:
            logger.info("waiting %.2f seconds until poll start", wait_secs)
            sleep(wait_secs)

        while (d1 := min(datetime.now(timezone.utc) - poll_buffer, end_time)) and d0 < end_time:
            logger.info("starting execution #%s, queries remaining: %s", exec_count, quota)
            if active_isins := _poll_active_isins(conn, api, sectors, market_date, d0, d1):
                if quota < len(active_isins):
                    logger.warning("running low on queries, now exiting")
                    break
                market_data, quota = _pull_market_data(api, active_isins, market_date)
                _store_market_data(conn, market_data)
                sleep_time = 60
            else:
                sleep_time = 120 # IF NO ACTIVE BONDS, WAIT TWO MINUTES BEFORE NEXT POLL

            if args.one_shot:
                logger.info("ran sector(s) %s once, now exiting main loop", sectors)
                break

            exec_count += 1
            d0 = d1

            logger.info("waiting %s seconds before next iteration", sleep_time)
            sleep(sleep_time)

        if not args.one_shot and d0 >= end_time:
            logger.info("designated stop time {:02d}:{:02d} UTC reached, now exiting".format(
                        end_time.hour, end_time.minute))

    except KeyboardInterrupt:
        logger.warning("user hit CTRL-C, now exiting")
    except Exception:  # pylint: disable=broad-except
        logger.exception("fatal error", exc_info=True)
    finally:
        logger.info("closing sqlite connection")
        conn.close()



if __name__ == "__main__":
    main()
