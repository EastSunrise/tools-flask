""" Search and handle resources

Priority of the site is decided by the order the subclass is written.

@Author Kingen
@Date 2020/4/25
"""
import abc
import re
import socket
import time
from urllib import parse, error, request
from urllib.request import Request

import bs4

from . import logger
from .spider import get_soup, browser


class VideoSearch(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def __init__(self, name, netloc, priority=10, timeout=20, scheme='https', headers=None) -> None:
        self.__name = name
        self._scheme = scheme
        self._netloc = netloc
        self.__priority = priority
        self._headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/80.0.3987.132 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;'
                      'q=0.8,application/signed-exchange;v=b3;q=0.9',
            'Accept-Lanaguage': 'zh-CN,zh;q=0.9,zh-TW;q=0.8',
        }
        if headers is not None:
            self._headers.update(headers)
        self._timeout = timeout
        self._last_access = 0.0

    @property
    def priority(self):
        # 1 with highest priority, default 10
        return self.__priority

    @property
    def name(self):
        return self.__name

    @property
    def home(self):
        return self._scheme + '://' + self._netloc + '/'

    def search(self, subject):
        logger.info('Searching: %s, for: %s', self.name, subject['title'])
        keys, matches = self._get_possible_titles(subject)
        resources = []
        for key in keys:
            try:
                self._next_access(15)
                soup = get_soup(self._search_req(key, subtype=subject['subtype']), timeout=self._timeout)
                for r in self._find_resources(soup, subtype=subject['subtype']):
                    resources.append((r['name'], self._get_full_url(r['href'])))
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue
        return resources

    def collect(self, subject, manual=False):
        """
        There are four steps to search resources:
        1. search resources by a specific key
        2. filter resources by comparing names of resources with the key
        3. access to pages of resources to get specific urls
        :return: {url: remark, ...}
        """
        logger.info('Collecting: %s, for: %s', self.name, subject['title'])
        keys, matches = self._get_possible_titles(subject)
        exact_resources, urls = [], {}
        for key in keys:
            try:
                self._next_access(15)
                soup = get_soup(self._search_req(key, subtype=subject['subtype']), timeout=self._timeout)
                resources = self._find_resources(soup, subtype=subject['subtype'])
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue
            if len(resources) == 0:
                continue

            # filter resources, keeping those matches key exactly or most similarly
            if manual:
                for x in resources:
                    while True:
                        c = input('%s, [y/n]: ' % x['name'])
                        if c == 'y':
                            exact_resources.append(x)
                            break
                        elif c == 'n':
                            break
            else:
                for resource in resources:
                    names = self._parse_resource_name(resource['name'], subject['subtype'])
                    if len(matches & names) > 0:
                        exact_resources.append(resource)
                    else:
                        logger.info('Excluded resource: %s, %s', resource['name'], self._get_full_url(resource['href']))

            # get download urls from the resources
            for resource in exact_resources:
                try:
                    links = self._parse_read_page(resource['href'], key, subject['subtype'])
                except socket.timeout:
                    continue
                except ConnectionResetError:
                    continue
                if len(links) > 0:
                    urls.update(links)
                else:
                    logger.info('No links resource: %s', resource['name'])
        return urls

    def _get_possible_titles(self, subject):
        """
        get titles that may match the subject
        :return (set of keys to search, set of possible matches)
        """
        if subject['subtype'] == 'movie':
            keys = [subject['title']]
            matches = {subject['title']}
            for x in subject['aka']:
                alia = re.sub(r'\(.*\)', '', x)
                matches.add(alia)
                matches.add(x)
            matches.add(subject['original_title'])
            return keys, matches

        current_season = subject['current_season'] if subject['current_season'] is not None else 1
        season_str = '第%s季' % num2chinese(current_season)
        keys = [subject['title'].replace(season_str, '').strip()]
        matches = {subject['title']}
        for x in subject['aka']:
            alia = re.sub(r'\(.*\)', '', x)
            # key = alia.replace(season_str, '').strip()
            # if key not in keys:
            #     keys.append(key)
            matches.add(alia)
            matches.add(x)
        for key in keys:
            if current_season == 1:
                matches.add(key)
            matches.update({key + season_str, key + ' ' + season_str, '%s[%s]' % (key, season_str), '%s%d' % (key, current_season)})
        return keys, matches

    @abc.abstractmethod
    def _search_req(self, key, **kwargs) -> Request:
        """
        :return: search request
        """
        pass

    @abc.abstractmethod
    def _find_resources(self, soup: bs4.BeautifulSoup, subtype) -> list:
        """
        Search resources by key and filtering by subtype is required.
        :return: [{'name': resource_name, 'href': href},...]
        """
        pass

    def _parse_resource_name(self, name, subtype):
        invalid_str = ['国语', '中字', '高清', 'HD', 'BD', '1280', 'DVD', '《', '》', '720p', '[', ']',
                       '1024', '576', '*', '中英字幕', '中英双字', '无水']
        for s in invalid_str:
            name = name.replace(s, '')
        # name = re.sub(r'\[.*\]', '', name)
        if subtype == 'movie':
            return set([n.strip().replace('  ', '') for n in name.split('/')])
        else:
            season = re.search(r'第.{1,2}季', name)
            if season:
                season_str = season[0]
                name = name.replace(season_str, '')
            else:
                season_str = ''
            return set([n.strip() + season_str for n in name.split('/')])

    def _resource_req(self, href, referer) -> Request:
        read_req = request.Request(href, headers=self._headers, method='GET')
        read_req.add_header('Referer', referer)
        return read_req

    def _parse_read_page(self, href, key, subtype):
        read_soup = get_soup(self._resource_req(self._get_full_url(href), self._search_req(key, subtype=subtype).full_url))
        return self._find_downs(read_soup)

    @abc.abstractmethod
    def _find_downs(self, soup) -> dict:
        """
        get useful urls on the page which href links to.
        :return: {down_url: remark, ...}, remark probably contain password if url is from pan.baidu.com
        """
        pass

    def _get_full_url(self, href: str, **query_params):
        """
        get a full url by join scheme, netloc and href
        """
        if href.startswith('http'):
            href = parse.splithost(parse.splittype(href)[1])[1]
        if href.startswith('/'):
            return '%s://%s%s' % (self._scheme, self._netloc, href) + \
                   ('' if not query_params else ('?' + parse.urlencode(query_params)))
        raise error.URLError('Unknown href: %s' % href)

    def _next_access(self, interval=0):
        """
        Wait for next available access
        :param interval: interval between two accesses
        :return:
        """
        waiting = interval - time.time() + self._last_access
        if waiting > 0:
            logger.info('Waiting for %.2fs', waiting)
            time.sleep(waiting)
        self._last_access = time.time()


