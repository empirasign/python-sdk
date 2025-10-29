"""
base_client.py

Base Empirasign API Client
"""
import logging
import datetime
import time
import random

import requests

logger = logging.getLogger(__name__)

class APIClient:
    """
    Base client for Empirasign APIs

    Attributes:
        verbose     (bool): Indicates if methods should print descriptive messages
        timeout     (float | tuple): default API request timeout in seconds or
                                     (connect timeout, read timeout) tuple
        api_key     (str): Empirasign API key
        api_secret  (str): Empirasign API Secret
        proxy_dict  (dict): requests proxy dictionary {protocol: proxy host}
        headers     (dict): API request headers
    """
    _ua_string_suffix = " api-oo-v1"

    # API path
    # assigned by subclasses
    _api_scheme = None
    _api_host = None
    _api_base = None
    _api_version = None

    # Response flds varied by API
    # assigned by subclasses
    _quota_key = None
    _next_page_key = None

    def __init__(self, api_key, api_secret, proxy_server=None):
        """
        Initialize the class.

        Args:
            api_key      (str): Your assigned API Key
            api_secret   (str): Your assigned API Secret
            proxy_server (str, Optional): https://www.empirasign.com/api-mbs/#proxy-server
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.proxy_dict = self.__proxies_dict(proxy_server)
        self.headers = requests.utils.default_headers()
        self.headers.update({'EMPIRASIGN-KEY': self.api_key, 'EMPIRASIGN-SECRET': self.api_secret})
        self.headers["User-Agent"] += self._ua_string_suffix

        self.verbose = False
        self.timeout = None

    @staticmethod
    def __proxies_dict(proxy_server):
        """
        Returns proxy dictionary required by requests library.
        http://docs.python-requests.org/en/latest/user/advanced/#proxies

        Args:
            proxy_server (str, Optional): proxy server host
        """
        if proxy_server:
            return {'http': f'http://{proxy_server}', 'https': f'https://{proxy_server}'}
        return {}

    def _request(self, url, params, method='GET', timeout=None, max_retries=3, base_delay=1):
        """
        request with exponential backoff
        """
        timeout = timeout or self.timeout
        for retry in range(max_retries + 1):
            try:
                if method == 'GET':
                    resp = requests.get(url, params, headers=self.headers,
                                        proxies=self.proxy_dict, timeout=timeout)
                else:
                    resp = requests.post(url, json=params, headers=self.headers,
                                         proxies=self.proxy_dict, timeout=timeout)
                break
            except requests.exceptions.RequestException as e:
                if retry == max_retries:
                    logger.warning('API request failed (attempt %d/%d): GET %s %s',
                                   retry + 1, max_retries + 1, url, repr(e))
                    raise

                delay = base_delay * (2 ** retry) + random.uniform(0, 1)
                logger.warning('API request failed (attempt %d/%d): GET %s %s (Retrying in %.2f)',
                                retry + 1, max_retries + 1, url, repr(e), delay)
                time.sleep(delay)
        return resp

    def _request_api(self, endpoint, params, method='GET', timeout=None):
        """
        Construct standard request
        """
        api_url = f'{self._api_scheme}://{self._api_host}{self._api_base}/v{self._api_version}/{endpoint}/'
        resp = self._request(api_url, params, method, timeout)
        if self.verbose:
            logger.info('Making request... %s', endpoint)
            logger.info('\tURL: %s', resp.url)
            logger.info('\tHTTPS Method: %s', method)
            logger.info('\tQuery Parameters: %s', params)
            logger.info('\tResponse Code: %s', resp.status_code)

        resp_json = resp.json()
        if self.verbose:
            if self._quota_key in resp_json['meta']:
                logger.info('\tRequests Left: %s', resp_json['meta'][self._quota_key])
            if resp.status_code != 200:
                logger.info('Errors: ' + '\n'.join(resp_json['meta']['errors']))
        return resp_json

    def _paginated_requests(self, endpoint, params, method='GET', max_pages=None, timeout=None):
        """
        Loop through paginated responses, consolidate results
        """
        next_url = f'{self._api_scheme}://{self._api_host}{self._api_base}/v{self._api_version}/{endpoint}/'

        results = {"data": []}
        results['meta'] = {'errors': [], 'warnings': []}

        pages_read = 0
        while next_url:
            time.sleep(1)
            resp = self._request(next_url, params, method, timeout)
            resp_json = resp.json()
            next_url = None
            pages_read += 1

            if self.verbose:
                logger.info('Making request... %s', endpoint)
                logger.info('\tURL: %s', resp.url)
                logger.info('\tHTTPS Method: %s', method)
                logger.info('\tQuery Parameters: %s', params)
                logger.info('\tFormat: JSON')
                logger.info('\tResponse Code: %s', resp.status_code)
                if self._quota_key in resp_json['meta']:
                    logger.info('\tRequests Left: %s', resp_json['meta'][self._quota_key])
                if resp.status_code != 200:
                    logger.info('Errors: ' + '\n'.join(resp_json['meta']['errors']))

            results['data'].extend(resp_json.get('data', []))
            results['meta']['errors'].extend(resp_json['meta'].get('errors', []))
            results['meta']['warnings'].extend(resp_json['meta'].get('warnings', []))
            if self._quota_key in resp_json['meta']:
                results['meta'][self._quota_key] = resp_json['meta'][self._quota_key]

            paging = resp_json['meta'].get('paging')
            if paging:
                if self.verbose:
                    logger.info('Current Page: %s', paging['current_page'])
                    logger.info('Showing %s results', paging['page_size'])
                if paging.get(self._next_page_key) and (not max_pages or max_pages > pages_read):
                    next_url = paging[self._next_page_key]
        return results

    @staticmethod
    def _handle_date_args(req_params, date_args, default_today=False):
        """
        handle single date, date range, or no date situations
        """
        args = {}
        if isinstance(date_args, (list, tuple)) and len(date_args) == 2:
            start, end = date_args[0], date_args[1]
            if isinstance(start, datetime.datetime) and isinstance(end, datetime.datetime):
                args['d0'] = start.strftime("%Y-%m-%dT%H:%M:%S")
                args['d1'] = end.strftime("%Y-%m-%dT%H:%M:%S")
            elif isinstance(start, datetime.date) and isinstance(end, datetime.date):
                args['d0'] = start.strftime("%Y-%m-%d")
                args['d1'] = end.strftime("%Y-%m-%d")
            else:
                args['d0'] = start
                args['d1'] = end
        elif isinstance(date_args, (str, datetime.date)):
            single = date_args
            args['dt'] = single.strftime("%Y-%m-%d") if isinstance(single, datetime.date) else single
        elif default_today:
            args['dt'] = datetime.date.today().strftime("%Y-%m-%d")
        elif date_args:
            raise ValueError("Invalid date arguments")
        req_params.update(args)
        return req_params

    @staticmethod
    def _handle_single_dt(dt, default_today=False):
        """
        handle single date formatting and default
        """
        if default_today:
            dt = dt or datetime.date.today()
        return dt.strftime('%Y-%m-%d') if isinstance(dt, datetime.date) else dt
