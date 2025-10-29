# -*- coding: utf-8 -*-
"""
imap_daq.py

Stop Forwarding and Start POSTing!
- scan imap inbox for emails should be sent to Empirasign servers
- send emails to api.empirasign.com/submit-email/
- archive them in designated folder
- compatible with Windows and Linux
"""

import configparser
import datetime
import imaplib
import os
import platform
import signal
import socket
import time
from pathlib import Path

import requests

from empirasign import ParserClient
from empirasign.utils import get_logger, safe_create_folder

THIS_DIR = Path(__file__).parent
if platform.system() == "Windows":
    CACHE_DIR = Path(os.getenv("APPDATA"))
else:
    CACHE_DIR = Path.home() / ".config"

CONF_NAME = 'email_daq.ini'
CONF_PATH = THIS_DIR / CONF_NAME
if not CONF_PATH.is_file():
    CONF_PATH = CACHE_DIR / CONF_NAME

IMAP = None

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
        'imap_settings': {
            'imap_server': 'imap.gmail.com',
            'source_folder': 'INBOX',
            'completed_folder': 'PARSED'
        },
        'user_settings': {
            'business_hours_start': 7,
            'business_hours_end': 17,
            'business_hours_interval': 300,
            'non_business_hours_interval': 1800
        },
        'app_settings': {
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

        # validate imap email credentials
        if not self['imap_settings']['email_account']:
            raise ValueError('Missing email account in the config file')
        if not self['imap_settings']['password']:
            raise ValueError('Missing email password in the config file')

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

        log_dir = Path(self.final_config['app_settings']['log_dir'])
        self.final_config['app_settings']['log_path'] = log_dir / 'imap_daq.log'

        self.final_config['imap_settings']['email_account'] = self['imap_settings']['email_account'].strip('\'"')
        self.final_config['imap_settings']['password'] = self['imap_settings']['password'].strip('\'"')


def transmit_mail(api, data, uid):
    """
    given email data, transmit to API endpoint for Empirasign servers
    """
    rfc_bytes = data[0][1]
    try:
        if DEBUG and CONF['app_settings']['debug_url']:
            post_data = {'rfc': rfc_bytes.decode("utf-8")}
            resp = requests.post(CONF['app_settings']['debug_url'], json=post_data,
                                 headers=api.headers, proxies=api.proxy_dict, timeout=15)
            res = resp.json()
        else:
            res = api.submit_eml(rfc_bytes, timeout=15)

        if res['meta']['results'] == 'OK':
            IMAP.uid('MOVE', uid, COMPLETED_FOLDER)  # move completed messages
        else:
            logger.error('error occurred during submission: %s', res['meta']['errors'])
    except Exception:  # pylint: disable=broad-except
        logger.exception("network or IO error")


def get_imap_uids(max_size=2500000):
    """
    return list of IMAP uids smaller than the max_size
    """
    if max_size:
        search_str = "(SMALLER {})".format(int(max_size))
    else:
        search_str = ""
    status, data = IMAP.uid('search', None, search_str)
    if status == "OK":
        return sorted([x.decode("ascii") for x in data[0].split()])
    return []


def main_loop():
    """
    scan inbox and deliver every detected email
    """
    status, _ = IMAP.select(SOURCE_FOLDER, readonly=False)

    if status != "OK":
        logger.warning("Invalid folder: '%s'", SOURCE_FOLDER)
        raise ValueError

    target_lst = get_imap_uids()
    if not target_lst:
        logger.info("No new emails detected in folder: %s", SOURCE_FOLDER)
        return

    logger.info("%s emails to parse in target folder: %s", len(target_lst), SOURCE_FOLDER)

    safe_create_folder(IMAP, COMPLETED_FOLDER)

    api = ParserClient(CONF['credentials']['api_key'], CONF['credentials']['api_secret'],
                       PROXY_SERVER)

    for imap_uid in target_lst:
        typ, data = IMAP.uid('fetch', imap_uid, '(RFC822)')
        if typ == 'OK':
            transmit_mail(api, data, imap_uid)


def main():
    """
    the main event
    """
    global IMAP  # pylint: disable=global-statement

    # authenticate imap login
    try:
        IMAP = imaplib.IMAP4_SSL(CONF["imap_settings"]['imap_server'])
    except socket.gaierror:
        logger.error('Invalid imap server: %s', CONF["imap_settings"]['imap_server'])
        return

    try:
        IMAP.login(CONF["imap_settings"]['email_account'], CONF["imap_settings"]['password'])
    except imaplib.IMAP4.error:
        logger.error('Invalid email credentials')
        if CONF["imap_settings"]['imap_server'] == 'imap.gmail.com':
            logger.info("For gmail, make sure to also enable IMAP in "\
                        "account settings and 'less secure apps' in gmail settings "\
                        "(https://myaccount.google.com/lesssecureapps)")
        else:
            logger.info("Some services may require certain settings to "\
                        "be enabled for third-party apps")
        return

    logger.info('sucessfully logged in to email')
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
    DEBUG = CONF["app_settings"]["debug"]
    PROXY_SERVER = CONF["app_settings"]["proxy_server"]
    SOURCE_FOLDER = CONF["imap_settings"]["source_folder"]
    COMPLETED_FOLDER = CONF["imap_settings"]["completed_folder"]

    logger = get_logger(CONF["app_settings"]["log_path"])

    signal.signal(signal.SIGTERM, _handle_exit)
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.warning("user hit CTRL-C or killed process, now exiting")
        if IMAP:
            IMAP.logout()
    except Exception as e:  # pylint: disable=broad-except
        logger.exception('untrapped exception: %s' % e)
        logger.info('Please email a copy of this log file "%s" to info@empirasign.com',
                    CONF["app_settings"]["log_path"])
        if IMAP:
            IMAP.logout()
