#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
intex_mktd.py

Leverage the /api/all-bonds/ and /api/bonds/ API endpoints to fill up the INTEX
market_data/market_color directory with fresh market data for selected sectors

Full API Documentation: https://www.empirasign.com/v1/market-api-docs/

API Usage Summary:
    HTTP METHOD     API ENDPOINT           QUOTA HIT                CLASS METHOD
    POST            /api/v1/bonds/         1 per bond               get_market_data
    GET             /api/v1/all-bonds/     None                     get_active_bonds

Sample Calls:
    ./intex_mktd.py --sectype "MBS 20yr" "MBS 30yr" (only bonds with MBS 20yr and MBS 30yr sectypes)
    ./intex_mktd.py --sectype2 CMBS                 (only bonds with CMBS sectype2)
"""

import argparse
import datetime
import sys
import tempfile
from pathlib import Path

from empirasign import MarketDataClient
from empirasign.utils import get_logger
from empirasign.intex_utils import write_intex_mktd
from empirasign.constants import SECTYPES, SECTYPES2

# ------------ USER CONFIGURATION ------------

API_KEY = 'YOUR_EMPIRASIGN_API_KEY'
API_SECRET = 'YOUR_EMPIRASIGN_API_SECRET'
PROXY_SERVER = ""  # e.g. proxy.mycompany.net:8080
# if you get a 407 Proxy Authentication Required error, you need to set
# PROXY_SERVER to something like username:password@proxy.mycompany.net:8080

INTEX_MKTD_DIR = Path('' or tempfile.gettempdir())
# The Default Location looks something like below
# C:\Users\WINDOWS_USERNAME\AppData\Roaming\intex\settings\market_data\market_color
# If your org has a shared location for Intex market_data, the path will be different

LOG_NAME = 'intex_mktd.log'

# ------------ END USER CONFIGURATION ------------

logger = get_logger(tempfile.gettempdir() + '/' + LOG_NAME)


def main():
    """
    the main event
    """
    parser = argparse.ArgumentParser(
        description='INTEXcalc Market Data',
        epilog=("When listing sectors with spaces, surround each sector with quotes, e.g.\n"
                "python intex_mktd.py --sectype 'ABS Auto'\n"
                "python intex_mktd.py --sectype 'ABS Auto' SN 'MBS 15yr'"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('sectors', nargs='+', help="list of securitytype or securitytype2 sectors")
    parser.add_argument("--sectype",
                        action='store_true',
                        dest="sectype",
                        help="filter sectors on OpenFIGI securitytype")
    parser.add_argument("--sectype2",
                        action='store_true',
                        dest="sectype2",
                        help="filter sectors on OpenFIGI securitytype2")
    args = parser.parse_args()

    if args.sectype:
        filter1 = set(args.sectors)
        filter2 = []
        invalid_sectors = filter1 - set(SECTYPES)
    elif args.sectype2:
        filter1 = []
        filter2 = set(args.sectors)
        invalid_sectors = filter2 - set(SECTYPES2)
    else:
        raise ValueError("must specify --sectype or --sectype2")
    if invalid_sectors:
        logger.error("Halting Execution: Invalid sector(s): %s", invalid_sectors)
        sys.exit(1)
    if not filter1 and not filter2:
        logger.error("Halting Execution: No sectors selected")
        sys.exit(1)
    logger.info("sector filters: sectype1: %s, sectype2: %s", filter1, filter2)

    api = MarketDataClient(API_KEY, API_SECRET, PROXY_SERVER)

    resp = api.get_active_bonds(datetime.date.today(), "Mtge")
    if resp["meta"]["results"] != "OK":
        logger.error("api call error: %s", resp)
        raise RuntimeError

    req_left = resp["meta"]['requests_left']
    logger.info("total result set: %s bonds, quota remaining: %s", len(resp["bonds"]), req_left)
    logger.info("sample list: %s", resp["bonds"][:10])
    if filter1:
        query_bonds = [x["isin"] for x in resp["bonds"] if x["figi_securitytype"] in filter1]
    else:
        query_bonds = [x["isin"] for x in resp["bonds"] if x["figi_securitytype2"] in filter2]

    # filter out any null results
    query_bonds = list({x for x in query_bonds if x})
    if len(query_bonds) > req_left:
        logger.warning("truncating bonds to query, %s requests left, but %s bonds to query",
                       req_left, len(query_bonds))
        query_bonds = query_bonds[:req_left]

    resp = api.get_market_data(query_bonds, nport=True)
    if resp["meta"]["errors"]:
        logger.error("api call error: %s", resp)
        raise RuntimeError

    write_intex_mktd(INTEX_MKTD_DIR, resp["data"])


if __name__ == "__main__":
    main()
