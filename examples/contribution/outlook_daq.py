# -*- coding: utf-8 -*-
"""
outlook_daq.py

Stop Forwarding and Start POSTing!
- scan MS Outlook instance for tagged emails to be sent to Empirasign servers
- send these messages api.empirasign.com/submit-email/
- mark messages as sent, by changing catetory to __mkt_data  (double underscore)
- compatible with WINDOWS ONLY

Extra Requirements:

Python for Win32 (pywin32) extensions
https://github.com/mhammond/pywin32

Getting Started
You must set up Rules to Categorize emails you want sent via API to Empirasign

How to set up Rules in Microsoft Outlook
https://support.microsoft.com/en-us/office/set-up-rules-in-outlook-75ab719a-2ce8-49a7-a214-6d62b67cbd41

What are Categories?
https://support.microsoft.com/en-us/office/use-categories-in-outlook-com-a0f709a4-9bd8-45d7-a2b3-b6f8c299e079

Our documentation on forwarding messages direct from Outlook also has notes
on using and setting up Rules
https://www.empirasign.com/outlook-tutorial/
"""

import base64
import configparser
import datetime
import os
import shelve
import signal
import time
from pathlib import Path

import requests
import win32com.client  # pylint: disable=import-error
import win32ui  # pylint: disable=import-error

from empirasign import ParserClient
from empirasign.utils import get_logger

THIS_DIR = Path(__file__).parent
CACHE_DIR = Path(os.getenv("APPDATA"))

CONF_NAME = 'email_daq.ini'
CONF_PATH = THIS_DIR / CONF_NAME
if not CONF_PATH.is_file():
    CONF_PATH = CACHE_DIR / CONF_NAME

TEMP_DIR = Path(os.getenv("TEMP"))


def _handle_exit(sig, frame):
    """
    gracefully handle a killed process
    """
    raise SystemExit


class Config(configparser.ConfigParser):
    """
    ConfigParser implementation with validation and fallback
    """
    _default_config = {
        'outlook_settings': {
            'auto_open_outlook': True,
            'submit_category': '_mkt_data',
            'default_lookback_period': 1
        },
        'user_settings': {
            'business_hours_start': 7,
            'business_hours_end': 17,
            'business_hours_interval': 300,
            'non_business_hours_interval': 1800,
        },
        'app_settings': {
            'cache_dir': str(CACHE_DIR),
            'log_dir': str(CACHE_DIR),
            'debug_url': '',
            'debug': False,
            'proxy_server': ''
        }
    }

    def __init__(self, config_file, inline_comment_prefixes=';'):
        """
        Initialize configuration

        Args:
            config_file (str | bytes | os.PathLike | list): config file path or list of config file paths
            inline_comment_prefixes (str, optional): set of substrings that prefix comments in
                                                     non-empty lines. Defaults to ';'.
        """
        super().__init__(inline_comment_prefixes=inline_comment_prefixes)
        self.read(config_file)  # each Section in the config file becomes a class attribute

        self.final_config = {}  # contains config fields with correct data types
        self.validate_config()
        self.slot_config()

    @property
    def default_config(self):
        """
        default configuration values
        """
        return self._default_config.copy()

    def validate_config(self):
        """
        ensure required credentials are provided
        """
        # validate parser credentials
        if not self['credentials']:
            raise ValueError('Missing credentials section in the config file')
        if not self['credentials']['api_key']:
            raise ValueError('Missing api_key in the config file')
        if not self['credentials']['api_secret']:
            raise ValueError('Missing api_secret in the config file')

    def slot_config(self):
        """
        Assign any missing fields in the configuration file to a default value
        Coerce all configuration fields to the correct data type

        ConfigParser by default bans read values from converting to non-strings,
        so all coerced fields are assigned to final_config
        """
        self.final_config['credentials'] = self['credentials']

        for section, fields in self.default_config.items():
            # assign entirety of a section and its fields if missing from config file
            if section not in self:
                self.final_config[section] = fields
                continue
            self.final_config[section] = {}

            for field, val in fields.items():
                # assign default value if missing from config file
                if field not in self[section] or self[section][field] == '':
                    self.final_config[section][field] = val
                    continue

                # coerce strings to correct data type based on default_config
                if isinstance(val, str):
                    self.final_config[section][field] = self[section][field].strip('\'"')
                elif isinstance(val, bool):
                    self.final_config[section][field] = self.getboolean(section, field)
                elif isinstance(val, int):
                    self.final_config[section][field] = self.getint(section, field)
                elif isinstance(val, float):
                    self.final_config[section][field] = self.getfloat(section, field)

        # mutate specific fields
        cache_dir = Path(self.final_config['app_settings']['cache_dir'])
        self.final_config['app_settings']['cache_path'] = cache_dir / 'outlook_daq_cache.dat'
        log_dir = Path(self.final_config['app_settings']['log_dir'])
        self.final_config['app_settings']['log_path'] = log_dir / 'outlook_daq.log'


