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
import json
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from empirasign import MarketDataClient
from empirasign.utils import get_logger
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


def _comp_px(handle, ticks):
    """
    helper function for price32_to_dec
    """
    tot_px = 0
    if ticks[-1] == "+":
        tot_px += .5 / 32.0
        ticks = ticks[:-1]
    if len(ticks) == 3:
        tot_px += float(ticks[-1]) / 8.0 / 32.0
        tot_px += float(ticks[:2]) / 32.0
    else:
        tot_px += float(ticks) / 32.0
    tot_px += float(handle)
    return tot_px


def price32_to_dec(price32):
    """
    convert a well-formed price32 or price with handle suffix to a
    decimal price
    """
    if not price32:
        return None
    if isinstance(price32, (int, float)):
        return float(price32)

    m = re.search(r"( *\$ *)(.+)", price32)
    if m:
        price32 = m.group(2)

    try:
        price32 = float(price32)
        return price32
    except Exception:  # pylint: disable=broad-except
        pass
    m = re.search(r'^(\d+)-?h$', price32, re.I)
    if m:
        return int(m.group(1)) + 0.25

    m = re.search(r'^(\d+)-$', price32, re.I)
    if m:
        return float(m.group(1))

    # negative price32 - specs
    m = re.search(r'^\-\d', price32, re.I)
    if m:
        parts = price32.strip().split("-")[-2:]
        if len(parts) == 2 and "" not in parts:
            try:
                return _comp_px(*parts) * -1
            except ValueError:
                pass
        return None

    price32 = price32.lower().replace("a", "")
    parts = price32.strip().split("-")
    if len(parts) == 2:
        try:
            return _comp_px(*parts)
        except ValueError:
            pass
    return None


def _to_intex(item):
    """
    take market data item from /api/bonds/ end point and covert to format
    suitable for .mktd files for INTEXcalc
    keys: Tranche ID, As Of, Quote, Quote Type, Color, Provider
    """
    required_fields = ["Tranche ID", "As Of", "Color", "Quote", "Quote Type"]
    idata = {"Tranche ID": item["isin"]}
    # handle nport data
    if item['kind'] == 'nport':
        idata["As Of"] = item["repPdDate"] + "T08:00:00-05:00"
        idata["Color"] = "N-PORT"
        idata["Provider"] = "EDGAR"
        balance_usd = item['balance'] / item['balanceExchangeRt']
        idata["Size"] = round(balance_usd, 3)
        try:
            idata["Quote"] = round(100 * item['valUSD'] / balance_usd, 3)
        except ZeroDivisionError:
            idata["Quote"] = None
        idata["Quote Type"] = "Price"
        idata["Fund-Name"] = item.get("seriesName")
        idata["Fund-Company"] = item.get("regName")
        return idata

    if item["kind"] in ("bwic", "pxtalk"):
        idata["As Of"] = item["trade_datetime_utc"][:-1] + "-00:00"
    else:
        if isinstance(item["trade_dt"], datetime.date):
            item["trade_dt"] = item["trade_dt"].strftime("%Y-%m-%d")
        idata["As Of"] = item["trade_dt"] + "T08:00:00-05:00"  # assume 8AM EST

    if item["kind"] == "bwic":
        idata["Provider"] = item["list_id"]
    else:
        idata["Provider"] = item.get("dealer", "unk")

    # handle price or spread data
    if item["kind"] in ("bwic", "pxtalk"):
        idata["Size"] = round(item["of"] * 1e6)
        if item.get("price") is not None:
            idata["Quote"] = item["price"]
            idata["Quote Type"] = "Price"
        elif item.get("price32") is not None:
            idata["Quote"] = price32_to_dec(item["price32"])
            idata["Quote Type"] = "Price"
        elif item.get("spread_dec") is not None:
            idata["Quote"] = item["spread_dec"]
            idata["curve"] = item.get("curve")
            idata["Quote Type"] = "Spread"
        elif item.get("spread") is not None:
            idata["Quote"] = item["spread"]
            idata["curve"] = item.get("curve")
            idata["Quote Type"] = "Spread"
        if item["kind"] == "pxtalk":
            idata["Color"] = "PX Talk"
        elif item["kind"] == 'bwic' and item['color']:
            idata["Color"] = item['color']
    elif item["kind"] == "offer":
        idata["Size"] = round(item["of_offer"] * 1e6)
        if item.get("price_offer") is not None:
            idata["Quote"] = item["price_offer"]
            idata["Quote Type"] = "Price"
        elif item.get("price32_offer") is not None:
            idata["Quote"] = price32_to_dec(item["price32_offer"])
            idata["Quote Type"] = "Price"
        elif item.get("spread_offer") is not None:
            idata["Quote"] = item["spread_offer"]
            idata["Quote Type"] = "Spread"
            idata["curve"] = item.get("curve")
        idata["Color"] = "Offer"
    elif item["kind"] == "bid":
        idata["Size"] = round(item["of_bid"] * 1e6)
        if item.get("price_bid") is not None:
            idata["Quote"] = item["price_bid"]
            idata["Quote Type"] = "Price"
        elif item.get("price32_bid") is not None:
            idata["Quote"] = price32_to_dec(item["price32_bid"])
            idata["Quote Type"] = "Price"
        elif item.get("spread_bid") is not None:
            idata["Quote"] = item["spread_bid"]
            idata["Quote Type"] = "Spread"
            idata["curve"] = item.get("curve")
        idata["Color"] = "Bid"
    else:
        # market is not yet implemented
        return {}
    if all(key in idata for key in required_fields):
        return idata
    return {}


def split_mkts(item):
    """
    split 2 way mkts into bid and offer quotes
    """
    bid_keys = ['of_bid', 'cf_bid', 'price_bid', 'price32_bid', 'spread_bid']
    offer_keys = ['of_offer', 'cf_offer', 'price_offer', 'price32_offer', 'spread_offer']
    if any(x for x in bid_keys if x in item) and any(x for x in offer_keys if x in item):
        bid = {x: item[x] for x in item if x not in offer_keys}
        offer = {x: item[x] for x in item if x not in bid_keys}
        return offer, bid
    return item, None


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

    # loop over the the results
    quotes = defaultdict(list)
    for quote in resp["data"]:
        quotes[quote["isin"]].append(quote)
    for isin in quotes:
        export_quotes = []
        for quote in quotes[isin]:
            # convert to intex mktd format
            quote, quote2 = split_mkts(quote)
            cur_quote = _to_intex(quote)
            if cur_quote:
                export_quotes.append(cur_quote)
            if quote2:
                cur_quote2 = _to_intex(quote2)
                if cur_quote2:
                    export_quotes.append(cur_quote2)
        if export_quotes:
            data_path = INTEX_MKTD_DIR / f"{isin}.mktd"
            with open(data_path, "wb") as fp:
                fp.write(
                    json.dumps(export_quotes, ensure_ascii=False, indent=2).encode("utf-8"))
                logger.info("saved bond data for: %s, num_quotes: %s path: %s", isin,
                            len(export_quotes), data_path)


if __name__ == "__main__":
    main()
