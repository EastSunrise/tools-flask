""" Video views

@Author Kingen
@Date 2020/5/13
"""
import base64
import logging
import math
import os
import re
from sqlite3 import connect, PARSE_DECLTYPES, Row
from urllib import parse

import pythoncom
from pymediainfo import MediaInfo

from tools.internet.downloader import IDM, Thunder
from tools.internet.resource import VideoSearch80s, VideoSearchXl720, VideoSearchXLC, VideoSearchZhandi, VideoSearchAxj, VideoSearchHhyyk, VideoSearchMP4
from tools.internet.spider import pre_download
from tools.utils import file
from tools.video import Archived

logger = logging.getLogger(__name__)

VIDEO_SUFFIXES = ('.avi', '.rmvb', '.mp4', '.mkv')
standard_kbps = 2500  # kb/s
standard_size = standard_kbps * 7680  # B/min
movie_duration_error = 60  # s


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
            return 'No subject found'
        subject_id, title, subtype = subject['id'], subject['title'], subject['subtype']
        archived, location = self.is_archived(subject)
        logger.info('Collecting subject: %s, %s', title, subject['alt'])
        if archived:
            logger.info('File exists for the subject %s: %s', title, location)
            return self.update_archived(subject_id, Archived.playable, location)

        links = {'http': {}, 'ed2k': {}, 'pan': {}, 'ftp': {}, 'magnet': {}, 'torrent': {}, 'unknown': {}}
        for site in sorted(self.ALL_SITES, key=lambda x: x.priority):
            for url, remark in site.collect(subject).items():
                p, u = classify_url(url)
                if any([(x in u) for x in self.JUNK_SITES]):
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

        # add download tasks
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
            return self.update_archived(subject_id, Archived.none)
        logger.info('Tasks added: %d for %s. Downloading...', url_count, title)
        return self.update_archived(subject_id, Archived.downloading)

    def archive(self, subject_id):
        subject = self.get_movie(id=subject_id)
        archived, location = self.is_archived(subject)
        if archived:
            return self.update_archived(subject_id, Archived.playable, location=location)
        return self.update_archived(subject_id, Archived.none)

    def archive_temp(self, subject_id):
        """
        After finishing all IDM and Thunder tasks.
        :return: -2: IOError, -1: no qualified file, 1: archived
        """
        subject = self.get_movie(id=subject_id)
        archived, location = self.is_archived(subject)
        if archived:
            return self.update_archived(subject_id, Archived.playable, location=location)

        if len(subject['durations']) == 0:
            logger.warning('No durations set for %s, id: %d', subject['title'], subject_id)
            return 'No durations'

        weights = {}
        paths = [os.path.join(self.__temp_dir, x) for x in os.listdir(self.__temp_dir) if x.startswith(str(subject_id))]
        for path in paths:
            try:
                weight = weight_video_file(path, subject['durations'], subject['subtype'])
                if weight < 0:
                    file.del_to_recycle(path)
                else:
                    weights[path] = weight
            except IOError as error:
                logger.error(error)
                file.del_to_recycle(path)
        if len(weights) == 0:
            logger.warning('No qualified video file: %s', subject['title'])
            return self.update_archived(subject_id, Archived.none)

        if subject['subtype'] == 'movie':
            chosen = max(weights, key=lambda x: weights[x])
            logger.info('Chosen file: %.2f, %s', weights[chosen], chosen)
            ext = os.path.splitext(chosen)[1]
            location = os.path.join(location + ext)
            code, msg = file.copy(chosen, location)
            if code != 0:
                return msg
            for p in weights:
                file.del_to_recycle(p)
        else:
            episodes_count = subject['episodes_count']
            with open('instance/tv.txt', 'a', encoding='utf-8') as fp:
                series = [{} for i in range(episodes_count)]
                for p, weight in weights.items():
                    basename: str = (os.path.splitext(p)[0])
                    name = basename.rsplit('_', 1)[1]
                    ms = re.findall(r'\d+', name)
                    if len(ms) == 1:
                        i = int(ms[0])
                        if 1 <= i <= episodes_count:
                            series[i - 1][p] = weight
                            continue
                    fp.write(p + '\n')
            empties = [str(i + 1) for i, x in enumerate(series) if len(x) == 0]
            if len(empties) > 0:
                logger.info('Not enough episodes for %s, total: %d, lacking: %s', subject['title'], episodes_count, ', '.join(empties))
                return self.update_archived(subject_id, Archived.none)
            episode_format = 'E%%0%dd' % math.ceil(math.log10(episodes_count + 1))
            for episode, files in enumerate(series):
                episode += 1
                chosen = max(files, key=lambda x: files[x])
                logger.info('Chosen episode %d: %.2f, %s', episode, files[chosen], chosen)
                ext = os.path.splitext(chosen)[1]
                dst = os.path.join(location, episode_format % episode + ext)
                code, msg = file.copy(chosen, dst)
                if code != 0:
                    continue
                for p in files:
                    file.del_to_recycle(p)
        return self.update_archived(subject_id, Archived.playable, location=location)

    def is_archived(self, subject):
        """
        :return: (False/True, location)
        """
        subtype = 'Movies' if subject['subtype'] == 'movie' else 'TV' if subject['subtype'] == 'tv' else 'Unknown'
        language = subject['languages'][0]
        language = '华语' if language in self.CHINESE else language
        path = os.path.join(self.cdn, subtype, language)

        filename = '%d_%s' % (subject['year'], subject['original_title'])
        if subject['title'] != subject['original_title']:
            filename += '_%s' % subject['title']
        # disallowed characters: \/:*?"<>|
        filename = re.sub(r'[\\/:*?"<>|]', '$', filename)

        location = os.path.join(path, filename)
        if subject['subtype'] == 'tv' and os.path.isdir(location):
            if len([x for x in os.listdir(location) if re.match(r'E\d+', x)]) == subject['episodes_count']:
                return True, location
        if subject['subtype'] == 'movie' and os.path.isdir(path):
            with os.scandir(path) as sp:
                for f in sp:
                    if f.is_file() and os.path.splitext(f.name)[0] == filename:
                        return True, f.path
        return False, location

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

    def update_archived(self, subject_id, dst: Archived, location=None):
        if dst == Archived.playable:
            if location is None:
                raise ValueError('Unspecific location')
        else:
            location = None
        con = self.connection
        cursor = con.cursor()
        cursor.execute('UPDATE movie SET archived = ?, location = ?, last_update=DATETIME(\'now\') WHERE id = ?',
                       (dst.name, location, subject_id))
        if cursor.rowcount != 1:
            logger.error('Failed to update archived of movie: %d', subject_id)
            con.rollback()
            return False
        con.commit()
        return dst

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


