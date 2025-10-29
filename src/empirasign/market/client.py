# -*- coding: utf-8 -*-
"""
market/client.py

This module illustrates how to access the Empirasign Market Data API
using Python in a Object-Oriented manner.
Access every public endpoint using a single class.

Full API Documentation: https://www.empirasign.com/v1/market-api-docs/

Endpoint Summary:
    HTTP METHOD     API ENDPOINT           QUOTA HIT                CLASS METHOD
    POST            /api/v1/bonds/         1 per bond               get_market_data
    GET             /api/v1/bwics/         None                     get_bwics
    POST            /api/v1/nport/         1 per bond               get_nport
    GET             /api/v1/offers/        None                     get_available_runs
    GET             /api/v1/offers/        1 per offer              get_dealer_runs
    GET             /api/v1/deal-classes/  None                     get_deal
    GET             /api/v1/all-bonds/     None                     get_active_bonds
    POST            /api/v1/collab/        None                     get_suggested
    GET             /api/v1/mbsfeed/       None                     get_events
    GET             /api/v1/query-log/     None                     get_query_log
    GET             /api/v1/mystatus/      None                     get_status

    POST            /api/v1/corp-bonds/    1 per bond, per page     get_corp_market_data
    GET             /api/v1/corp-runs/     None                     get_corp_available_runs
    GET             /api/v1/corp-runs/     1 per offer, per page    get_corp_dealer_runs

Dates:
    Dates should be represented as datetime.date or datetime.datetime objects or their
    respective ISO 8601 string representations, '2024-06-18' and '2024-06-18T12:00:00'

    NOTE: datetime.datetime constraints are only available for corporate-specific endpoints

Example Usage:
    api = MarketDataClient("API_KEY", "API_SECRET")  # initialize an authorized API object

    # grab market data
    api.get_market_data(["05543DBT0", "36242DL68", "43739EBN6"])

    # grab market data for a specific date
    api.get_market_data(["05543DBT0", "36242DL68", "43739EBN6"], datetime.date(2021, 01, 01))

    # use tuple to specify a date range
    api.get_market_data(["05543DBT0", "36242DL68", "43739EBN6"], (d0, d1))

    api.quota  # check your remaining queries
"""

import logging  # descriptive logging in verbose mode

from empirasign.base_client import APIClient

logger = logging.getLogger(__name__)


