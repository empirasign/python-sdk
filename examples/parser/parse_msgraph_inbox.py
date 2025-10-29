#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_msgraph_inbox.py

Example script to parse runs in Outlook Inbox via Microsoft Graph API
- saves to local JSON files
- maintains state using IMAP folders
- compatible with Windows and Linux

Full API Documentation: https://www.empirasign.com/v1/parser-api-docs/

TRY USING IMAP FIRST!
If your Microsoft Exchange Server has IMAP support enabled, or you can enable
IMAP support, we recommend using the parse_imap_inbox.py script

Link to IMAP Settings for MS Exchange Server
https://docs.microsoft.com/en-us/exchange/clients/pop3-and-imap4/configure-imap4?view=exchserver-2019


Microsoft Graph API Links

Quick Start
https://developer.microsoft.com/en-us/graph/quick-start

Authentication
https://docs.microsoft.com/en-us/graph/security-authorization

Basic REST Method Call
https://docs.microsoft.com/en-us/graph/use-the-api#call-a-rest-api-method

Get Email Message Contents Call (returns RFC formatted string)
https://docs.microsoft.com/en-us/graph/outlook-get-mime-message
"""

import datetime
import email
import json
import tempfile
import time
from urllib.parse import quote
from pathlib import Path

import requests

from empirasign import ParserClient
from empirasign.utils import get_logger

# ------------ USER CONFIGURATION ------------

API_KEY = "YOUR_EMPIRASIGN_API_KEY"        # provided by Empirasign
API_SECRET = "YOUR_EMPIRASIGN_API_SECRET"  # provided by Empirasign
PROXY_SERVER = ""  # e.g. proxy.mycompany.net:8080
# if you get a 407 Proxy Authentication Required error, you need to set
# PROXY_SERVER to something like username:password@proxy.mycompany.net:8080

ACCESS_TOKEN = ""  # configured from Azure Active Directory

# this script maintains state via folder usage
# once this email is moved into COMPLETED_FOLDER, no further parsing attempts
# will be made
SOURCE_FOLDER = "INBOX"
COMPLETED_FOLDER = "PARSED"

RESULTS_DIR = Path(tempfile.gettempdir())

LOG_DIR = Path(tempfile.gettempdir())
LOG_NAME = "parse_msgraph_inbox.log"

# ------------ END USER CONFIGURATION ------------

logger = get_logger(LOG_DIR / LOG_NAME)


def get_ids(d0, d1=None):
    """
    return list of msg id's for a date or date range
    """
    if not d1:
        d1 = datetime.date.today() + datetime.timedelta(1)
    if d1 < d0:
        d0, d1 = d1, d0
    search_str = '/me/messages?$filter=(receivedDateTime ge {}) and (receivedDateTime le {})'.format(
        d0.strftime("%Y-%m-%dT00:00:00Z"), d1.strftime("%Y-%m-%dT00:00:00Z"))

    url = "https://graph.microsoft.com/v1.0" + search_str
    logger.info("API url: %s", url)
    resp = requests.get(url, headers={'Authorization': 'Bearer ' + ACCESS_TOKEN})
    ids = [x['id'] for x in resp.json()['value']]
    return ids


def _safe_create_folder(folder_name):
    """
    create folder_name if it does not already exist
    return the folder id for later storage
    """
    url = 'https://graph.microsoft.com/v1.0/me/mailFolders/'
    headers = {'Authorization': 'Bearer ' + ACCESS_TOKEN}
    resp = requests.get(url, headers=headers)
    folder = [x for x in resp.json()['value'] if x['displayName'] == folder_name]

    if not folder:
        data = {'displayName': folder_name}
        resp = requests.post(url, json=data, headers=headers)
        logger.info("created COMPLETED_FOLDER: %s", folder_name)
        return resp.json()['id']

    logger.info("folder %s already exists", folder_name)
    return folder[0]['id']


def move_msg(folder_id, uid):
    """
    move completed emails to the completed folder
    """
    url = "https://graph.microsoft.com/v1.0/me/messages/{}/move"
    headers = {'Authorization': 'Bearer ' + ACCESS_TOKEN}
    data = {'destinationId': folder_id}
    requests.post(url.format(uid), json=data, headers=headers)


def main():
    """
    the main event
    """
    t0 = time.time()
    logger.info("parse_msgraph_inbox.py starting")

    target_lst = get_ids(datetime.date.today())
    logger.info("%s emails to parse in target folder: %s", len(target_lst), SOURCE_FOLDER)

    if target_lst:
        folder_id = _safe_create_folder(COMPLETED_FOLDER)
    done_lst = []
    request_url = "https://graph.microsoft.com/v1.0/me/messages/{}/$value"

    api = ParserClient(API_KEY, API_SECRET, PROXY_SERVER)
    quota = True
    for uid in target_lst:
        data = requests.get(request_url.format(uid),
                            headers={'Authorization': 'Bearer ' + ACCESS_TOKEN})
        res = api.parse_eml('corp', data.text, 3.5)

        if res['meta']['results'] == 'OK':
            done_lst.append(uid)
            # compute a filename that's safe on Windows and Linux
            # https://docs.microsoft.com/en-us/windows/win32/fileio/naming-a-file
            message_id = email.message_from_string(data.text)["Message-ID"]
            fname = quote(message_id, safe="") + ".json"
            # reversible via unquote(fname)[:-5]

            logger.info("saving parsed results, uid: %s, Message-ID: %s filename: %s", uid,
                        message_id, fname)
            # check remaininq quota
            if res["meta"]["api_req_left"] < 1:
                quota = False
        else:
            fname = uid + "-error.json"
            logger.warning("error occurred: %s", res['meta']['errors'])
            logger.warning("saving error file, uid: %s, filename: %s", uid, fname)

        with open(RESULTS_DIR / fname, "wt") as fp:
            fp.write(json.dumps(res, sort_keys=True, indent=2, ensure_ascii=False))

        if not quota:
            logger.warning("early exit of loop, daily quota exhausted, processed %s / %s",
                           len(done_lst), len(target_lst))
            break

    for uid in done_lst:
        move_msg(folder_id, uid)
    logger.info("moved %s emails to folder: %s", len(done_lst), COMPLETED_FOLDER)
    logger.info("finished, total run time secs: {:,}".format(round(time.time() - t0)))


if __name__ == "__main__":
    main()