def weight_video_file(filepath, movie_durations=None, subtype='movie'):
    """
    Read related arguments from a file.
    """
    if not os.path.isfile(filepath):
        raise ValueError
    ext = os.path.splitext(filepath)[1]
    duration = get_duration(filepath) // 1000
    size = os.path.getsize(filepath)
    return weight_video(ext, movie_durations, size, duration, subtype=subtype)


def weight_video(ext=None, movie_durations=None, size=-1, file_duration=-1, subtype='movie'):
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
        durations = sorted([int(re.findall(r'\d+', d)[0]) for d in movie_durations])
        if file_duration >= 0:
            if subtype == 'movie':
                for i, duration in enumerate(durations):
                    if abs(duration * 60 - file_duration) < movie_duration_error:
                        ws.append(100 * (i + 1) / len(durations))
                        break
                    if i == len(durations) - 1:
                        # logger.warning('Error durations: %.2f, %s', file_duration / 60, ','.join([str(x) for x in movie_durations]))
                        return -1
            else:
                ws.append(100 * file_duration / durations[-1] if file_duration <= durations[-1] else durations[-1] / file_duration)
        if size >= 0:
            target_size = int(sum(durations) / len(durations) * standard_size)
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
        return -1
    return sum(ws) / len(ws)


def classify_url(url: str):
    """
    Classify and decode a url. Optional protocols: http/ed2k/pan/ftp/magnet/torrent/unknown

    Structure of urls:
    ed2k: ed2k://|file|<file name>|<size of file, Unit: B>|<hash of file>|/
    magnet:

    :return: (protocol of url, decoded url)
    """
    src = url
    if url.startswith('thunder://'):
        url = base64.b64decode(url[10:])
        try:
            url = url.decode('utf-8').strip('AAZZ')
        except UnicodeDecodeError:
            try:
                url = url.decode('gbk').strip('AAZZ')
            except UnicodeDecodeError:
                return 'unknown', src
    url = parse.unquote(url.rstrip('/'))

    if 'pan.baidu.com' in url:
        return 'pan', url
    if url.endswith('.torrent'):
        return 'torrent', url
    for head in ['ftp', 'http', 'ed2k', 'magnet']:
        if url.startswith(head):
            return head, url
    return 'unknown', url
