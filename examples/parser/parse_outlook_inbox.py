#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_outlook_inbox.py

Example script to parse runs in Outlook client Inbox
- saves to local JSON files
- maintains state using IMAP folders
- compatible with WINDOWS ONLY

Full API Documentation: https://www.empirasign.com/v1/parser-api-docs/

Extra Requirements:

Python for Win32 (pywin32) extensions
https://github.com/mhammond/pywin32
"""

import datetime
import json
import os
import tempfile
import time
from urllib.parse import quote
from pathlib import Path

import win32com.client  # pylint: disable=import-error
import win32ui  # pylint: disable=import-error

from empirasign import ParserClient
from empirasign.utils import get_logger

# ------------ USER CONFIGURATION ------------

API_KEY = "YOUR_EMPIRASIGN_API_KEY"        # provided by Empirasign
API_SECRET = "YOUR_EMPIRASIGN_API_SECRET"  # provided by Empirasign
PROXY_SERVER = ""  # e.g. proxy.mycompany.net:8080
# if you get a 407 Proxy Authentication Required error, you need to set
# PROXY_SERVER to something like username:password@proxy.mycompany.net:8080

# this script maintains state via folder usage
# once an email is moved into COMPLETED_FOLDER, no further parsing attempts
# will be made
SOURCE_FOLDER = "INBOX"
COMPLETED_FOLDER = "PARSED"

RESULTS_DIR = Path(tempfile.gettempdir())
LOG_DIR = Path(tempfile.gettempdir())
LOG_NAME = "parse_outlook_inbox.log"

# ------------ END USER CONFIGURATION ------------

logger = get_logger(LOG_DIR / LOG_NAME)


def get_target_mail_items(inbox, dt0, dt1=None):
    """
    return list of MailItems uids for a date or date range, label and max_size
    """
    if not dt1:
        dt1 = datetime.date.today() + datetime.timedelta(1)
    if dt1 < dt0:
        dt0, dt1 = dt1, dt0
    dt1 += datetime.timedelta(1)  # this makes the search inlusive?

    dt0_str = dt0.strftime(r'%Y-%m-%d %H:%M %p')
    dt1_str = dt1.strftime(r'%Y-%m-%d %H:%M %p')
    # https://documentation.help/Microsoft-Outlook-Visual-Basic-Reference/olmthRestrict.htm
    filter_str = "[ReceivedTime] >= '{}' And [ReceivedTime] < '{}'".format(dt0_str, dt1_str)
    logger.info("applying filter on inbox: %s", filter_str)
    target_items = inbox.Restrict(filter_str)
    logger.info('Detected %s target emails to parse', len(target_items))
    return target_items


def _safe_create_folder(root_folder, subfolder):
    """
    create subfolder under root_folder (aka INBOX) if it does not already exist
    """
    subfolders = [folder.Name for folder in root_folder.Folders]
    if subfolder not in subfolders:
        logger.info("creating folder %s under INBOX", subfolder)
        root_folder.Folders.Add(subfolder)
    logger.info("%s already exists as subfolder inder INBOX", subfolder)
    # reutrn the destination folder as an object
    return root_folder.Folders[subfolder]


def msg_to_disk(msg):
    """
    Save an Outlook Mailitem object as a .msg file to the temp directory
    """
    fname = quote(msg.EntryID, safe="") + ".msg"
    msg_path = str(Path(tempfile.gettempdir()) / fname)
    msg.SaveAs(msg_path)
    return msg_path


def main():
    """
    the main event
    """

    t0 = time.time()
    logger.info("parse_outlook_inbox.py starting")

    # Check if Outlook is opened
    try:
        win32ui.FindWindow(None, "Microsoft Outlook")
    except win32ui.error:
        logger.warning("Outlook is not running, trying to start")
        try:
            os.startfile("outlook")  # pylint: disable=no-member
        except Exception:  # pylint: disable=broad-except
            logger.exception("Cannot find Outlook")
            raise

    outlook = win32com.client.Dispatch('outlook.application')
    mapi = outlook.GetNamespace('MAPI')
    # retrieve user's email address or exit if there are no accounts logged in
    if mapi.Accounts.Count == 0:
        logger.warning("Outlook is running but default user is not authenticated vs email server")
        raise RuntimeError

    inbox_folder = mapi.GetDefaultFolder(6)
    dest_folder = _safe_create_folder(inbox_folder, COMPLETED_FOLDER)
    # https://docs.microsoft.com/en-us/office/vba/api/outlook.oldefaultfolders
    target_lst = get_target_mail_items(inbox_folder.Items, datetime.date.today())
    if not target_lst:
        logger.warning('No emails to parse')

    api = ParserClient(API_KEY, API_SECRET, PROXY_SERVER)

    done_lst = []
    quota = True
    for msg in target_lst:
        msg_path = msg_to_disk(msg)
        res = api.parse_email_file('corp', msg_path, 3.5)

        if res['meta']['results'] == 'OK':
            done_lst.append(msg.EntryID)
            # compute a filename that's safe on Windows and Linux
            # https://docs.microsoft.com/en-us/windows/win32/fileio/naming-a-file
            fname = quote(msg.EntryID, safe="") + ".json"
            # reversible via unquote(fname)[:-5]

            logger.info("saving parsed results MailItem.EntryID: %s filename: %s",
                        msg.EntryID, fname)
            msg.Move(dest_folder)
            # check remaininq quota
            if res["meta"]["api_req_left"] < 1:
                quota = False
        else:
            fname = quote(msg.EntryID, safe="") + "-error.json"
            logger.warning("parser error occurred: %s",  res['meta']['errors'])
            logger.warning("saving error file, MailItem.EntryID: %s, filename: %s", msg.EntryID, fname)

        with open(RESULTS_DIR / fname, "wt") as fp:
            fp.write(json.dumps(res, sort_keys=True, indent=2, ensure_ascii=False))

        if not quota:
            logger.warning("early exit of loop, daily quota exhausted, processed %s / %s",
                           len(done_lst), len(target_lst))
            break

    tot_runtime = round(time.time() - t0)
    logger.info("finished total run time secs: %s, target_lst: %s processed_lst: %s ", tot_runtime,
                target_lst, len(done_lst))


if __name__ == "__main__":
    main()