class VideoSearch80s(VideoSearch):
    """
    Links distribution: mostly http, few ed2k/magnet
    """

    def __init__(self) -> None:
        super().__init__('80s', 'www.y80s.com', priority=1, scheme='http', timeout=20, headers={
            'Host': 'www.y80s.com',
        })

    def _search_req(self, key, **kwargs) -> Request:
        form_data = parse.urlencode({'search_typeid': 1, 'skey': key, 'Input': '搜索'}).encode(encoding='utf-8')
        search_req = request.Request(self._get_full_url('/movie/search'), data=form_data, headers=self._headers, method='POST')
        search_req.add_header('Origin', 'http://www.y80s.com')
        search_req.add_header('Referer', 'http://www.y80s.com/')
        return search_req

    def _find_resources(self, soup, subtype) -> list:
        resources = []
        if soup.find('div', class_='nomoviesinfo'):
            return []
        ul = soup.find('ul', {'class': 'me1 clearfix'})
        for mov in ul.find_all('li'):
            mov_a = mov.h3.a
            href = mov_a['href']
            t = 'movie' if 'movie' in href else ('tv' if ('ju' in href or 'zy' in href) else 'unknown')
            if subtype == t:
                resources.append({
                    'name': mov_a.get_text().strip(),
                    'href': mov_a['href']
                })
        return resources

    def _find_downs(self, soup):
        links = {}
        for span in soup.find_all('span', {'class': 'dlname nm'}):
            down_a = span.span.a
            links[down_a['href']] = down_a.get_text().strip()
        return links

    def _next_access(self, interval=0):
        super()._next_access(10)


class VideoSearchXl720(VideoSearch):
    """
    Links distribution: mainly ed2k/ftp, few magnet/http/pan
    """

    def __init__(self) -> None:
        super().__init__('Xl720', 'www.xl720.com', priority=2, headers={
            'authority': 'www.xl720.com',
            'scheme': 'https'
        })

    def _get_possible_titles(self, subject):
        if subject['title'] == subject['original_title']:
            combined_title = '%s (%s)' % (subject['title'], subject['year'])
        else:
            combined_title = '%s %s (%s)' % (subject['title'], subject['original_title'], subject['year'])
        return {combined_title}, {combined_title}

    def _search_req(self, key, **kwargs) -> Request:
        search_req = request.Request(self._get_full_url('/', s=key), headers=self._headers, method='GET')
        search_req.add_header('Referer', self.home)
        return search_req

    def _find_resources(self, soup: bs4.BeautifulSoup, subtype) -> list:
        resources = []
        for div in soup.find_all('div', class_='post clearfix'):
            mov_a = div.find('h3').find('a', rel='bookmark')
            resources.append({
                'name': mov_a['title'],
                'href': self._get_full_url(mov_a['href'])
            })
        return resources

    def _find_downs(self, soup) -> dict:
        links = {}
        for div in soup.find_all('div', id=['zdownload', 'ztxt']):
            down_a = div.find('a', rel='nofollow')
            links[down_a['href']] = down_a['title']
        return links

    def _get_full_url(self, href: str, **query_params):
        return super()._get_full_url(href, **query_params).replace('%20', '+')


