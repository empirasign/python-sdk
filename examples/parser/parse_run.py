#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_run.py

Example script showing how to parse a runs message embedded in an
email via the Empirasign Parser API endpoint.
Supported Sectors: Structured Products, Corporates, and Loans

Full API Documentation: https://www.empirasign.com/v1/parser-api-docs/

Sample Calls:
    ./parse_run.py dealer_run_abs.eml      (eml/rfc822 formated run)
    ./parse_run.py dealer_run_cmbs.msg     (MS Outlook formated run)

Notes on email file formats
https://www.msoutlookware.com/difference/msg-vs-eml.html
https://www.w3.org/Protocols/rfc822/
https://blogs.msdn.microsoft.com/openspecification/2009/11/06/msg-file-format-part-1/
"""

import argparse
import json
import pprint
from pathlib import Path

from empirasign import ParserClient
from empirasign.utils import get_logger

# ------------ USER CONFIGURATION ------------

API_KEY = "YOUR_EMPIRASIGN_API_KEY"        # provided by Empirasign
API_SECRET = "YOUR_EMPIRASIGN_API_SECRET"  # provided by Empirasign
PROXY_SERVER = ""  # e.g. proxy.mycompany.net:8080
# if you get a 407 Proxy Authentication Required error, you need to set
# PROXY_SERVER to something like username:password@proxy.mycompany.net:8080

LOG_DIR = Path()
LOG_NAME = "parse_run.log"
# ------------ END USER CONFIGURATION ------------

def main():
    """
    the main event
    """
    parser = argparse.ArgumentParser(description='parse email runs message in eml or msg format')
    parser.add_argument(dest="infile", help="input msg/eml filename")
    parser.add_argument('-s',
                        dest="sector",
                        choices=["run", "corp", "loan"],
                        default="run",
                        help="sector parser endpoint to hit, default is structured products")
    parser.add_argument('-o', dest="outfile", help="output filename [not required]")
    args = parser.parse_args()

    logger = get_logger(LOG_DIR / LOG_NAME)

    infile = args.infile
    if not args.outfile:
        outfile = infile.rsplit(".", 1)[0] + ".json"
    elif not args.outfile.endswith(".json"):
        outfile = args.outfile + ".json"
    else:
        outfile = args.outfile

    api = ParserClient(API_KEY, API_SECRET, PROXY_SERVER)

    res = api.parse_email_file(args.sector, infile, 3.5)
    logger.info(pprint.pformat(res))

    if res['meta']['results'] == 'OK':
        with open(outfile, "w") as f:
            f.write(json.dumps(res, sort_keys=True, indent=2, ensure_ascii=False))
        logger.info("results file saved: %s", outfile)
    else:
        logger.info("error occurred: %s", res['meta']['errors'])


if __name__ == "__main__":
    main()
