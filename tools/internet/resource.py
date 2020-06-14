""" Search and handle resources

Priority of the site is decided by the order the subclass is written.

@Author Kingen
@Date 2020/4/25
"""
import abc
import os
import re
import socket
from urllib import parse, error
from urllib.request import Request

from bs4 import BeautifulSoup

from tools.video import Subtype
from . import logger
from .spider import BaseSite


def _get_possible_titles(subject) -> (str, set):
    """
    get titles that may match the subject
    :return (set of keys to search, set of possible matches)
    """
    if subject['subtype'] == Subtype.movie:
        matches = {subject['title']}
        for x in subject['aka']:
            alia = re.sub(r'\(.*\)', '', x)
            matches.add(alia)
            matches.add(x)
        matches.add(subject['original_title'])
        return subject['title'], matches

    current_season = subject['current_season'] if subject['current_season'] is not None else 1
    season_str = '第%s季' % num2chinese(current_season)
    base_title = subject['title'].replace(season_str, '').strip()
    matches = {subject['title']}
    for x in subject['aka']:
        alia = re.sub(r'\(.*\)', '', x)
        matches.add(alia)
        matches.add(x)
    if current_season == 1:
        matches.add(base_title)
    matches.update({
        base_title + season_str,
        base_title + ' ' + season_str,
        '%s[%s]' % (base_title, season_str),
        '%s%d' % (base_title, current_season)
    })
    matches.update(get_exact_title(subject))
    return base_title, matches


class VideoSearch(BaseSite):

    @abc.abstractmethod
    def __init__(self, name, domain, interval=0, priority=10, scheme='https', strict=False, use_browser=False) -> None:
        super().__init__(name, domain, scheme=scheme, interval=interval)
        self.__priority = priority
        self.__strict = strict
        self.__use_browser = use_browser

    @property
    def strict(self):
        return self.__strict

    @property
    def priority(self):
        # 1 with highest priority, default 10
        return self.__priority

    def search(self, subject):
        logger.info('Searching: %s, for: %s', self.name, subject['title'])
        keys, matches = _get_possible_titles(subject)
        resources = []
        for key in keys:
            try:
                for r in self._find_resources(key, subtype=subject['subtype']):
                    resources.append((r['name'], self._get_url(r['href'])))
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue
        return resources

    def collect(self, subject):
        """
        There are steps to search resources:
        1. Extract searching key: title commonly, removing season suffix if it's tv,
            or combined title for exact match
        2. Request: do searching request with the key
        3. Filter resources: comparing pre-handled names of resources with the key, same subtype
        4. Get urls: access to pages of resources to get specific urls
        :return: {url: remark, ...}
        """
        logger.info('Collecting: %s, for: %s', self.name, subject['title'])
        key, matches = _get_possible_titles(subject)
        exact_resources, urls = [], {}
        resources = self._find_resources(key, subtype=subject['subtype'])
        for r in resources:
            if r['href'].startswith('//'):
                r['href'] = self._scheme + ':' + r['href']
            elif r['href'].startswith('/'):
                r['href'] = self._get_url(r['href'])
            elif r['href'].startswith(self._scheme):
                pass
            else:
                raise error.URLError('Unknown href: %s' % r['href'])
        if len(resources) == 0:
            return urls

        # filter resources, keeping those matches key exactly or most similarly
        for resource in resources:
            names = self._parse_resource_names(resource['name'], subject['subtype'])
            if len(matches & names) > 0:
                logger.info('Chosen resource: %s, %s', resource['name'], resource['href'])
                exact_resources.append(resource)
            else:
                logger.info('Excluded resource: %s, %s', resource['name'], resource['href'])

        # get download urls from the resources
        for resource in exact_resources:
            if self.__use_browser:
                soup = self.get_browser_soup(resource['href'])
            else:
                soup = self.get_soup(resource['href'])
            links = self._find_downs(soup)
            if len(links) > 0:
                urls.update(links)
            else:
                logger.info('No links resource: %s', resource['name'])
        return urls

    def _is_subtype(self, subtype: Subtype, key, movie_keys, tv_keys, unknown_keys):
        if key in movie_keys:
            return subtype == Subtype.movie
        if key in tv_keys:
            return subtype == Subtype.tv
        if key in unknown_keys:
            return False
        raise ValueError('Unknown key of subtype: %s, site: %s' % (key, self.name))

    @staticmethod
    def _parse_resource_names(name: str, subtype: Subtype) -> set:
        invalid_str = ['国语', '中字', '高清', 'HD', 'BD', '1280', 'DVD', '《', '》', '720p', '[', ']',
                       '1024', '576', '*', '中英字幕', '中英双字', '无水']
        for s in invalid_str:
            name = name.replace(s, '')
        # name = re.sub(r'\[.*\]', '', name)
        names = {name}
        if subtype == Subtype.movie:
            names.update(set([n.strip().replace('  ', '') for n in name.split('/')]))
        else:
            season = re.search(r'第.{1,2}季', name)
            if season:
                season_str = season[0]
                name = name.replace(season_str, '')
            else:
                season_str = ''
            names.update(set([n.strip() + season_str for n in name.split('/')]))
        match = re.search(r'《(.*)》', name)
        if match is not None:
            names.add(match.group(1))
        return names

    @abc.abstractmethod
    def _find_resources(self, key: str, subtype: Subtype) -> list:
        """
        Search resources by key and filtering by subtype is required.
        :return: [{'name': resource_name, 'href': href},...]
        """
        pass

    @abc.abstractmethod
    def _find_downs(self, soup: BeautifulSoup) -> dict:
        """
        get useful urls on the page which href links to.
        :return: {down_url: remark, ...}, remark probably contain password if url is from pan.baidu.com
        """
        pass


