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

base_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.132 Safari/537.36'
}


def do_request(req: Request, pause=0.0, timeout=10, retry=3):
    """
    do request
    :param req: an instance of request.Request
    :return: content of response
    """
    if pause > 0:
        time.sleep(pause)
    logger.info('%s from %s', req.method, req.full_url)
    if req.get_method().upper() == 'POST' and req.data is not None:
        logger.info('Query: ' + parse.unquote(req.data.decode('utf=8')))
    timeout_count = reset_count = no_response_count = refused_count = 0
    while True:
        try:
            with urlopen(req, timeout=timeout) as r:
                return r.read().decode('utf-8')
        except socket.timeout as e:
            logger.error('Timeout!')
            if timeout_count >= retry:
                raise e
            timeout_count += 1
            logger.info('Retry...')
            time.sleep(timeout)
        except error.HTTPError as e:
            logger.error(e)
            raise e
        except error.URLError as e:
            logger.error(e)
            if e.errno is not None:
                raise e
            if e.reason is not None:
                e = e.reason
                if isinstance(e, socket.gaierror):
                    raise e
                if isinstance(e, TimeoutError):
                    if no_response_count >= retry:
                        raise e
                    no_response_count += 1
                    logger.info('Retry...')
                    time.sleep(timeout)
                    continue
                if isinstance(e, ConnectionRefusedError):
                    if refused_count >= retry:
                        raise e
                    refused_count += 1
                    logger.info('Retry...')
                    time.sleep(timeout)
                    continue
            logger.error('Unknown error')
            raise e
        except ConnectionResetError as e:
            logger.error(e)
            if reset_count >= retry:
                raise e
            reset_count += 1
            logger.info('Retry...')
            time.sleep(timeout)


def pre_download(url, pause=0.0, timeout=30, retry=3):
    """
    Do Pre-request a download url
    Get info of response, Content-Length or file size mainly.
    :return: (code, msg, args). Optional code and msg: (200, 'OK')/(1, 'Unknown Content Length')/(408, 'Timeout')
            'args', a dict of info will be returned if code is 200: size(B)
    """
    if pause > 0:
        time.sleep(pause)
    req = Request(quote_url(url), headers=base_headers, method='GET')
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


def get_soup(req: Request, pause=0.0, timeout=10) -> BeautifulSoup:
    """
    Request and return a soup of the page
    """
    return BeautifulSoup(do_request(req, pause, timeout), 'html.parser')


options = webdriver.ChromeOptions()
options.headless = False


def browser(url, func=None):
    """
    simulate browser
    :param url:
    :param func: function for extra operations with a WebDriver as the argument
    :return:
    """
    logger.info('Get from %s', url)
    chrome = webdriver.Chrome(options=options, executable_path='chromedriver 81.0.4044.138.exe')
    chrome.get(url)
    if func is not None:
        func(chrome)
    source = chrome.page_source
    chrome.close()
    return source
