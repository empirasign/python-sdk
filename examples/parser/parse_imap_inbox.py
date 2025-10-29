#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_imap_inbox.py

Example script to parse runs in IMAP Inbox
- save parse results to local JSON files
- maintain state using IMAP folders
- compatible with Windows and Linux
- not very efficient with IMAP network traffic (no chunking of requests)

Full API Documentation: https://www.empirasign.com/v1/parser-api-docs/
"""

import datetime
import email
import imaplib
import json
import tempfile
import time
from urllib.parse import quote
from pathlib import Path

from empirasign import ParserClient
from empirasign.utils import get_logger, safe_create_folder

# ------------ USER CONFIGURATION ------------

API_KEY = "YOUR_EMPIRASIGN_API_KEY"        # provided by Empirasign
API_SECRET = "YOUR_EMPIRASIGN_API_SECRET"  # provided by Empirasign
PROXY_SERVER = ""  # e.g. proxy.mycompany.net:8080
# if you get a 407 Proxy Authentication Required error, you need to set
# PROXY_SERVER to something like username:password@proxy.mycompany.net:8080

IMAP_HOST = "imap.gmail.com"  # or whomever your email backend provider is
EMAIL_USER = "runs@hedgefundalpha.com"
EMAIL_PASS = "HARD_TO_GUESS_STRING"

# this script maintains state via folder usage
# once an email is moved into COMPLETED_FOLDER, no further parsing attempts
# will be made
SOURCE_FOLDER = "INBOX"
COMPLETED_FOLDER = "PARSED"

RESULTS_DIR = Path(tempfile.gettempdir())

LOG_DIR = Path(tempfile.gettempdir())
LOG_FILE = 'parse_imap_inbox.log'

# ------------ END USER CONFIGURATION ------------

logger = get_logger(LOG_DIR / LOG_FILE)


def get_imap_uids(imap, d0, d1=None, max_size=2500000):
    """
    return list of IMAP uids for a date or date range, label and max_size
    https://automatetheboringstuff.com/2e/chapter18/
    https://www.atmail.com/blog/imap-commands/
    https://gist.github.com/martinrusev/6121028
    """
    if not d1:
        d1 = datetime.date.today() + datetime.timedelta(1)
    if d1 < d0:
        d0, d1 = d1, d0
    d1 += datetime.timedelta(1)  # this makes the search inlusive?
    date_str = 'SENTSINCE "{}" SENTBEFORE "{}"'.format(d0.strftime("%d-%b-%Y"),
                                                       d1.strftime("%d-%b-%Y"))
    if max_size:
        size_str = "SMALLER {}".format(int(max_size))
    else:
        size_str = ""
    search_items = [x for x in [size_str, date_str] if x]
    search_str = "(" + " ".join(search_items) + ")"
    logger.info("IMAP search string: %s", search_str)
    status, data = imap.uid('search', None, search_str)
    if status == "OK":
        return sorted([x.decode("ascii") for x in data[0].split()])
    return []


def main():
    """
    the main event
    """

    t0 = time.time()
    logger.info("parse_imap_inbox.py starting")

    imap = imaplib.IMAP4_SSL(IMAP_HOST, 993)
    try:
        imap.login(EMAIL_USER, EMAIL_PASS)
    except Exception:
        # if you get the following error
        # error: b'[AUTHENTICATIONFAILED] Invalid credentials (Failure)'
        # for Gmail / Google Workspace must enable "Less Secure app access" at the following URL
        # https://myaccount.google.com/u/3/security?gar=1
        # other services may have other settings to enable
        # For example, Fastmail calls them App passwords
        # https://www.fastmail.help/hc/en-us/articles/360058752854-App-passwords
        logger.exception("try enabling 'Less Secure app access' at https://myaccount.google.com/u/3/security?gar=1")  # pylint: disable=line-too-long
        raise

    status, num_raw = imap.select(SOURCE_FOLDER, readonly=False)  # pylint: disable=unused-variable
    logger.info("target folder: %s, total messages (no filter): %s", SOURCE_FOLDER, num_raw)
    target_lst = get_imap_uids(imap, datetime.date.today())
    logger.info("%s emails to parse in target folder: %s", len(target_lst), SOURCE_FOLDER)

    api = ParserClient(API_KEY, API_SECRET, PROXY_SERVER)

    if target_lst:
        safe_create_folder(imap, COMPLETED_FOLDER)
    done_lst = []
    quota = True
    for imap_uid in target_lst:
        typ, data = imap.uid('fetch', imap_uid, '(RFC822)')
        if typ == "OK":
            # we can send email to parser
            rfc_bytes = data[0][1]
            res = api.parse_eml('corp', rfc_bytes, 3.5)

            if res['meta']['results'] == 'OK':
                done_lst.append(imap_uid)
                # compute a filename that's safe on Windows and Linux
                # https://docs.microsoft.com/en-us/windows/win32/fileio/naming-a-file
                message_id = email.message_from_bytes(rfc_bytes)["Message-ID"]
                fname = quote(message_id, safe="") + ".json"
                # reversible via unquote(fname)[:-5]
                logger.info("saving parsed results, imap_uid: %s, Message-ID: %s filename: %s",
                            imap_uid, message_id, fname)

                # check remaining quota
                if res["meta"]["api_req_left"] < 1:
                    quota = False
            else:
                fname = imap_uid + "-error.json"
                logger.warning("error occurred: %s",  res['meta']['errors'])
                logger.warning("saving error file, imap_uid: %s, filename: %s", imap_uid, fname)

            with open(RESULTS_DIR / fname, "wt") as fp:
                fp.write(json.dumps(res, sort_keys=True, indent=2, ensure_ascii=False))

            if not quota:
                logger.warning("early exit of loop, daily quota exhausted, processed %s / %s",
                               len(done_lst), len(target_lst))
                break

    if done_lst:
        imap.uid('MOVE', ",".join(done_lst), COMPLETED_FOLDER)  # move completed messages
    imap.logout()
    logger.info("finished, total run time secs: {:,}".format(round(time.time() - t0)))


if __name__ == "__main__":
    main()
