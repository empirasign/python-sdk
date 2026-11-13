#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new_issue_poll.py

This script makes optimal use of the Empirasign API to monitor & store New Issue events in real-time.

While designed to demonstrate a real-time polling approach by default, this script offers
optional arguments for performing simple one-time data pulls as well.

Full API Documentation: https://www.empirasign.com/v1/market-api-docs/

API Usage Summary:
    HTTP METHOD     API ENDPOINT           QUOTA HIT                CLASS METHOD
    GET             /api/v1/new-issue/         None                get_new_issues

The /new-issue/ endpoint is an RSS-style event feed, returning the N most recently updated events
by default

However, multiple methods of pre-filtering are available to end users for more efficient bandwith
usage:

    - OpenFIGI securitytypes
    - Deal Ticker wildcard match
    - Since timestamp


Sample Calls:

    real-time polling:

        ./new_issue_poll.py -C
        ./new_issue_poll.py -C -s"ABS Card,ABS Auto"

    one-time data pull:

        ./new_issue_poll.py -C -l50 -s"ABS Card,ABS Auto"
        ./new_issue_poll.py -C -t"10:15"
        ./new_issue_poll.py -C -t"2026-08-06T10:15:00"
"""

import sys
import sqlite3
import argparse
import json
from time import sleep
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

from empirasign import MarketDataClient
from empirasign.market.schemas import NEWISSUE_DEAL_SCHEMA, NEWISSUE_CLASS_SCHEMA
from empirasign.utils import get_logger, upsert, create_sqlite_table
from empirasign.constants import SECTYPES

# ------------ USER CONFIGURATION ------------

API_KEY = 'YOUR_EMPIRASIGN_API_KEY'
API_SECRET = 'YOUR_EMPIRASIGN_API_SECRET'
PROXY_SERVER = ""  #e.g. proxy.mycompany.net:8080
# if you get a 407 Proxy Authentication Required error, you need to set
# PROXY_SERVER to something like username:password@proxy.mycompany.net:8080

WORK_DIR = Path()  # where the sqlite and log files will be saved
DB_NAME = "new_issue_poll.sqlite"  # name of sqlite database file (all tables live here)
LOG_NAME = "new_issue_poll.log"

# recommended polling hours are between 7:00am and 7:00pm ET
DEFAULT_END_UTC = "23:00"

# ------------ END USER CONFIGURATION ------------

logger = get_logger(WORK_DIR / LOG_NAME)

NEWISSUE_DEAL_FLDS = [fld for fld, _ in NEWISSUE_DEAL_SCHEMA]
NEWISSUE_DEAL_INDICES = {
    'idx_deal_event_id': 'event_id',
    'idx_modified_at': 'modified_at'
}
NEWISSUE_CLASS_FLDS = [fld for fld, _ in NEWISSUE_CLASS_SCHEMA]
NEWISSUE_CLASS_INDICES = {
    'idx_class_event_id': 'event_id',
    'idx_class': 'class'
}

# ------------ Argument Handlers ------------

def _validate_securitytypes(securitytypes):
    """
    check that user-entered sectors are valid
    """
    if securitytypes:
        securitytypes = [x.strip() for x in securitytypes.split(',')]
    else:
        securitytypes = []
    if invalid_sectors := set(securitytypes) - set(SECTYPES):
        logger.error("Halting Execution: Invalid BWIC sector(s): %s", invalid_sectors)
        sys.exit(1)
    return securitytypes


def _handle_time_arg(ts_str):
    """
    convert time-based arguments from accepted string patterns to datetimes
    """
    short_timestamp = '%H:%M'
    iso_timestamp = '%Y-%m-%dT%H:%M:%S'
    try:
        ts = datetime.strptime(ts_str, short_timestamp).time()
        ts = datetime.combine(datetime.now(timezone.utc).date(), ts, tzinfo=timezone.utc)
    except ValueError:
        try:
            ts = datetime.strptime(ts_str, iso_timestamp)
        except ValueError:
            logger.error("Time arguments must be [%s, %s]", iso_timestamp, short_timestamp)
            return None
    return ts

# ------------ Helpers ------------

def _get_new_issue_events(api, securitytypes, since, limit):
    """
    poll Empirasign for new issue events, organize resulting records for local storage
    """
    resp = api.get_new_issues(since=since,
                              securitytype=securitytypes,
                              limit=limit)
    if resp["meta"]["results"] != "OK":
        logger.error("FAILURE! polling for new issue events, errors: %s", resp["meta"]["errors"])
        return [], [], []

    logger.info("%s events across %s since %s", len(resp["data"]), securitytypes, since)
    deal_recs, class_recs, delete_ids = [], [], []
    for record in resp["data"]:
        event_id = record["event_id"]
        if record["action"] == "delete":
            delete_ids.append(event_id)
            continue
        deal_recs.append({k: v for k, v in record.items() if k != "classes"})
        for class_rec in record["classes"]:
            class_rec["event_id"] = event_id
            class_recs.append(class_rec)

    return deal_recs, class_recs, delete_ids


def _delete_events(conn, event_ids):
    """
    delete deal and class-level records associated with provided event_id
    """
    cursor = conn.cursor()
    delete_logs = defaultdict(int)

    for event_id in event_ids:
        cursor.execute("DELETE FROM new_issue_deals WHERE event_id = ?", (event_id,))
        delete_logs['deal'] += cursor.rowcount
        cursor.execute("DELETE FROM new_issue_classes WHERE event_id = ?", (event_id,))
        delete_logs['class'] += cursor.rowcount

    logger.info('deleted: %s deals, %s classes', delete_logs['deal'], delete_logs['class'])

    if sum(delete_logs.values()):
        conn.commit()


def _store_events(conn, deals, classes):
    """
    insert or update deal and class-level records based on unique event_id
    """
    deal_pks = ('event_id',)
    class_pks = ('event_id', 'class')
    insert_logs, update_logs = defaultdict(int), defaultdict(int)

    for record in deals:
        record = {key: value for key, value in record.items() if key in NEWISSUE_DEAL_FLDS}
        res = upsert(conn, 'new_issue_deals', deal_pks, record, ph="?")
        if res == 'INSERT':
            insert_logs['deal'] += 1
        elif res == 'UPDATE':
            update_logs['deal'] += 1

    for record in classes:
        record['rtg'] = json.dumps(record.get('rtg') or {})
        record = {key: value for key, value in record.items() if key in NEWISSUE_CLASS_FLDS}
        res = upsert(conn, 'new_issue_classes', class_pks, record, ph="?")
        if res == 'INSERT':
            insert_logs['class'] += 1
        elif res == 'UPDATE':
            update_logs['class'] += 1

    # log updates to our market data table
    logger.info('inserted: %s deals, %s classes', insert_logs['deal'], insert_logs['class'])
    logger.info('updated: %s deals, %s classes', update_logs['deal'], update_logs['class'])

    if sum(insert_logs.values()) or sum(update_logs.values()):
        conn.commit()


def _poll_new_issues(conn, api, securitytypes, since=None, limit=None):
    """
    poll for and store results
    """
    deal_recs, class_recs, delete_ids = _get_new_issue_events(api, securitytypes, since, limit)
    if deal_recs or delete_ids:
        if deal_recs:
            _store_events(conn, deal_recs, class_recs)
        if delete_ids:
            _delete_events(conn, delete_ids)
        sleep_time = 60
    else:
        sleep_time = 120  # if no activity, wait a bit longer
    return sleep_time


def main():
    """
    the main event
    """
    parser = argparse.ArgumentParser()
    # general arguments
    parser.add_argument("-s", "--sectypes", dest="sectypes", metavar="ABS Home,ABS Other",
                        help=("filter results by comma-separated OpenFIGI securitytype(s). "
                              f"Available securitypes: {SECTYPES}"))
    parser.add_argument("-C", "--create-table", dest="create_db", action="store_true",
                        help="creates/overwrites new SQLite tables for demo backend")
    parser.add_argument("-v", action="store_true", dest="verbose", help="log all debugging info")
    # one-shot arguments
    parser.add_argument("-l", "--limit", dest="limit", type=int, metavar="100",
                        help="optional limit on number of results, defaults to API default")
    parser.add_argument("-t", "--since", dest="since", type=str, metavar="06:00",
                        help="filter by modified_at timestamp (HH:MM or YYYY-MM-DD:HH:MM:SS) in UTC")
    args = parser.parse_args()

    # configure client
    api = MarketDataClient(API_KEY, API_SECRET, PROXY_SERVER)
    api.verbose = bool(args.verbose)

    # handle script arguments
    securitytypes = _validate_securitytypes(args.sectypes)
    if args.since:
        args.since = _handle_time_arg(args.since)

    conn = sqlite3.connect(WORK_DIR / DB_NAME)
    if args.create_db:
        create_sqlite_table(conn, 'new_issue_deals', NEWISSUE_DEAL_SCHEMA,
                            indices=NEWISSUE_DEAL_INDICES)
        create_sqlite_table(conn, 'new_issue_classes', NEWISSUE_CLASS_SCHEMA,
                            indices=NEWISSUE_CLASS_INDICES)

    logger.info('polling for recent New Issue events: %s', args._get_kwargs())

    try:
        exec_count = 1
        since_time = datetime.now(timezone.utc)
        end_time = _handle_time_arg(DEFAULT_END_UTC)

        # run a "catch-up" poll for potential overnight updates
        sleep_time = _poll_new_issues(conn, api, securitytypes, since=args.since, limit=args.limit)

        # using either of these arguments indicates a single poll use-case
        if args.limit or args.since:
            return

        sleep(sleep_time)
        while since_time <= end_time:  # begin polling
            logger.info("starting execution #%s", exec_count)
            new_since = datetime.now(timezone.utc)
            sleep_time = _poll_new_issues(conn, api, securitytypes, since=since_time)

            exec_count += 1
            since_time = min(new_since, end_time)

            logger.info("waiting %s seconds before next iteration", sleep_time)
            sleep(sleep_time)

        if since_time >= end_time:
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
