#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mydata_poll.py

Poll MyData in real-time and store locally

Full API Documentation: https://www.empirasign.com/v1/parser-api-docs/

Sample Calls:
    ./mydata_poll.py -C
    (poll all of today's MyData until EOD UTC, create new SQLite DB)

    ./mydata_poll.py -s12:00 -e21:00
    (poll MyData from 12:00 to 21:00 UTC, use existing DB)

    ./mydata_poll.py -d30
    (poll all of today's MyData, with 30 sec delays)
"""
import argparse
import sqlite3
import re
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from pathlib import Path

from empirasign import ParserClient
from empirasign.utils import get_logger, make_insertp, create_sqlite_table
from empirasign.parser.schemas import (CORP_SCHEMA, CDS_SCHEMA, MYDATA_SCHEMA, RUNS_SCHEMA,
                                       BWIC_AUCTION_SCHEMA, BWIC_BOND_SCHEMA)

# ------------ USER CONFIGURATION ------------

API_KEY = 'MY_API_KEY'
API_SECRET = 'MY_API_SECRET'
PROXY_SERVER = '' #e.g. proxy.mycompany.net:8080
# if you get a 407 Proxy Authentication Required error, you need to set
# PROXY_SERVER to something like username:password@proxy.mycompany.net:8080

WORK_DIR = Path()  # where the sqlite and log files will be saved
DB_NAME = 'mydata.sqlite'
LOG_NAME = 'mydata_poll.log'

# ------------ END USER CONFIGURATION ------------

logger = get_logger(WORK_DIR / LOG_NAME)

SCHEMAS = {
    'corp': MYDATA_SCHEMA + CORP_SCHEMA,
    'cds': MYDATA_SCHEMA + CDS_SCHEMA,
    # 'run': MYDATA_SCHEMA + RUNS_SCHEMA,
    # 'bwic': MYDATA_SCHEMA + tuple(set(BWIC_AUCTION_SCHEMA + BWIC_BOND_SCHEMA)) # remove shared flds
}

INDICES = {
#   tbl: {
#      idx_name: idx_column
#   }
    'corp': {
        'idx_isin': 'isin'
    }
}


def _insert_records(cursor, records, tbl_name, col_names):
    "insert quotes into SQLite tbl"
    q = make_insertp(tbl_name, col_names)
    for record in records:
        cursor.execute(q, tuple(record.get(k) for k in col_names))


def _handle_time_arg(time_string):
    "deserialize time string into UTC datetime object with current date"
    try:
        time_arg = datetime.strptime(time_string, r'%H:%M').time()
        current_date = datetime.now(timezone.utc).date()
        dt = datetime.combine(current_date, time_arg)
        dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError) as e:
        raise argparse.ArgumentTypeError('poll times must be in HH:MM format') from e
    return dt


def main():
    """
    the main event
    """
    parser = argparse.ArgumentParser()
    parser.register("type", "time", _handle_time_arg)
    parser.add_argument("-C", dest="create_db", action="store_true",
                        help="build sqlite database from scratch")
    parser.add_argument("-d", dest="delay", type=int, help="poll delay, in seconds")
    parser.add_argument("-s", dest="poll_start", type="time", default="00:00",
                        help="start time for polling MyData, in UTC (HH:MM)")
    parser.add_argument("-e", dest="poll_end", type="time", default="23:59",
                        help="end time for polling MyData, in UTC (HH:MM)")
    args = parser.parse_args()

    if args.poll_start >= args.poll_end:
        parser.error('poll_end must be greater than poll_start')
    logger.info('polling MyData from %s to %s (UTC)', args.poll_start, args.poll_end)

    conn = sqlite3.connect(WORK_DIR / DB_NAME)
    if args.create_db:
        for sector, schema in SCHEMAS.items():
            create_sqlite_table(conn, sector, schema, indices=INDICES.get(sector, {}))

    try:
        cursor = conn.cursor()
        d0 = args.poll_start

        api = ParserClient(API_KEY, API_SECRET, PROXY_SERVER)

        while (d1 := min(datetime.now(timezone.utc), args.poll_end)) and d0 < d1:
            d0_fmt, d1_fmt = d0.strftime('%Y-%m-%dT%H:%M:%S'), d1.strftime('%Y-%m-%dT%H:%M:%S')
            logger.info('polling for new MyData records within adjusted timeframe [%s, %s)',
                        d0_fmt, d1_fmt)

            data = api.get_mydata((d0, d1))['data']
            logger.info('pulled %s new records', len(data))

            data_by_sector = defaultdict(list)
            for record in data:
                api_path = record['path']
                sector = re.search(r'parse-([a-z]+)', api_path).group(1)
                data_by_sector[sector].append(record)

            for sector, sector_data in data_by_sector.items():
                if sector not in SCHEMAS:
                    continue
                sector_cols = [col_name for col_name, _ in SCHEMAS[sector]]
                _insert_records(cursor, sector_data, sector, sector_cols)
                logger.info('inserted %s %s records', len(sector_data), sector)
            conn.commit()

            if args.delay:
                next_poll = d1 + timedelta(seconds=args.delay)
                sleep_secs = max((next_poll - datetime.now(timezone.utc)).total_seconds(), 0)
                logger.info('waiting %s seconds until next poll', sleep_secs)
                time.sleep(sleep_secs)

            d0 = d1

        logger.info('polling window has completed, exiting...')

    except KeyboardInterrupt:
        logger.warning("user hit CTRL-C, now exiting")
    except Exception:  # pylint: disable=broad-except
        logger.exception("fatal error", exc_info=True)
    finally:
        logger.info("closing sqlite connection")
        conn.close()


if __name__ == '__main__':
    main()
