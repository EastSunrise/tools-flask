""" Video views

@Author Kingen
@Date 2020/5/13
"""
import base64
import logging
import math
import os
import re
from itertools import groupby
from sqlite3 import connect, PARSE_DECLTYPES, Row
from urllib import parse

import pythoncom
from pymediainfo import MediaInfo

from tools.internet.downloader import IDM, Thunder
from tools.internet.resource import VideoSearch80s, VideoSearchXl720, VideoSearchXLC, VideoSearchZhandi, VideoSearchAxj, VideoSearchHhyyk, VideoSearchMP4
from tools.internet.spider import pre_download
from tools.utils import file
from tools.utils.common import cmp_strings

logger = logging.getLogger(__name__)

VIDEO_SUFFIXES = ('.avi', '.rmvb', '.mp4', '.mkv')
standard_kbps = 2500  # kb/s


class VideoManager:
    CHINESE = ['汉语普通话', '普通话', '粤语', '闽南语', '河南方言', '贵州方言', '贵州独山话']
    JUNK_SITES = ['yutou.tv', '80s.la', '80s.im', '2tu.cc', 'bofang.cc:', 'dl.y80s.net', '80s.bz', 'xubo.cc']
    ALL_SITES = [VideoSearch80s(), VideoSearchXl720(), VideoSearchXLC(),
                 VideoSearchZhandi(), VideoSearchAxj(), VideoSearchHhyyk(), VideoSearchMP4()]

    def __init__(self, cdn, db_path, idm_path='IDM.exe') -> None:
        self.cdn = cdn
        self.__db = db_path
        self.__con = None
        self.__temp_dir = os.path.join(self.cdn, 'Temp')
        self.__idm = IDM(idm_path)

    @property
    def cdn(self):
        return self.__cdn

    @cdn.setter
    def cdn(self, cdn):
        if not os.path.isdir(cdn):
            cdn = './'
        self.__cdn = cdn

    @property
    def connection(self):
        if self.__con is None:
            self.__con = connect(self.__db, detect_types=PARSE_DECLTYPES)
            self.__con.row_factory = Row
            self.__con.set_trace_callback(lambda x: logger.info('Execute: %s', x))
        return self.__con

    def close_connection(self):
        if self.__con is not None:
            self.__con.close()

    def search_resources(self, subject_id: int):
        """
        :return: sites and resources found
        """
        subject = self.get_movie(id=subject_id)
        if subject is None:
            logger.info('No subject found with id: %d', subject_id)
            return {}
        resources = {}
        for site in sorted(self.ALL_SITES, key=lambda x: x.priority):
            resources[site.name] = site.search(subject)
        return resources

    def collect_resources(self, subject_id: int):
        """
        Search and download resources for subject specified by id.
        :param subject_id:
        :return: archived
        """
        subject = self.get_movie(id=subject_id)
        if subject is None:
            logger.info('No subject found with id: %d', subject_id)
            return 'none'
        return self.__collect_subject(subject, self.ALL_SITES)

    def archive_temp(self, subject_id):
        """
        After finishing all IDM and Thunder tasks.
        :return: -2: IOError, -1: no qualified file, 1: archived
        """
        paths = [os.path.join(self.__temp_dir, x) for x in os.listdir(self.__temp_dir) if x.startswith(str(subject_id))]
        subject = self.get_movie(id=subject_id)
        weights = {}
        for path in paths:
            try:
                weights[path] = weight_video_file(path, subject['durations'])
            except IOError as e:
                logger.error(e)
                weights[path] = -1
        chosen = max(weights, key=lambda x: weights[x])
        if weights[chosen] < 0:
            logger.warning('No qualified video file: %s', subject['title'])
            self.update_movie(subject_id, archived='none')
            return 'none'
        else:
            logger.info('Chosen file: %.2f, %s', weights[chosen], chosen)
            ext = os.path.splitext(chosen)[1]
            path, filename = self.__get_location(subject)
            dst = os.path.join(path, filename + ext)
            code = file.copy(chosen, dst)
            if code != 0:
                return -2
        for p in weights:
            file.del_to_recycle(p)
        self.update_movie(subject_id, archived='playable', location=dst)
        return 'playable'

    def __collect_subject(self, subject, sites):
        subject_id, title, subtype = subject['id'], subject['title'], subject['subtype']
        path, filename = self.__get_location(subject)
        archived = self.__archived(subject)
        logger.info('Collecting subject: %s, %s', title, subject['alt'])
        if archived:
            logger.info('File exists for the subject %s: %s', title, archived)
            self.update_movie(subject_id, archived='playable', location=archived)
            return 'playable'

        # movie
        if subtype == 'movie':
            links = {'http': {}, 'ed2k': {}, 'pan': {}, 'ftp': {}, 'magnet': {}, 'torrent': {}, 'unknown': {}}
            for site in sorted(sites, key=lambda x: x.priority):
                for url, remark in site.collect(subject).items():
                    p, u = classify_url(url)
                    if any([u.find(x) >= 0 for x in self.JUNK_SITES]):
                        continue
                    filename, ext, size = None, None, -1
                    if p == 'http':
                        filename = os.path.basename(u)
                        ext = os.path.splitext(filename)[1]
                        code, msg, args = pre_download(u)
                        if code == 200:
                            size = args['size']
                        else:
                            continue
                    elif p == 'ftp':
                        filename = os.path.basename(u)
                        ext = os.path.splitext(filename)[1]
                    elif p == 'ed2k':
                        filename = u.split('|')[2]
                        ext = os.path.splitext(filename)[1]
                        size = int(u.split('|')[3])
                    if weight_video(ext, subject['durations'], size) < 0:
                        continue
                    links[p][u] = (u, filename, ext)
            url_count = 0
            for u, filename, ext in links['http'].values():
                logger.info('Add IDM task of %s, downloading from %s to the temporary dir', title, u)
                self.__idm.add_task(u, self.__temp_dir, '%d_%s_http_%d_%s' % (subject_id, title, url_count, filename))
                url_count += 1
            pythoncom.CoInitialize()
            thunder = Thunder()
            for p in ['ed2k', 'ftp']:
                for u, filename, ext in links[p].values():
                    logger.info('Add Thunder task of %s, downloading from %s to the temporary dir', title, u)
                    thunder.add_task(u, '%d_%s_%s_%d_%s' % (subject_id, title, p, url_count, filename))
                    url_count += 1
            thunder.commit_tasks()
            pythoncom.CoUninitialize()

            if url_count == 0:
                logger.warning('No resources found for: %s', title)
                self.update_movie(subject_id, archived='none')
                return 'none'
            logger.info('Tasks added: %d for %s. Downloading...', url_count, title)
            self.update_movie(subject_id, archived='downloading')
            return 'downloading'
        else:
            episodes_count = subject['episodes_count']
            links = {'http': [], 'ed2k': [], 'pan': [], 'ftp': [], 'magnet': [], 'torrent': [], 'unknown': []}
            for site in sorted(sites, key=lambda x: x.priority):
                for url, remark in site.collect(subject).items():
                    p, u = classify_url(url)
                    if any([u.find(x) >= 0 for x in self.JUNK_SITES]):
                        continue
                    ext = None
                    if p == 'http':
                        ext = os.path.splitext(u)[1]
                    elif p == 'ftp':
                        ext = os.path.splitext(u)[1]
                    elif p == 'ed2k':
                        ext = os.path.splitext(u.split('|')[2])[1]
                    if weight_video(ext) < 0:
                        continue
                    links[p].append({'url': u})
            urls = self.__extract_tv_urls(links['http'], episodes_count)
            empties = [str(i + 1) for i, x in enumerate(urls) if x is None]
            if len(empties) > 0:
                logger.info('Not enough episodes for %s, total: %d, lacking: %s', subject['title'], episodes_count, ', '.join(empties))
                self.update_movie(subject_id, archived='none')
                return 'none'
            logger.info('Add IDM tasks of %s, %d episodes', title, episodes_count)
            path = os.path.join(path, filename)
            os.makedirs(path, exist_ok=True)
            episode = 'E%%0%dd%%s' % math.ceil(math.log10(episodes_count + 1))
            for i, url in enumerate(urls):
                self.__idm.add_task(url, path, episode % ((i + 1), os.path.splitext(url)[1]))
            logger.info('Tasks added: %d for %s. Downloading...', episodes_count, title)
            self.update_movie(subject_id, archived='idm')
            return 'idm'

    def __extract_tv_urls(self, http_resources, episodes_count):
        for r in http_resources:
            t, s = parse.splittype(r['url'])
            h, p = parse.splithost(s)
            h = '%s://%s' % (t, h)
            r['head'], r['path'] = h, p
        urls = [None] * (episodes_count + 1)
        # resource keys: url, head, path
        for length, rs_sort_len in groupby(sorted(http_resources, key=lambda x: len(x['path'])), key=lambda x: len(x['path'])):
            for head, rs_sort_head in groupby(sorted(rs_sort_len, key=lambda x: x['head']), key=lambda x: x['head']):
                rs_sorted = list(rs_sort_head)

                # path like: *{episodes_count}end.mp4
                if len(rs_sorted) == 1:
                    r0 = rs_sorted[0]
                    if os.path.splitext(r0['path'])[0].endswith('%dend' % episodes_count):
                        if pre_download(r0['url'])[0] == 200:
                            urls[episodes_count] = r0['url']
                    continue

                # extract pattern of similar urls
                commons, differences = cmp_strings([x['path'] for x in rs_sorted])
                for i, x in enumerate(commons[:-1]):
                    ed = re.search(r'\d+$', x)
                    if ed is not None:
                        commons[i] = x[:ed.start()]
                        for y in differences:
                            y[i] = x[ed.start():] + y[i]
                for i, x in enumerate(commons[1:]):
                    sd = re.search(r'^\d+', x)
                    if sd is not None:
                        commons[i] = x[sd.end():]
                        for y in differences:
                            y[i] = y[i] + x[:sd.end()]
                del_count = 0
                for i, x in enumerate(commons[1:-1]):
                    if x == '':
                        for y in differences:
                            y[i] = y[i] + x + y[i + 1]
                            del y[i + 1 - del_count]
                        del commons[i + 1 - del_count]
                        del_count += 1

                # exclude if number of differences is > 2 or differences aren't digit or the digit is over count if episodes.
                if any((not x[-1].isdigit() or int(x[-1]) > episodes_count) for x in differences):
                    continue
                if any((len(x) > 2 or not x[0].isdigit()) for x in differences):
                    continue

                gs = {}  # path_format: episodes_list
                # two parts of differences, first one as key to group, second one as episode
                if any(len(set(x)) > 1 for x in differences):
                    placeholder_count = 1
                    for first, episodes_grouped in groupby(sorted(differences, key=lambda x: x[0]), key=lambda x: x[0]):
                        pf = commons[0] + first + '%d'.join(commons[1:])
                        gs[pf] = gs.get(pf, []) + [x[-1] for x in episodes_grouped]
                else:  # all differences represent episode
                    placeholder_count = len(differences[0])
                    pf = '%d'.join(commons)
                    gs[pf] = gs.get(pf, []) + [x[0] for x in differences]
                for path_format, episodes in gs.items():
                    url_format = head + path_format
                    episodes_len = [len(x) for x in episodes]
                    min_len = min(episodes_len)
                    # fixed length
                    if min_len == max(episodes_len):
                        url_format = url_format.replace('%d', '%%0%dd' % min_len)
                    episodes_int = [int(x) for x in episodes]
                    start, end = min(episodes_int), max(episodes_int)

                    # compute bounds of episodes
                    code_s, msg, args = pre_download(url_format % tuple([1] * placeholder_count), pause=3)
                    if code_s == 200:
                        start = 1
                    else:
                        left = self.__compute_limit(2, start, url_format, placeholder_count, True)
                        if left > start:
                            continue
                        start = left
                    code_e, msg, args = pre_download(url_format % tuple([episodes_count] * placeholder_count), pause=3)
                    if code_e == 200:
                        end = episodes_count + 1
                    else:
                        left = self.__compute_limit(end, episodes_count - 1, url_format, placeholder_count, False)
                        if left <= end:
                            continue
                        end = left
                    for i in range(start, end):
                        urls[i] = url_format % tuple([i] * placeholder_count)
        return urls[1:]

    @staticmethod
    def __compute_limit(left, right, uf, phs, is_equal):
        while left <= right:
            m = (left + right) >> 1
            code, msg, args = pre_download(uf % tuple([m] * phs), pause=10)
            if code == 200 ^ is_equal:
                left = m + 1
            else:
                right = m - 1
        return left

    def __archived(self, subject):
        """
        :return: False if not archived, otherwise, filepath.
        """
        path, filename = self.__get_location(subject)
        filepath = os.path.join(path, filename)
        if subject['subtype'] == 'tv' and os.path.isdir(filepath):
            if len([x for x in os.listdir(filepath) if re.match(r'E\d+', x)]) == subject['episodes_count']:
                return filepath
        if subject['subtype'] == 'movie' and os.path.isdir(path):
            with os.scandir(path) as sp:
                for f in sp:
                    if f.is_file() and os.path.splitext(f.name)[0] == filename:
                        return f.path
        return False

    def __get_location(self, subject):
        """
        Get location for the subject
        :param subject: required properties: subtype, languages, year, title, original_title
        :return: (dir, name). The name returned doesn't include an extension.
        """
        subtype = 'Movies' if subject['subtype'] == 'movie' else 'TV' if subject['subtype'] == 'tv' else 'Unknown'
        language = subject['languages'][0]
        language = '华语' if language in self.CHINESE else language
        filename = '%d_%s' % (subject['year'], subject['original_title'])
        if subject['title'] != subject['original_title']:
            filename += '_%s' % subject['title']
        # disallowed characters: \/:*?"<>|
        filename = re.sub(r'[\\/:*?"<>|]', '$', filename)
        return os.path.join(self.cdn, subtype, language), filename

    def add_movie(self, subject):
        con = self.connection
        cursor = con.cursor()
        cursor.execute('INSERT INTO movie(id, title, alt,status, tag_date, original_title, aka, subtype, languages, '
                       'year, durations, current_season, episodes_count, seasons_count, last_update, archived) '
                       'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, DATETIME(\'now\'), 0)',
                       ([subject[key] for key in [
                           'id', 'title', 'alt', 'status', 'tag_date', 'original_title', 'aka', 'subtype', 'languages',
                           'year', 'durations', 'current_season', 'episodes_count', 'seasons_count'
                       ]]))
        if cursor.rowcount != 1:
            logger.error('Failed to Add movie: %s. ROLLBACK!', subject['title'])
            con.rollback()
            return False
        con.commit()
        return True

    def update_movie(self, subject_id: int, ignore_none=True, **kwargs):
        params = {}
        for k, v in kwargs.items():
            if not ignore_none or v is not None:
                params[k] = v
        if not params or len(params) == 0:
            raise ValueError('No params to update')
        con = self.connection
        cursor = con.cursor()
        cursor.execute('UPDATE movie SET last_update=DATETIME(\'now\'), %s WHERE id = %d'
                       % (', '.join(['%s = :%s' % (k, k) for k in params]), subject_id), params)
        if cursor.rowcount != 1:
            logger.error('Failed to update movie: %d', subject_id)
            con.rollback()
            return False
        con.commit()
        return True

    def get_movies(self, order_by=None, desc='asc', ignore_blank=False, **params):
        cursor = self.__select_movie(order_by=order_by, desc=desc, ignore_blank=ignore_blank, **params)
        return [dict(x) for x in cursor.fetchall()]

    def get_movie(self, **params):
        cursor = self.__select_movie(**params)
        r = cursor.fetchone()
        if r:
            return dict(r)
        return None

    def __select_movie(self, order_by=None, desc='asc', ignore_blank=False, **params):
        sql = 'SELECT * FROM movie'
        if ignore_blank:
            for k, v in params.copy().items():
                if v is None or v == '':
                    del params[k]
        if params and len(params) > 0:
            sql += ' WHERE %s' % (' AND '.join(['%s = :%s' % (k, k) for k in params]))
        if order_by:
            sql += ' ORDER BY %s' % order_by
            if desc.lower() == 'desc':
                sql += ' DESC'
        cursor = self.connection.cursor()
        cursor.execute(sql, params)
        return cursor


