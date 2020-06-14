""" Spider for http/https protocols

@Author Kingen
@Date 2020/4/13
"""
import socket
import time
from urllib import parse, error
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from selenium import webdriver

from . import logger

BASE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.132 Safari/537.36'
}


def pre_download(url, pause=0.0, timeout=30, retry=3):
    """
    Do Pre-request a download url
    Get info of response, Content-Length or file size mainly.
    :return: (code, msg, args). Optional code and msg: (200, 'OK')/(1, 'Unknown Content Length')/(408, 'Timeout')
            'args', a dict of info will be returned if code is 200: size(B)
    """
    if pause > 0:
        time.sleep(pause)
    req = Request(quote_url(url), headers=BASE_HEADERS, method='GET')
    timeout_count = reset_count = no_response_count = refused_count = 0
    while True:
        try:
            logger.info('Pre-GET from %s', req.full_url)
            with urlopen(req, timeout=timeout) as r:
                size = r.getheader('Content-Length')
                if size is None:
                    logger.error('Unknown Content Length')
                    return 1, 'Unknown Content Length', None
                else:
                    return 200, 'OK', {'size': int(size)}
        except socket.timeout:
            logger.error('Timeout')
            if timeout_count >= retry:
                return 408, 'Timeout', None
            timeout_count += 1
            logger.info('Retry...')
            time.sleep(timeout)
        except error.HTTPError as e:
            logger.error(e)
            return e.code, e.reason, None
        except error.URLError as e:
            logger.error(e)
            if e.errno is not None:
                return e.errno, e.strerror, None
            if e.reason is not None:
                e = e.reason
                if isinstance(e, socket.gaierror):
                    return e.errno, e.strerror, None
                if isinstance(e, TimeoutError):
                    if no_response_count >= retry:
                        return e.errno, e.strerror, None
                    no_response_count += 1
                    logger.info('Retry...')
                    time.sleep(timeout)
                    continue
                if isinstance(e, ConnectionRefusedError):
                    if refused_count >= retry:
                        return e.errno, e.strerror, None
                    refused_count += 1
                    logger.info('Retry...')
                    time.sleep(timeout)
                    continue
            logger.error('Unknown error')
            raise e
        except ConnectionResetError as e:
            logger.error(e)
            if reset_count >= retry:
                return e.errno, e.strerror, None
            reset_count += 1
            logger.info('Retry...')
            time.sleep(timeout)


def quote_url(url: str) -> str:
    """
    Encode the url except the scheme and netloc only when doing a request
    """
    scheme, netloc, path, query, fragment = parse.urlsplit(url)
    return parse.urlunsplit((scheme, netloc, parse.quote(path), parse.quote(query, safe='=&'), parse.quote(fragment)))


class BaseSite:
    def __init__(self, name, domain, scheme='https', headers=None, timeout=30, interval=0) -> None:
        """
        :param name: name of the site
        :param domain: top-level domain of the site, like 'google.com'
        :param scheme: scheme of the site, generally http/https
        :param headers: headers for request
        :param timeout:
        :param interval: interval to do next request
        """
        self.__name = name
        self._scheme = scheme
        self.__domain = domain
        self.__headers = BASE_HEADERS
        if headers is not None:
            self.__headers.update(headers)
        self.__timeout = timeout
        self.__interval = interval
        self.__last_access = 0.0
        self.__chrome = webdriver.Chrome(executable_path='chromedriver 81.0.4044.138.exe')

    @property
    def name(self):
        return self.__name

    @property
    def home(self):
        return self._scheme + '://' + self.__domain + '/'

    def get_soup(self, req) -> BeautifulSoup:
        """
        Request and return a soup of the page
        """
        return BeautifulSoup(self.do_request(req), 'html.parser')

    def get_browser_soup(self, url, func=None) -> BeautifulSoup:
        return BeautifulSoup(self.browser(url, func), 'html.parser')

    def do_request(self, req, retry=3):
        """
        do request
        :param req: an instance of request.Request or a url
        :return: content of response
        """
        self.__next_access()
        if isinstance(req, str):
            req = Request(req, headers=self.__headers, method='GET')
        req.headers.update(self.__headers)
        logger.info('%s from %s', req.method, req.full_url)
        if req.get_method().upper() == 'POST' and req.data is not None:
            logger.info('Query: ' + parse.unquote(req.data.decode('utf=8')))
        timeout_count = reset_count = 0
        while True:
            try:
                with urlopen(req, timeout=self.__timeout) as r:
                    return r.read().decode('utf-8')
            except socket.timeout as e:
                logger.error('Timeout!')
                if timeout_count >= retry:
                    raise e
                timeout_count += 1
                logger.info('Retry...')
                time.sleep(self.__timeout)
            except error.HTTPError as e:
                logger.error(e)
                raise e
            except error.URLError as e:
                logger.error(e)
                if timeout_count >= retry:
                    raise e
                timeout_count += 1
                logger.info('Retry...')
                time.sleep(self.__timeout)
            except ConnectionResetError as e:
                logger.error(e)
                if reset_count >= retry:
                    raise e
                reset_count += 1
                logger.info('Retry...')
                time.sleep(self.__timeout)

    def browser(self, url, func=None):
        """
        simulate browser
        :param url:
        :param func: function for extra operations with a WebDriver as the argument
        :return:
        """
        logger.info('Get from %s: %s', self.name, url)
        self.__chrome.get(url)
        if func is not None:
            func(self.__chrome)
        source = self.__chrome.page_source
        return source

    def _get_url(self, path, low_domain='', path_params=None, query_params=None) -> str:
        """
        get a full encoded url by join netloc and href
        """
        if path_params is not None:
            path = path.format(**path_params)
        query = parse.urlencode(query_params) if query_params is not None else ''
        if low_domain is not None and low_domain != '':
            low_domain = low_domain + '.'
        return parse.urlunsplit((self._scheme, low_domain + self.__domain, path, query, None))

    def __next_access(self, interval=0):
        """
        Wait for next available access
        :param interval: interval between two accesses
        :return:
        """
        if interval == 0:
            interval = self.__interval
        waiting = interval - time.time() + self.__last_access
        if waiting > 0:
            logger.info('Waiting for %.2fs', waiting)
            time.sleep(waiting)
        self.__last_access = time.time()