class VideoSearch80s(VideoSearch):
    """
    Links distribution: mostly http, few ed2k/magnet
    """

    def __init__(self) -> None:
        super().__init__('80s', 'y80s.com', priority=1, scheme='http', interval=10)

    def _find_resources(self, key: str, subtype) -> list:
        form_data = parse.urlencode({'keyword': key}).encode(encoding='utf-8')
        req = Request(self._get_url('/search', 'm'), data=form_data, method='POST')
        soup = self.get_soup(req)
        resources = []
        for mov_a in soup.find('div', class_='list-group').find_all('a', class_='list-group-item'):
            href: str = mov_a['href']
            if self._is_subtype(subtype, href.rstrip('/').split('/')[-2], ('movie',), ('ju', 'zy'),
                                ('dm', 'mv', 'video', 'course', 'trailer')):
                small = mov_a.find('small')
                resources.append({
                    'name': str(small.previous_sibling).strip(),
                    'href': 'http:%s' % href,
                    'year': int(small.get_text())
                })
        return resources

    def _find_downs(self, soup: BeautifulSoup):
        links = {}
        for tr in soup.find('table').find_all('tr'):
            down_a = tr.td.a
            links[down_a['href']] = down_a.get_text().strip()
        return links

    def _get_url(self, path, low_domain='m', path_params=None, query_params=None) -> str:
        return super()._get_url(path, low_domain, path_params, query_params)


class VideoSearchXl720(VideoSearch):
    """
    Links distribution: mainly ed2k/ftp, few magnet/http/pan
    """

    def __init__(self) -> None:
        super().__init__('Xl720', 'xl720.com', priority=2)

    def _find_resources(self, key: str, subtype: Subtype) -> list:
        soup = self.get_soup(self._get_url('/', query_params={'s': key}))
        resources = []
        for div in soup.find_all('div', class_='post clearfix'):
            mov_a = div.find('h3').find('a', rel='bookmark')
            type_key = os.path.basename(div.find('div', class_='entry-meta').find('a', rel='category tag')['href'])
            if self._is_subtype(
                    subtype, type_key, ('dongzuopian', 'fanzuipian', 'kehuanpian', 'xijupian', 'aiqingpian', 'xuanyipian', 'kongbupian',
                                        'zainanpian', 'zhanzhengpian', 'maoxian', 'jingsong', 'qihuan', 'juqingpian'),
                    ('daluju', 'gangtaiju', 'rihanju', 'oumeiju'),
                    ('donghuapian', 'jilupian')) and mov_a.find('em'):
                resources.append({
                    'name': mov_a['title'],
                    'href': mov_a['href']
                })
        return resources

    def _find_downs(self, soup: BeautifulSoup) -> dict:
        links = {}
        for div in soup.find_all('div', id=['zdownload', 'ztxt']):
            down_a = div.find('a', rel='nofollow')
            links[down_a['href']] = down_a['title']
        return links

    def _get_url(self, path, low_domain='', path_params=None, query_params=None):
        return super()._get_url(path, low_domain, path_params, query_params).replace('%20', '+')