def get_duration(filepath):
    media_info = MediaInfo.parse(filepath)
    tracks = dict([(x.track_type, x) for x in media_info.tracks])
    d = tracks['General'].duration
    if isinstance(d, int):
        return d
    if 'Video' in tracks:
        d = tracks['Video'].duration
        if isinstance(d, int):
            return d
    raise IOError('Duration Not Found')


def weight_video_file(filepath, movie_durations=None):
    """
    Read related arguments from a file.
    """
    if not os.path.isfile(filepath):
        raise ValueError
    ext = os.path.splitext(filepath)[1]
    duration = get_duration(filepath) // 1000
    size = os.path.getsize(filepath)
    return weight_video(ext, movie_durations, size, duration)


def weight_video(ext=None, movie_durations=None, size=-1, file_duration=-1):
    """
    Calculate weight of a file for a movie. Larger the result is, higher quality the file has.
    Properties read from the file have higher priority than those specified by arguments.

    Whose extension is not in VIDEO_SUFFIXES will be excluded directly.

    If duration of the movie isn't given, size and duration will be invalid. Otherwise, follow below rules.
    Actual duration of the file has to be within 1 minutes compared to give duration.
    Size of the file will be compared to standard size computed based on given duration of the movie and standard kbps.
    The file will be excluded if its size is less than half of the standard size.

    The file is a good one if weight is over 90.

    :param movie_durations: Unit: minute
    :param size: Unit: B
    :param file_duration: Unit: second
    :return ratio * 100
    """
    if movie_durations is None:
        movie_durations = []
    ws = []
    if ext is not None:
        if ext not in VIDEO_SUFFIXES:
            # logger.warning('No video file: %s', ext)
            return -1
        else:
            if ext in ('.mp4', '.mkv'):
                ws.append(100)
            else:
                ws.append(50)
    if movie_durations and len(movie_durations) > 0:
        durations = [int(re.findall(r'\d+', d)[0]) for d in movie_durations]
        if file_duration >= 0:
            for i, duration in enumerate(sorted(durations)):
                if abs(duration * 60 - file_duration) < 60:
                    ws.append(100 * (i + 1) / len(durations))
                    break
                if i == len(durations) - 1:
                    # logger.warning('Error durations: %.2f, %s', file_duration / 60, ','.join([str(x) for x in movie_durations]))
                    return -1
        if size >= 0:
            target_size = int(sum(durations) / len(durations) * 7680 * standard_kbps)
            if size < (target_size // 2):
                # logger.warning('Too small file: %s, request: %s', print_size(size), print_size(target_size))
                return -1
            elif size <= target_size:
                ws.append(100 * (size / target_size))
            elif size <= (target_size * 2):
                ws.append(100 * (target_size / size))
            else:
                ws.append(200 * (target_size / size) ** 2)
    if len(ws) == 0:
        return 0
    return sum(ws) / len(ws)


def classify_url(url: str):
    """
    Classify and decode a url. Optional protocols: http/ed2k/pan/ftp/magnet/torrent/unknown

    Structure of urls:
    ed2k: ed2k://|file|<file name>|<size of file, Unit: B>|<hash of file>|/
    magnet:

    :return: (protocol of url, decoded url)
    """
    if url.startswith('thunder://'):
        url = base64.b64decode(url[10:])
        try:
            url = url.decode('utf-8').strip('AAZZ')
        except UnicodeDecodeError:
            url = url.decode('gbk').strip('AAZZ')
    url = parse.unquote(url.rstrip('/'))

    if 'pan.baidu.com' in url:
        return 'pan', url
    if url.endswith('.torrent'):
        return 'torrent', url
    for head in ['ftp', 'http', 'ed2k', 'magnet']:
        if url.startswith(head):
            return head, url
    return 'unknown', url