class VideoSearchXLC(VideoSearch):
    """
    Links distribution: evenly torrent/ftp/magnet/pan/http/ed2k
    """

    def __init__(self) -> None:
        super().__init__('XLC', 'www.xunleicang.in', priority=3, timeout=20, headers={
            'authority': 'www.xunleicang.in',
            'scheme': 'https'
        })

    def _search_req(self, key, **kwargs) -> Request:
        form_data = parse.urlencode({'wd': key}).encode(encoding='utf-8')
        search_req = request.Request(self._get_full_url('/vod-search'), data=form_data, headers=self._headers, method='POST')
        search_req.add_header('Origin', self.home)
        search_req.add_header('Referer', self.home)
        return search_req

    def _find_resources(self, soup, subtype):
        resources = []
        for mov in soup.find_all('div', {'class': 'movList4'}):
            mov_a = mov.ul.li.h3.a
            resources.append({
                'name': mov_a.get_text().strip(),
                'href': mov_a['href']
            })
        return resources

    def _find_downs(self, soup):
        links = {}
        for down_ul in soup.find_all('ul', {'class': 'down-list'}):
            down_a = down_ul.li.div.span.a
            links[down_a['href']] = down_a.get_text().strip()
        return links


class VideoSearchAxj(VideoSearch):
    """
    Links distribution: mainly magnet/pan, few ed2k
    """

    def __init__(self) -> None:
        super().__init__('Axj', 'www.aixiaoju.com', headers={
            'authority': 'www.aixiaoju.com',
            'scheme': 'https'
        })

    def _search_req(self, key, **kwargs) -> Request:
        fid = '26' if kwargs['subtype'] == 'movie' else '27'
        search_req = request.Request(self._get_full_url('/app-thread-run', fid=fid, app='search', keywords=key, orderby='lastpost_time'),
                                     headers=self._headers, method='GET')
        search_req.add_header('Referer', self.home)
        return search_req

    def _next_access(self, interval=0):
        super()._next_access(15)

    def _find_resources(self, soup: bs4.BeautifulSoup, subtype) -> list:
        resources = []
        for dl in soup.find('div', class_='search_content').find_all('dl'):
            mov_a = dl.find('dt').find('a', class_='tlink')
            resources.append({
                'name': mov_a.get_text().strip(),
                'href': mov_a['href']
            })
        return resources

    def _parse_read_page(self, href, key, subtype):
        soup = bs4.BeautifulSoup(browser(self._get_full_url(href)), 'html.parser')
        return self._find_downs(soup)

    def _find_downs(self, soup) -> dict:
        links = {}
        for a in soup.find('div', class_='editor_content').find_all('a'):
            remark = a.get_text().strip()
            if a['href'].startswith('https://pan.baidu.com'):
                remark = str(a.next_sibling).strip()
            links[a['href']] = remark
        return links


class VideoSearchZhandi(VideoSearch):
    """
    Links distribution: mostly ftp, partly ed2k, few magnet/http
    """

    def __init__(self) -> None:
        super().__init__('Zhandi', 'www.zhandi.cc', timeout=20, headers={
            'Host': 'www.zhandi.cc'
        })

    def _search_req(self, key, **kwargs) -> Request:
        form_data = parse.urlencode({'wd': key}).encode(encoding='utf-8')
        search_req = request.Request(self._get_full_url('/index.php', s='vod-search'),
                                     data=form_data, headers=self._headers, method='POST')
        search_req.add_header('Origin', 'https://www.zhandi.cc')
        search_req.add_header('Referer', 'https://www.zhandi.cc/')
        return search_req

    def _find_resources(self, soup, subtype) -> list:
        resources = []
        for mov in soup.find('ul', {'id': 'contents'}).find_all('li'):
            mov_a = mov.h5.a
            if any(t in mov_a['href'] for t in ['Dz', 'Xj', 'Aq', 'Kh', 'Kb', 'War', 'Jq']):
                t = 'movie'
            elif any(t in mov_a['href'] for t in ['Gc', 'Gt', 'Om', 'Rh', 'Hw', 'Zy']):
                t = 'tv'
            else:
                t = 'unknown'
            if subtype == t:
                resources.append({
                    'name': mov_a.get_text().strip(),
                    'href': mov_a['href']
                })
        return resources

    def _find_downs(self, soup):
        links = {}
        down_ul = soup.find('ul', id='downul')
        if down_ul is None:
            return {}
        for down_li in down_ul.find_all('li'):
            down_a = down_li.p.a
            links[down_a['href']] = down_a.get_text().strip()
        return links


