# -*- coding: utf-8 -*-
"""
parser/client.py

This module illustrates how to access the Empirasign Parser API
using Python in a Object-Oriented manner.
Access every public endpoint using a single class.

Full API Documentation: https://www.empirasign.com/v1/parser-api-docs/

Endpoint Summary:
    HTTP METHOD     API ENDPOINT           QUOTA HIT                CLASS METHOD
    POST            /parse-bwic/           1                        parse_email_file
                    /parse-run/                                     parse_eml
                    /parse-corp/                                    parse_msg
                    /parse-loan/
                    /parse-cds/

    POST            /id-mapper/            1 per id                 get_id_mapping
    GET             /mydata/               None                     get_mydata
    POST            /raw-msg/{tx_id}/      None                     get_raw_msg
    POST            /submit-email/         None                     submit_eml
                                                                    submit_msg

Example Usage:
    api = ParserClient('API_KEY', 'API_SECRET') # initialize an authorized API object

    # parse a dealer runs email
    api.parse_email_file('run', 'dealer_run.eml')

    # parse a bwic MS Outlook email
    api.parse_email_file('bwic', 'bwic.msg')

    # parse a corporate runs email string
    api.parse_eml('corp', '<eml string>')

    # request id mapping
    api.get_id_mapping([["cusip", "3128MMVE0"], ["isin", "US3138YKH632"]])

    # get MyData 1PM to 2PM
    api.get_mydata(('2025-01-01T13:00:00', '2025-01-01T14:00:00'))
"""
import logging
import base64
import email.policy
from email.header import Header
from email.utils import formataddr
from email.message import EmailMessage

from empirasign.base_client import APIClient

logger = logging.getLogger(__name__)


class ParserClient(APIClient):
    """
    Single class for accessing all endpoints of the Empirasign Parser API
    """
    _api_scheme = 'https'
    _api_host = 'api.empirasign.com'
    _api_base = ''
    _api_version = 1

    _quota_key = 'api_req_left'
    _next_page_key = 'next_page'

    _valid_parse_types = ('run', 'bwic', 'corp', 'loan', 'cds')
    _valid_id_types = ('bbg_ticker', 'cusip', 'id_bb', 'isin', 'figi', 'loanxid')

    def parse_eml(self, parse_type, eml, timeout=None):
        """
        Parse RFC .eml email

        Args:
            parse_type  (str): API endpoint, one of _valid_parse_types
            eml         (str | bytes): eml string or bytes
            timeout     (float | tuple, optional): API request timeout in seconds or
                                                   (connect timeout, read timeout) tuple
        """
        if parse_type not in self._valid_parse_types:
            raise ValueError(
                f'Invalid parse type: {parse_type}, Valid parse types: {self._valid_parse_types}')

        if isinstance(eml, bytes):
            eml = eml.decode('utf-8')
        return self._request_api(f'parse-{parse_type}', {'eml': eml}, 'POST', timeout)

    def parse_msg(self, parse_type, msg_bytes, timeout=None):
        """
        Parse Outlook .msg email

        Args:
            parse_type  (str): API endpoint, one of _valid_parse_types
            msg_bytes   (bytes): msg bytes
            timeout     (float | tuple, optional): API request timeout in seconds or
                                                   (connect timeout, read timeout) tuple
        """
        if parse_type not in self._valid_parse_types:
            raise ValueError(
                f'Invalid parse type: {parse_type}, Valid parse types: {self._valid_parse_types}')

        b64_str = base64.b64encode(msg_bytes).decode("ascii")
        return self._request_api(f'parse-{parse_type}', {'msg': b64_str}, 'POST', timeout)

    def parse_email_file(self, parse_type, file_path, timeout=None):
        """
        Parse Outlook .msg email

        Args:
            parse_type  (str): API endpoint, one of _valid_parse_types
            file_path   (str): email filepath
            timeout     (float | tuple, optional): API request timeout in seconds or
                                                   (connect timeout, read timeout) tuple
        """
        if file_path.lower().endswith(".msg"):
            with open(file_path, 'rb') as fp:
                msg_bytes = fp.read()
            return self.parse_msg(parse_type, msg_bytes, timeout)

        with open(file_path) as fp:
            eml_str = fp.read()
        return self.parse_eml(parse_type, eml_str, timeout)

    def get_mydata(self, date_args, timeout=None):
        """
        Get paginated mydata records within given time range

        Args:
            date_args   (tuple): Start and end of datetime range.
                                 datetime.datetime or ISO 8601 str [start, end)
            timeout     (float | tuple, optional): API request timeout in seconds or
                                                   (connect timeout, read timeout) tuple
        """
        req_params = self._handle_date_args({}, date_args)
        return self._paginated_requests('mydata', req_params, timeout=timeout)

    def get_raw_msg(self, tx_id, format_msg=False, timeout=None):
        """
        Retrieve raw email by transaction ID

        Args:
            tx_id       (str):  Parser transaction ID (UUID).
            format_msg  (bool): If True, returns a structured dictionary of email parts.
                                Returns raw source string by default.
            timeout     (float | tuple, optional): API request timeout in seconds or
                                                   (connect timeout, read timeout) tuple
        """
        return self._request_api(f'raw-msg/{tx_id}', {'format_msg': format_msg}, 'POST', timeout=timeout)

    def get_id_mapping(self, ids, timeout=None):
        """
        Get all associated identifiers for given bonds

        Args:
            ids (list[list[str, str]]): list of [id_type, id] key pairs to map
                                        id_type one of _valid_id_types
            timeout (float | tuple, optional): API request timeout in seconds or
                                               (connect timeout, read timeout) tuple
        """
        return self._request_api('id-mapper', {'ids': ids}, 'POST', timeout)

    def submit_eml(self, eml, timeout=None):
        """
        Send RFC .eml email to Empirasign

        Args:
            eml     (str | bytes): eml string or bytes
            timeout (float | tuple, optional): API request timeout in seconds or
                                               (connect timeout, read timeout) tuple
        """
        if isinstance(eml, bytes):
            eml = eml.decode('utf-8')
        return self._request_api('submit-email', {'rfc': eml}, 'POST', timeout)

    def submit_msg(self, msg_bytes, timeout=None):
        """
        Send Outlook .msg email to Empirasign

        Args:
            msg_bytes   (bytes): Outlook .msg email bytes
            timeout     (float | tuple, optional): API request timeout in seconds or
                                                   (connect timeout, read timeout) tuple
        """
        b64_str = base64.b64encode(msg_bytes).decode("ascii")
        return self._request_api('submit-email', {'msg': b64_str}, 'POST', timeout)

    def create_eml(self, subject, email_body,
                   sender_name='',
                   sender_email='',
                   recipient_name='',
                   recipient_email='',
                   received_time=None,
                   message_id=None):
        """
        Mock a .eml email for use with Parser API
        """
        mock_eml = EmailMessage(policy=email.policy.default)
        mock_eml['Subject'] = subject
        # From: John Doe (ACME CORP) <john.doe@acme.com>
        if recipient_name or recipient_email:
            mock_eml['To'] = formataddr((str(Header(recipient_name, 'utf-8')), recipient_email))
        if sender_name or sender_email:
            mock_eml['From'] = formataddr((str(Header(sender_name, 'utf-8')), sender_email))
        # Mon, 20 Nov 1995 19:12:08
        if received_time:
            mock_eml['Date'] = received_time.strftime('%a, %d %b %Y %H:%M:%S')
        if message_id:
            mock_eml['Message-ID'] = message_id
        mock_eml.set_content(email_body)
        return mock_eml.as_string()
