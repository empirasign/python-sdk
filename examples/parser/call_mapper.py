#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
call_mapper.py

Example script showing how to use the identifier mapper endpoint

Sample cURL:
    curl -X POST "https://api.empirasign.com/v1/id-mapper/" \
         -H "Content-Type: application/json" \
         -d '{"api_key": "API_KEY", "api_secret": "API_SECRET",
            "ids": [["id_bb", "BL4666196"], ["loanxid", "LX194827"], ["figi", "BBG01LMWNLF9"],
            ["cusip", "3128MMVE0"], ["isin", "US3138YKH632"], ["bbg_ticker", "FG A87733"]]}'
"""

import pprint

from empirasign import ParserClient

# ------------ USER CONFIGURATION ------------

API_KEY = "YOUR_EMPIRASIGN_API_KEY"        # provided by Empirasign
API_SECRET = "YOUR_EMPIRASIGN_API_SECRET"  # provided by Empirasign
PROXY_SERVER = ""  # e.g. proxy.mycompany.net:8080
# if you get a 407 Proxy Authentication Required error, you need to set
# PROXY_SERVER to something like username:password@proxy.mycompany.net:8080

# ------------ END USER CONFIGURATION ------------

ids = [
    ["bbg_ticker", "FG A87733"],
    ["cusip", "3128MMVE0"],
    ["isin", "US3138YKH632"],
    ["figi", "BBG01LMWNLF9"],
    ["id_bb", "BL4666196"],
    ["loanxid", "LX194827"],
]

api = ParserClient(API_KEY, API_SECRET, PROXY_SERVER)
res = api.get_id_mapping(ids)
pprint.pprint(res)