class MarketDataClient(APIClient):
    """
    Client for accessing all endpoints of the Empirasign Market Data API

    Properties:
        quota (int): current status of API quota

    All methods accept a timeout argument:
        timeout (float | tuple, optional): API request timeout in seconds or
                                           (connect timeout, read timeout) tuple
    """
    _api_scheme = 'https'
    _api_host = 'www.empirasign.com'
    _api_base = '/api'
    _api_version = 1

    _quota_key = 'requests_left'
    _next_page_key = 'next'

    @property
    def quota(self):
        """Current API quota"""
        return self.get_status()[self._quota_key]

    @staticmethod
    def __chunker(lst, chunk_size):
        """
        Break down large lists into managable chunks
        """
        for i in range(0, len(lst), chunk_size):
            yield lst[i:i + chunk_size]

    def __bulk_request_api(self, endpoint, bulk_items, params, chunk_size,
                           req_key="bonds", res_key="data", timeout=None):
        """
        Break up bulk requests that exceed per-query limits, consolidate results
        """
        results = {res_key: [], 'meta': {'errors': [], 'warnings': []}}
        for items_chunk in self.__chunker(bulk_items, chunk_size):
            params[req_key] = ",".join(items_chunk)
            res = self._request_api(endpoint, params, method='POST', timeout=timeout)
            results[res_key].extend(res.get(res_key, []))
            results['meta']['errors'].extend(res['meta'].get('errors', []))
            results['meta']['warnings'].extend(res['meta'].get('warnings', []))
            if self._quota_key in res['meta']:
                results['meta'][self._quota_key] = res['meta'][self._quota_key]
        return results

    #--------------------- Public API Endpoint Methods -------------------------

    def get_market_data(self, uids, date_args=None, nport=False, timeout=None):
        """
        Get all market data for a list of bonds.
        Args:
            uids        (list of str): List of unique bond identifiers (CUSIP, ISIN, or BBG Ticker).
            date_args   (datetime.date or str:YYYY-MM-DD, Optional): Single search date.
                        (tuple, Optional): Start and end of date range (inclusive).
                        NOTE: Defaults to no date constraint
            nport       (bool, Optional): Include N-PORT data if True
        """
        req_params = self._handle_date_args({}, date_args)
        req_params['nport'] = nport
        return self.__bulk_request_api('bonds', uids, req_params, 200, timeout=timeout)

    def get_bwics(self, sector, date_args=None, timeout=None):
        """
        Get summary level data for BWICs in a given sector. NOTE: Maximum 60 day lookback
        Args:
            sector      (str): BWIC sector defined in www.empirasign.com/api-mbs/
            date_args   (datetime.date or str:YYYY-MM-DD, Optional): Single search date.
                        (tuple, Optional): Start and end of date range (inclusive).
                        NOTE: Defaults to no date constraint
        """
        req_params = self._handle_date_args({'sector': sector}, date_args, default_today=True)
        return self._request_api('bwics', req_params, timeout=timeout)

    def get_nport(self, uids, date_args=None, timeout=None):
        """
        Get NPORT filing data for a list of bonds.
        Args:
            uids         (list of str): List of bond identifiers (CUSIPs or ISINs only).
            date_args    (datetime.date or str:YYYY-MM-DD, Optional): Single search date.
                         (tuple, Optional): Start and end of date range (inclusive).
                         NOTE: Defaults to no date constraint
        """
        req_params = self._handle_date_args({}, date_args)
        return self.__bulk_request_api('nport', uids, req_params, 750, timeout=timeout)

    def get_deal_classes(self, uid, timeout=None):
        """
        Give all tranches on the deal.
        Args:
            uid     (str): A bond identifier (CUSIP, ISIN, BBG Ticker, or Deal Series).
        """
        return self._request_api('deal-classes', {'bond': uid}, timeout=timeout)

    def get_available_runs(self, date_args=None, min_cf=None, timeout=None):
        """
        Get all dealer & sector combinations for Dealer Runs on a given date.
        Args:
            date_args   (datetime.date or ISO 8601 str, Optional): Single search date.
                        (tuple, Optional): Start and end of datetime range.
                            datetime.datetime or ISO 8601 str [start, end)
            min_cf      (float, Optional): Filter results by minimum CF
        NOTE: Defaults to today; datetime range constraints must be same day
        """
        req_params = self._handle_date_args({}, date_args, default_today=True)
        if min_cf is not None:
            req_params['min_cf'] = min_cf
        return self._request_api('offers', req_params, timeout=timeout)

    def get_dealer_runs(self, dealer, sector, date_args=None, min_cf=None, timeout=None):
        """
        Get all Dealer Runs records for a particular dealer, sector, & date combination.
        Args:
            dealer      (str): The dealer
            sector      (str): The sector
            date_args   (datetime.date or ISO 8601 str, Optional): Single search date.
                        (tuple, Optional): Start and end of datetime range.
                            datetime.datetime or ISO 8601 str [start, end)
            min_cf      (float, Optional): Filter results by minimum CF
        NOTE: Defaults to today; datetime range constraints must be same day
        """
        req_params = {'dealer': dealer, 'sector': sector}
        req_params = self._handle_date_args(req_params, date_args, default_today=True)
        if min_cf is not None:
            req_params['min_cf'] = min_cf
        return self._request_api('offers', req_params, timeout=timeout)

    def get_active_bonds(self, dt=None, figi_marketsector='Mtge', kind=None, timeout=None):
        """
        Get all bonds that appeared on BWICs or Dealer Runs for a given date & sector.
        NOTE: figi_marketsector is exactly equivalent to marketSecDes as defined by OpenFIGI
        https://www.openfigi.com/api#openapi-schema
        Args:
            dt                  (datetime.date or str:YYYY-MM-DD): The query date.
            figi_marketsector   (str, Optional): The market sector "Mtge" or "Corp", default Mtge.
            kind                (str, Optional): Kind of market activity, "bwics" or "runs".
        """
        dt = self._handle_single_dt(dt, default_today=True)
        req_params = {'figi_marketsector': figi_marketsector, 'dt': dt}
        if kind and kind in ('bwics', 'runs'):
            req_params['kind'] = kind
        elif kind:
            raise ValueError("If specified, kind must be either 'bwics' or 'runs'")
        return self._request_api('all-bonds', req_params, timeout=timeout)

    def get_all_matchers(self, dt=None, timeout=None):
        """
        Get all bonds that appeared on BWICs or Dealer Runs for a given date that also appeared on
        recent Fund Holdings (N-PORT) or Insurance Transactions (NAIC) filings.
        https://www.openfigi.com/api#openapi-schema
        Args:
            dt                  (datetime.date or str:YYYY-MM-DD): The query date.
        """
        dt = self._handle_single_dt(dt, default_today=True)
        return self._request_api('all-matchers', {'dt': dt}, timeout=timeout)

    def get_suggested(self, uids, timeout=None):
        """
        Get a list of similar bonds for each bond provided using Empirasign's
        Collaborative Search Algorithm: https://www.empirasign.com/blog/Collaborative-Search/
        NOTE: Maximum 50 bonds per request
        Args:
            uids  (list of str): List of unique bond identifiers (CUSIP, ISIN, BBG Ticker)
        """
        return self.__bulk_request_api('collab', uids, {}, 50, res_key='data', timeout=timeout)

    def get_events(self, n=15, timeout=None):
        """
        Get the latest market events from the news feed (new bwic, price talk, or trade color).
        Args:
            n   (int, Optional): Number of events, defaults to 15. n must be between 1 and 200.
        """
        return self._request_api('mbsfeed', {'n': n}, timeout=timeout)

    def get_query_log(self, dt=None, timeout=None):
        """
        Get a log of queries made on a given date. 30 day maximum lookback.
        Args:
            dt  (datetime.date or str:YYYY-MM-DD, Optional): The query date, defaults to today.
        """
        dt = self._handle_single_dt(dt, default_today=True)
        return self._request_api('query-log', {'dt': dt}, timeout=timeout)

    def get_status(self, timeout=None):
        """
        Check API status and see how many queries are remaining in your quota.
        """
        return self._request_api('mystatus', {}, timeout=timeout)

    def get_corp_market_data(self, uids, date_args=None, max_pages=None, timeout=None):
        """
        Get all market data for a list of corporate bond identifiers.
        As of now, only dealer runs data available for corporates.

        NOTE: This method returns all paginated results by default.
        NOTE: Date range can be dates or datetimes for precision polling
        NOTE: Maximum 100 UIDs per request

        Args:
            uids (list of str): List of unique bond identifiers (CUSIP, ISIN, or FIGI).
            date_args   (datetime.date or ISO 8601 str, Optional): Single search date.
                        (tuple, Optional): Start and end of date/datetime range.
                            datetime.date or ISO 8601 str (inclusive)
                            datetime.datetime or ISO 8601 str [start, end)
            max_pages   (int): Maximum number of result pages queried/returned
        NOTE: Defaults to no date constraint
        """
        req_params = self._handle_date_args({'bonds': ",".join(uids)}, date_args)
        return self._paginated_requests('corp-bonds', req_params, 'POST', max_pages, timeout)

    def get_corp_available_runs(self, date_args=None, timeout=None):
        """
        Get all dealer & sector combinations for Dealer Runs on a given date.
        Args:
            date_args   (datetime.date or ISO 8601 str, Optional): Single search date.
                        (tuple, Optional): Start and end of datetime range.
                            datetime.datetime or ISO 8601 str [start, end)
        NOTE: Defaults to today, datetime range constraints must be same day
        """
        req_params = self._handle_date_args({}, date_args, default_today=True)
        return self._request_api('corp-runs', req_params, timeout=timeout)

    def get_corp_dealer_runs(self, dealer, date_args=None, max_pages=None, timeout=None):
        """
        Get all Dealer Runs records for a particular dealer, sector, & date combination.
        Args:
            dealer      (str): The dealer
            date_args   (datetime.date or ISO 8601 str, Optional): Single search date.
                        (tuple, Optional): Start and end of datetime range.
                            datetime.datetime or ISO 8601 str [start, end)
            max_pages   (int): Maximum number of result pages queried/returned
        NOTE: This method returns all paginated results automatically.
        NOTE: Defaults to today, datetime range constraints must be same day
        """
        req_params = self._handle_date_args({'dealer': dealer}, date_args, default_today=True)
        return self._paginated_requests('corp-runs', req_params, 'GET', max_pages, timeout)