def export_msg(msg):
    """
    Save an Outlook Mailitem object as a .msg file to the temp directory
    """
    # NOTE we should look into used Message-ID or filename safe version of Message-ID as filename
    clean_subject = ''.join(c for c in str(msg.Subject) if c.isalnum())  # save for Windows
    # Windows filenames can't be longer than 255 chars
    fname = "{}_{}.msg".format(datetime.date.today(), clean_subject[:240])  # ISO 8601 is fine
    msg_path = TEMP_DIR / fname
    msg.SaveAs(msg_path)
    return msg_path


def transmit_mail(api, msg_path):
    """
    given a file path on disk, transmit to API endpoint for Empirasign servers
    """
    try:
        with open(msg_path, 'rb') as fp:
            msg_bytes = fp.read()
    except FileNotFoundError:
        # msg no longer exists in TEMP
        logger.info('%s not detected. No longer sending it.', msg_path)
        return

    try:
        if DEBUG and CONF['app_settings']['debug_url']:
            post_data = {'msg': base64.b64encode(msg_bytes).decode('ascii')}
            resp = requests.post(CONF['app_settings']['debug_url'], json=post_data,
                                 headers=api.headers, proxies=api.proxy_dict, timeout=15)
            res = resp.json()
        else:
            res = api.submit_msg(msg_bytes, timeout=15)

        if res['meta']['results'] == 'OK':
            os.remove(msg_path)
        else:
            logger.error('error occurred during submission: %s, msg_path: %s',
                         res['meta']['errors'], msg_path)
            STORAGE['revisit'] += [msg_path]
    except Exception:  # pylint: disable=broad-except
        logger.exception("network or IO error, msg_path: %s", msg_path)
        STORAGE['revisit'] += [msg_path]


def process_email(msg):
    """
    save a msg to disk and apply a category to signify this
    """
    msg_path = export_msg(msg)  # location on disk in TEMP_DIR
    # update the categories message will be in transmission queue
    # msg.Categories is just a delimited string
    # https://docs.microsoft.com/en-us/office/vba/api/outlook.mailitem.categories
    msg.Categories.replace(TARGET_CAT, TARGET_CAT_DONE)
    try:
        msg.Save()
        logger.info("successfully re-tagged email: %s, %s, %s", msg.Subject, msg.ReceivedTime,
                    msg.Categories)
    except Exception:  # pylint: disable=broad-except
        logger.exception("message save fails after categories mutation %s %s %s", msg.Categories,
                         msg.Subject, msg.ReceivedTime)
    # NOTE how do we ensure we don't keep uploading messages that we could not change the category
    return msg_path