class VideoSearchXLC(VideoSearch):
    """
    Links distribution: evenly torrent/ftp/magnet/pan/http/ed2k
    """

    def __init__(self) -> None:
        super().__init__('XLC', 'xunleicang.in', priority=3)

    def _find_resources(self, key: str, subtype: Subtype):
        form_data = parse.urlencode({'wd': key}).encode(encoding='utf-8')
        soup = self.get_soup(Request(self._get_url('/vod-search'), data=form_data, method='POST'))
        resources = []
        for mov in soup.find_all('div', {'class': 'movList4'}):
            mov_a = mov.ul.li.h3.a
            if self._is_subtype(subtype, mov.ul.li.ul.find_all('li')[1].get_text().split(':')[1].strip(),
                                ('动作片', '喜剧片', '爱情片', '科幻片', '恐怖片', '剧情片', '战争片', '其它片',
                                 '4K', '1080P', '3D电影', '国语配音'),
                                ('大陆剧', '港台剧', '欧美剧', '日韩剧', '新马泰', '综艺片'),
                                ('动画片',)):
                resources.append({
                    'name': mov_a.get_text().strip(),
                    'href': mov_a['href']
                })
        return resources

    def _find_downs(self, soup: BeautifulSoup):
        links = {}
        for down_ul in soup.find('div', class_='ui-limit').find_all('ul', {'class': 'down-list'}):
            for down_li in down_ul.find_all('li', class_='item'):
                down_a = down_li.div.span.a
                links[down_a['href']] = down_a.get_text().strip()
        return links


class VideoSearchAxj(VideoSearch):
    """
    Links distribution: mainly magnet/pan, few ed2k
    """

    def __init__(self) -> None:
        super().__init__('Axj', 'aixiaoju.com', interval=15, use_browser=True)

    def _find_resources(self, key: str, subtype: Subtype) -> list:
        url = self._get_url('/app-thread-run', query_params={'app': 'search', 'keywords': key, 'orderby': 'lastpost_time'})
        soup = self.get_soup(url)
        resources = []
        for dl in soup.find('div', class_='search_content').find_all('dl'):
            mov_a = dl.find('dt').find('a', class_='tlink')
            resources.append({
                'name': mov_a.get_text().strip(),
                'href': mov_a['href']
            })
        return resources

    def _find_downs(self, soup: BeautifulSoup) -> dict:
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
        super().__init__('Zhandi', 'zhandi.cc')

    def _find_resources(self, key: str, subtype: Subtype) -> list:
        form_data = parse.urlencode({'wd': key}).encode(encoding='utf-8')
        req = Request(self._get_url('/index.php', query_params={'s': 'vod-search'}), data=form_data, method='POST')
        soup = self.get_soup(req)
        resources = []
        for mov in soup.find('ul', {'id': 'contents'}).find_all('li'):
            mov_a = mov.h5.a
            if self._is_subtype(subtype, mov_a['href'].strip('/').split('/')[-2],
                                ('Dz', 'Xj', 'Aq', 'Kh', 'Kb', 'War', 'Jq'),
                                ('Gc', 'Gt', 'Om', 'Rh', 'Hw', 'Zy'),
                                ('Dm', 'Jl', 'OSK', 'Redian')):
                resources.append({
                    'name': mov_a.get_text().strip(),
                    'href': mov_a['href']
                })
        return resources

    def _find_downs(self, soup: BeautifulSoup):
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
        # todo filter by subtype
        import warnings
        warnings.warn('Not filtered by subtype', DeprecationWarning)
        super().__init__('Hhyyk', 'hhyyk.com', scheme='http')

    def _find_resources(self, key: str, subtype: Subtype) -> list:
        soup = self.get_soup(self._get_url('/search', query_params={'keyword': key}))
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

    def _find_downs(self, soup: BeautifulSoup):
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
        # todo filter by subtype
        import warnings
        warnings.warn('Not filtered by subtype', DeprecationWarning)
        super().__init__('MP4', 'domp4.com', use_browser=True)

    def _find_resources(self, key: str, subtype: Subtype) -> list:
        soup = self.get_soup(self._get_url('/search/%s.html' % parse.quote(key)))
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

    def _find_downs(self, soup: BeautifulSoup) -> dict:
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
        super().__init__('Ssk', 'sskzmz.com')

    def _find_resources(self, key: str, subtype: Subtype) -> list:
        soup = self.get_soup(self._get_url('/index/search', {'tab': key}))
        resources = []
        for mov in soup.find('div', {'class': 'row movie'}).find_all('div'):
            mov_a = mov.a
            resources.append({
                'name': mov_a.get_text().strip(),
                'href': mov_a['href']
            })
        return resources

    def _find_downs(self, soup: BeautifulSoup):
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


def get_exact_title(subject) -> set:
    if subject['title'] == subject['original_title']:
        combined_title = subject['title']
    else:
        combined_title = '%s %s' % (subject['title'], subject['original_title'])
    matches = {'%s (%s)' % (combined_title, subject['year'])}
    if subject['subtype'] == Subtype.tv and subject['current_season'] is not None:
        matches.add('%s Season %d (%s)' % (combined_title, subject['current_season'], subject['year']))
    return matches