class VideoSearchHhyyk(VideoSearch):
    """
    Links distribution: mainly ftp/pan/magnet, few torrent/http
    """

    def __init__(self) -> None:
        super().__init__('Hhyyk', 'www.hhyyk.com', timeout=20, scheme='http', headers={
            'Host': 'www.hhyyk.com'
        })

    def _search_req(self, key, **kwargs) -> Request:
        search_req = request.Request(self._get_full_url('/search', keyword=key), headers=self._headers, method='GET')
        search_req.add_header('Referer', 'http://www.hhyyk.com/')
        search_req.add_header('Host', self._netloc)
        return search_req

    def _find_resources(self, soup, subtype) -> list:
        resources = []
        tbody = soup.find('tbody')
        if tbody is not None:
            for tr in tbody.find_all('tr')[1:]:
                mov_a = tr.td.a
                resources.append({
                    'name': mov_a.get_text().strip(),
                    'href': mov_a['href']
                })
        return resources

    def _parse_resource_name(self, name, subtype):
        match = re.search(r'《.*》', name)
        if match:
            name = match[0].strip('《》')
        return super()._parse_resource_name(name, subtype)

    def _find_downs(self, soup):
        links = {}
        for p in soup.find_all('p', class_='detail-text-p'):
            down_a = p.span.a
            links[down_a['href']] = down_a.get_text().strip()
        return links


class VideoSearchMP4(VideoSearch):
    """
    Links distribution: mainly ftp/ed2k/magnet, few http
    """

    def __init__(self) -> None:
        super().__init__('MP4', 'www.domp4.com')

    def _search_req(self, key, **kwargs) -> Request:
        search_req = request.Request(self._get_full_url('/search/%s.html' % parse.quote(key)),
                                     headers=self._headers, method='GET')
        search_req.add_header('Referer', self.home)
        return search_req

    def _find_resources(self, soup: bs4.BeautifulSoup, subtype) -> list:
        resources = []
        for li in soup.find('div', id='list_all').find('ul').find_all('li'):
            h2 = li.find('h2')
            if h2:
                a = h2.find('a')
                resources.append({
                    'name': a.get_text().strip(),
                    'href': a['href']
                })
        return resources

    def _parse_resource_name(self, name, subtype):
        match = re.search(r'《.*》', name)
        if match:
            name = match[0].strip('《》')
        return super()._parse_resource_name(name, subtype)

    def _parse_read_page(self, href, key, subtype):
        soup = bs4.BeautifulSoup(browser(self._get_full_url(href)), 'html.parser')
        return self._find_downs(soup)

    def _find_downs(self, soup) -> dict:
        links = {}
        for div in soup.find_all('div', class_='article-related download_url'):
            for li in div.find('ul').find_all('li'):
                a = li.find('div', class_='url-left').find('a')
                links[a['href']] = a['title']
        return links


class SrtSearchSsk(VideoSearch):
    """
    Search srt resources from <https://sskzmz.com/>.
    """

    def __init__(self) -> None:
        import warnings
        warnings.warn('Not filter by subtype', DeprecationWarning)
        super().__init__('Ssk', 'sskzmz.com', timeout=20, headers={
            'Host': 'sskzmz.com'
        })

    def _search_req(self, key, **kwargs) -> Request:
        search_req = request.Request(self._get_full_url('/index/search', tab=key), headers=self._headers, method='GET')
        search_req.add_header('Referer', 'https://sskzmz.com/')
        return search_req

    def _find_resources(self, soup, subtype) -> list:
        resources = []
        for mov in soup.find('div', {'class': 'row movie'}).find_all('div'):
            mov_a = mov.a
            resources.append({
                'name': mov_a.get_text().strip(),
                'href': mov_a['href']
            })
        return resources

    def _find_downs(self, soup):
        links = {}
        for tr in soup.find('tbody').find_all('tr')[1:]:
            tds = tr.find_all('td')
            links[tds[0].get_text().strip()] = tds[3].a['href']
        return links


CHINESE_NUMERALS = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']


def num2chinese(num: int) -> str:
    """
    transfer Arabic numerals to Chinese numerals
    """
    if num <= 0 or num > 20:
        raise ValueError
    if num <= 10:
        return CHINESE_NUMERALS[num]
    if num == 20:
        return '二十'
    return '十' + CHINESE_NUMERALS[num - 10]