def main_loop():
    """
    scan inbox and deliver any newly tagged emails
    """
    # Check if Outlook is opened
    try:
        win32ui.FindWindow(None, "Microsoft Outlook")
    except win32ui.error:
        if CONF["outlook_settings"]['auto_open_outlook']:
            try:
                os.startfile("outlook")  # pylint: disable=no-member
            except Exception:  # pylint: disable=broad-except
                logger.exception("Cannot find Outlook")
                return
        else:
            logger.warning("Outlook needs to be open")
            return

    outlook = win32com.client.Dispatch('outlook.application')
    mapi = outlook.GetNamespace('MAPI')

    # retrieve user's email address or exit if there are no accounts logged in
    if mapi.Accounts.Count == 0:
        logger.warning("No logged in users detected")
        return

    if 'revisit' not in STORAGE:
        STORAGE['revisit'] = []
    if 'last_timestamp' not in STORAGE:
        delta = datetime.timedelta(days=CONF["outlook_settings"]['default_lookback_period'])
        STORAGE['last_timestamp'] = datetime.datetime.now() - delta

    if DEBUG:
        STORAGE['last_timestamp'] = datetime.datetime.now() - datetime.timedelta(days=30)

    # https://docs.microsoft.com/en-us/office/vba/api/outlook.oldefaultfolders
    inbox = mapi.GetDefaultFolder(6).Items
    last_timestamp_str = STORAGE['last_timestamp'].strftime(r'%Y-%m-%d %H:%M %p')
    # https://documentation.help/Microsoft-Outlook-Visual-Basic-Reference/olmthRestrict.htm
    filter_str = """
    [ReceivedTime] >= '{}' And [Categories] = '{}' And Not([Categories] = '{}')
    """.format(last_timestamp_str, TARGET_CAT, TARGET_CAT_DONE)
    logger.info("applying filter on inbox: %s", filter_str)
    recent_inbox = inbox.Restrict(filter_str)
    STORAGE['last_timestamp'] = datetime.datetime.now()
    logger.info('Detected %s new emails', len(recent_inbox))

    msg_paths = [process_email(msg) for msg in recent_inbox]
    msg_paths.extend(STORAGE['revisit'])  # retry previous comm errors
    STORAGE['revisit'] = []

    api = ParserClient(CONF['credentials']['api_key'], CONF['credentials']['api_secret'],
                       PROXY_SERVER)

    msg_paths = set(msg_paths)  # pull out any dupes
    if msg_paths:
        logger.info("%s messages to transmit to endpoint", len(msg_paths))
        for msg_path in msg_paths:
            transmit_mail(api, msg_path)
    else:
        logger.info('No emails to send')


def main():
    """
    the main event
    """

    active_start_time = datetime.time(CONF["user_settings"]['business_hours_start'], 0, 0)
    active_end_time = datetime.time(CONF["user_settings"]['business_hours_end'], 0, 0)

    while True:
        main_loop()
        curr_time = datetime.datetime.now().time()
        if active_start_time <= curr_time <= active_end_time:
            loop_time = CONF["user_settings"]['business_hours_interval']
        else:
            loop_time = CONF["user_settings"]['non_business_hours_interval']
        if DEBUG:
            loop_time = 10
        time.sleep(loop_time)


if __name__ == "__main__":
    # load configuration file
    CONF = Config(CONF_PATH, inline_comment_prefixes=";").final_config

    # define config vars
    STORAGE = shelve.open(CONF["app_settings"]["cache_path"], flag="c")  # create if not exist
    DEBUG = CONF["app_settings"]["debug"]
    PROXY_SERVER = CONF["app_settings"]["proxy_server"]
    TARGET_CAT = CONF["outlook_settings"]["submit_category"]
    TARGET_CAT_DONE = "_" + TARGET_CAT

    logger = get_logger(CONF["app_settings"]["log_path"])

    signal.signal(signal.SIGTERM, _handle_exit)
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.warning("user hit CTRL-C or killed process, now exiting")
        STORAGE.close()
    except Exception as e:  # pylint: disable=broad-except
        logger.exception('untrapped exception: %s' % e)
        logger.info('Please email a copy of this log file "%s" to info@empirasign.com',
                    CONF["app_settings"]["log_path"])
        STORAGE.close()
