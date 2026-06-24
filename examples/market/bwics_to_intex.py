#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bwics_to_intex.py

Poll Empirasign API for BWIC information in selected sector(s)
Export data to folder INTEXCalc watches for BWIC information in BWIC/JSON format
rinse/repeat

Full API Documentation: https://www.empirasign.com/market-api-docs/

API Usage Summary:
    HTTP METHOD     API ENDPOINT           QUOTA HIT                CLASS METHOD
    GET             /api/v1/bwics/         None                     get_bwics

Sample Calls:
    ./bwics_to_intex.py cmbs
    ./bwics_to_intex.py agcmo naresi
    ./bwics_to_intex.py ALL                 (do all sectors in BWIC_SECTORS_MAJOR)
    ./bwics_to_intex.py agcmo --one-shot    (poll agcmo sector once, then exit)
"""

import argparse
import datetime
import sys
import tempfile
import time
from pathlib import Path

from empirasign import MarketDataClient
from empirasign.utils import get_logger
from empirasign.constants import BWIC_SECTORS
from empirasign.intex_utils import write_intex_bwic

# ------------ USER CONFIGURATION ------------

API_KEY = 'YOUR_EMPIRASIGN_API_KEY'
API_SECRET = 'YOUR_EMPIRASIGN_API_SECRET'
PROXY_SERVER = ""  # e.g. proxy.mycompany.net:8080
# if you get a 407 Proxy Authentication Required error, you need to set
# PROXY_SERVER to something like username:password@proxy.mycompany.net:8080

LOG_DIR = Path('' or tempfile.gettempdir())
INTEX_BWIC_DIR = Path('' or tempfile.gettempdir())
# often looks like this:
# C:\Users\WINDOWS_USERNAME\AppData\Roaming\intex\settings\market_data\bwic
# If your org has a shared location for Intex market_data, the path will be different

LOG_NAME = 'bwics_to_intex.log'

# stop polling for new market data 21:30 UTC, or 5:30 EST
# this parameter needs to be adjusted when daylight savings time switches
STOP_HOUR = 21
STOP_MINUTE = 30

# ------------ END USER CONFIGURATION ------------

logger = get_logger(LOG_DIR / LOG_NAME)


def utc_minutes():
    """
    helper function for loop control, returns minutes after midnight UTC
    """
    cur_time = datetime.datetime.now(datetime.timezone.utc)
    return cur_time.hour * 60 + cur_time.minute


def main():
    """
    the main event
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('sectors', nargs='+')
    parser.add_argument("--one-shot",
                        action='store_true',
                        dest="one_shot",
                        help="run once, no looping")
    args = parser.parse_args()

    cur_dt = datetime.date.today()
    fwd_dt = cur_dt + datetime.timedelta(days=7)
    sectors = args.sectors
    if "ALL" in args.sectors:
        sectors = ('mtge',)

    if not sectors:
        logger.error(
            "Halting Execution: You must select one or more of the following valid sectors: %s",
            BWIC_SECTORS)
        sys.exit(1)

    invalid_sectors = set(sectors) - set(BWIC_SECTORS)
    if invalid_sectors:
        logger.error("Halting Execution: Invalid sector(s): %s", invalid_sectors)
        sys.exit(1)

    api = MarketDataClient(API_KEY, API_SECRET, PROXY_SERVER)

    try:
        run_number = 1
        cur_time = utc_minutes()
        while args.one_shot or cur_time < (STOP_HOUR * 60 + STOP_MINUTE):
            logger.info("starting run: %s", run_number)

            for sector in sectors:
                resp = api.get_bwics(sector, (cur_dt, fwd_dt))
                if resp["meta"]["results"] != "OK":
                    logger.error("api call error: %s", resp)
                    raise RuntimeError
                logger.info("sector: %s num_results: %s, API meta data: %s", sector,
                            len(resp["data"]), resp["meta"])
                for bwic in resp["data"]:
                    write_intex_bwic(INTEX_BWIC_DIR, bwic)
            if args.one_shot:
                logger.info("ran sector(s) %s once, now exiting main loop", sectors)
                break
            logger.info("waiting 60 seconds before next iteration")
            time.sleep(60)  # DO NOT POLL SERVER MORE THAN ONCE PER MINUTE
            cur_time = utc_minutes()
        if not args.one_shot:
            logger.info("it's after designated stop time {:02d}:{:02d} UTC, now exiting".format(
                STOP_HOUR, STOP_MINUTE))
    except KeyboardInterrupt:
        logger.warning("user hit CTRL-C, now exiting")
    except Exception:  # pylint: disable=broad-except
        logger.exception("fatal error", exc_info=True)


if __name__ == "__main__":
    main()
