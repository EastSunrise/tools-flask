""" Video views

@Author Kingen
@Date 2020/5/13
"""
import base64
import logging
import math
import os
import re
import shutil
from sqlite3 import connect, PARSE_DECLTYPES, Row
from urllib import parse, error

import pythoncom
from pymediainfo import MediaInfo

from tools.internet.douban import Douban
from tools.internet.downloader import IDM, Thunder
from tools.internet.resource import VideoSearch80s, VideoSearchXl720, VideoSearchXLC, VideoSearchZhandi, \
    VideoSearchAxj
from tools.utils import file
from tools.video import Archived, Status, Subtype

logger = logging.getLogger(__name__)

VIDEO_SUFFIXES = ('.avi', '.rmvb', '.mp4', '.mkv')
movie_standard_kbps = 2000  # kb/s
movie_standard_size = movie_standard_kbps * 7680  # B/min
tv_standard_kbps = 1000  # kb/s
tv_standard_size = tv_standard_kbps * 7680  # B/min
movie_duration_error = 60  # seconds


class VideoManager:
    CHINESE = ['汉语普通话', '普通话', '粤语', '闽南语', '河南方言', '贵州方言', '贵州独山话']
    JUNK_SITES = ['yutou.tv', '80s.la', '80s.im', '2tu.cc', 'bofang.cc:', 'dl.y80s.net', '80s.bz', 'xubo.cc']
    ALL_SITES = [VideoSearch80s(), VideoSearchXl720(), VideoSearchXLC(), VideoSearchZhandi(), VideoSearchAxj()]
    SOURCE_FIELDS = ['id', 'title', 'alt', 'status', 'tag_date', 'original_title', 'aka', 'subtype', 'languages', 'year',
                     'durations', 'current_season', 'episodes_count', 'season_count']
    FIELDS = SOURCE_FIELDS + ['archived', 'location', 'source', 'last_update']

    def __init__(self, cdn, db_path, idm_path, api_key, cookie) -> None:
        self.cdn = cdn
        self.__temp_dir = os.path.join(self.cdn, 'Temp')
        self.__db = db_path
        self.__idm = IDM(idm_path, self.__temp_dir)
        self.__douban: Douban = Douban(api_key)
        self.__cookie = cookie
        self.__con = None

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
            self.__con = None

    def update_my_movies(self, user_id, start_date=None):
        """
        Update my collected movies from Douban to database.

        If not exist in db, get full info and insert into db, with archived set to 0.
        If exists, update status and tag_date.

        :param start_date: when tag_date start
        """
        subjects = self.get_movies()
        ids = [m['id'] for m in subjects]
        if start_date is None and len(subjects) > 0:
            start_date = max([x['tag_date'] for x in subjects if x['tag_date'] is not None])
        logger.info('Start updating movies since %s', start_date if start_date else '')
        added_count = error_count = 0
        for subject_id, subject in self.__douban.collect_user_movies(user_id, start_date=start_date).items():
            subject['status'] = Status.from_name(Status, subject.get('status'))
            subject_id = int(subject_id)
            try:
                subject.update(self.movie_subject(subject_id))
            except error.HTTPError as e:
                error_count += 1
                logger.error(e)
                continue

            if subject_id in ids:
                self.update_movie(subject_id, **subject)
            else:
                if self.add_movie(subject):
                    added_count += 1
        logger.info('Finish updating movies, %d movies added, %d errors', added_count, error_count)
        return added_count, error_count

    def archive_all(self):
        subjects = self.get_movies(order_by='last_update', desc='desc')
        archived_count = unarchived_count = 0
        locations = set()
        for subject in subjects:
            archived, location = self.is_archived(subject)
            if archived:
                if subject['archived'] != Archived.playable or subject['location'] != location:
                    if self.update_archived(subject['id'], Archived.playable, location):
                        archived_count += 1
                        locations.add(location)
                        continue
            elif subject['archived'] == Archived.playable:
                if self.update_archived(subject['id'], Archived.added):
                    unarchived_count += 1
                    continue
            locations.add(subject['location'])
        logger.info('Finish archiving: %d archived, %d unarchived', archived_count, unarchived_count)

        for dirpath, dirnames, filenames in os.walk(os.path.join(self.cdn, 'Movies')):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if filepath not in locations:
                    logger.warning('Unarchived video file: %s', filepath)

        return archived_count, unarchived_count

    def add_subject(self, subject_id: int):
        subject = self.get_movie(id=subject_id)
        if subject is None:
            return self.add_movie(self.movie_subject(subject_id))
        logger.info('Exists subject: %d', subject_id)
        return True

    def movie_subject(self, subject_id):
        try:
            subject = self.__douban.movie_subject(subject_id)
        except error.HTTPError as e:
            if e.code == 404:
                subject = self.__douban.movie_subject_with_cookie(subject_id, self.__cookie)
            else:
                raise
        subject['subtype'] = Subtype.from_name(Subtype, subject['subtype'])
        subject['title'] = remove_redundant_spaces(subject['title'])
        subject['original_title'] = remove_redundant_spaces(subject['original_title'])
        remove_redundant_spaces(subject['aka'])
        for k in subject.copy():
            if k not in self.FIELDS:
                del subject[k]
        return subject

    def search_resources(self, key):
        """
        :return: sites and resources found
        """
        resources = {}
        if isinstance(key, int):
            subject = self.get_movie(id=key)
            if subject is None:
                logger.info('No subject found with id: %d', key)
                return {}
            for site in sorted(self.ALL_SITES, key=lambda x: x.priority):
                resources[site] = site.search(subject)
            return resources
        if isinstance(key, str):
            pass

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
        subject_id, title = subject['id'], subject['title']
        archived, location = self.is_archived(subject)
        logger.info('Collecting subject: %s, %s', title, subject['alt'])
        if archived:
            logger.info('File exists for the subject %s: %s', title, location)
            return self.update_archived(subject_id, Archived.playable, location)

        links = {'http': {}, 'ed2k': {}, 'pan': {}, 'ftp': {}, 'magnet': {}, 'torrent': {}, 'unknown': {}}
        for site in sorted(self.ALL_SITES, key=lambda x: x.priority):
            resources = site.collect(subject)
            for url, remark in resources.items():
                p, u = classify_url(url)
                if any([(x in u) for x in self.JUNK_SITES]):
                    continue
                filename, ext, size = None, None, -1
                if p == 'http' or p == 'ftp':
                    filename = os.path.basename(u)
                    ext = os.path.splitext(filename)[1]
                elif p == 'ed2k':
                    filename = u.split('|')[2]
                    ext = os.path.splitext(filename)[1]
                    size = int(u.split('|')[3])
                elif p == 'torrent':
                    filename = os.path.basename(u)
                if weight_video(subject['subtype'], ext, subject['durations'], size) < 0:
                    continue
                links[p][u] = (u, filename, ext)

        dst_dir = os.path.join(self.__temp_dir, '%d_%s' % (subject_id, title))
        os.makedirs(dst_dir, exist_ok=True)
        url_count = 0
        for p in ['http', 'ftp']:
            for u, filename, ext in links[p].values():
                logger.info('Add IDM task of %s, downloading from %s to the temporary dir', title, u)
                self.__idm.add_task(u, dst_dir, '%d_%s_http_%d_%s' % (subject_id, title, url_count, filename))
                url_count += 1
        pythoncom.CoInitialize()
        thunder = Thunder()
        for p in ['ed2k', 'ftp', 'torrent']:
            for u, filename, ext in links[p].values():
                logger.info('Add Thunder task of %s, downloading from %s to the temporary dir', title, u)
                thunder.add_task(u, '%d_%s_%s_%d_%s' % (subject_id, title, p, url_count, filename))
                url_count += 1
        for p in ['magnet']:
            for u, filename, ext in links[p].values():
                logger.info('Add Thunder task of %s, downloading from %s to the temporary dir', title, u)
                thunder.add_task(u, '')
                url_count += 1
        thunder.commit_tasks()
        pythoncom.CoUninitialize()

        if url_count == 0:
            logger.warning('No resources found for: %s', title)
            return self.update_archived(subject_id, Archived.none)
        logger.info('Tasks added: %d for %s. Downloading...', url_count, title)
        return self.update_archived(subject_id, Archived.downloading)

    def archive_temp(self, subject_id):
        """
        After finishing all IDM and Thunder tasks.
        :return: -2: IOError, -1: no qualified file, 1: archived
        """
        subject = self.get_movie(id=subject_id)
        if len(subject['durations']) == 0:
            logger.warning('No durations set for %s, id: %d', subject['title'], subject_id)
            return 'No durations'

        weights = {}
        dst_dir = os.path.join(self.__temp_dir, '%d_%s' % (subject_id, subject['title']))
        for dirpath, dirnames, filenames in os.walk(dst_dir):
            for filename in filenames:
                if filename.endswith('.torrent'):
                    pass
                elif os.path.splitext(filename)[1] in VIDEO_SUFFIXES:
                    path = os.path.join(dirpath, filename)
                    try:
                        weight = weight_video_file(path, subject['subtype'], subject['durations'])
                        if weight < 0:
                            file.delete_file(path, False)
                        else:
                            weights[path] = weight
                    except IOError as e:
                        logger.error(e)
                        file.delete_file(path, True)
                else:
                    return 'Not all downloaded'

        if len(weights) == 0:
            logger.warning('No qualified video file: %s', subject['title'])
            shutil.rmtree(dst_dir)
            return self.update_archived(subject_id, Archived.none)

        archived, location = self.is_archived(subject)
        if subject['subtype'] == Subtype.movie:
            chosen = max(weights, key=lambda x: weights[x])
            logger.info('Chosen file: %.2f, %s', weights[chosen], chosen)
            dst = os.path.splitext(location)[0] + os.path.splitext(chosen)[1]
            if not archived or (archived and weight_video_file(location, subject['subtype'], subject['durations']) < weights[chosen]):
                if archived:
                    file.delete_file(location, False)
                code, msg = file.copy(chosen, dst)
                if code != 0:
                    return msg
                location = dst
            for p in weights:
                file.delete_file(p, False)
        else:
            episodes_count = subject['episodes_count']
            series = [{} for i in range(episodes_count)]
            for p, weight in weights.items():
                name = os.path.splitext(os.path.basename(p))[0]
                if name.startswith(str(subject_id)):
                    name = name.rsplit('_', 1)[1]
                index = get_episode(name, episodes_count, subject['current_season'])
                if not index:
                    logger.warning('Can\'t get episode from: %s', p)
                    continue
                series[index - 1][p] = weight
            empties = [str(i + 1) for i, x in enumerate(series) if len(x) == 0]
            if len(empties) > 0:
                return 'Not enough episodes for %s, total: %d, lacking: %s' % (subject['title'], episodes_count, ', '.join(empties))
            episode_format = 'E%%0%dd' % math.ceil(math.log10(episodes_count + 1))
            for episode, files in enumerate(series):
                if len(files) == 0:
                    continue
                episode += 1
                chosen = max(files, key=lambda x: files[x])
                logger.info('Chosen episode %d: %.2f, %s', episode, files[chosen], chosen)
                ext = os.path.splitext(chosen)[1]
                dst = os.path.join(location, (episode_format % episode) + ext)
                code, msg = file.copy(chosen, dst)
                if code != 0:
                    continue
                for p in files:
                    file.delete_file(p, False)
        shutil.rmtree(dst_dir)
        return self.update_archived(subject_id, Archived.playable, location=location)

    def play(self, subject_id):
        movie = self.get_movie(id=subject_id)
        if movie:
            location = movie['location']
            if movie['subtype'] == Subtype.movie and os.path.isfile(location):
                os.startfile(location)
                return Archived.playable
            elif movie['subtype'] == Subtype.tv and os.path.isdir(location) and len(os.listdir(location)) > 0:
                os.startfile(os.path.join(location, os.listdir(location)[0]))
                return Archived.playable
            logger.info('No location found')
            return self.update_archived(subject_id, Archived.added)
        return 'Not found'

    def is_archived(self, subject):
        """
        :return: (False/True, location)
        """
        subtype = 'Movies' if subject['subtype'] == Subtype.movie else 'TV' if subject['subtype'] == Subtype.tv else 'Unknown'
        language = subject['languages'][0]
        language = '华语' if language in self.CHINESE else language
        path = os.path.join(self.cdn, subtype, language)

        filename = '%d_%s' % (subject['year'], subject['original_title'])
        if subject['title'] != subject['original_title']:
            filename += '_%s' % subject['title']
        # disallowed characters: \/:*?"<>|
        filename = re.sub(r'[\\/:*?"<>|]', '$', filename)

        location = os.path.join(path, filename)
        if subject['subtype'] == Subtype.tv and os.path.isdir(location):
            if len([x for x in os.listdir(location) if re.match(r'E\d+', x)]) == subject['episodes_count']:
                return True, location
        if subject['subtype'] == Subtype.movie and os.path.isdir(path):
            with os.scandir(path) as sp:
                for f in sp:
                    if f.is_file() and os.path.splitext(f.name)[0] == filename:
                        return True, f.path
        return False, location

    def add_movie(self, subject):
        if subject.get('archived', None) is None:
            subject['archived'] = Archived.added
        if subject.get('status', None) is None:
            subject['status'] = Status.unmarked
        con = self.connection
        cursor = con.cursor()
        cursor.execute('INSERT INTO movie(%s, last_update) VALUES (%s, DATETIME(\'now\'))'
                       % (', '.join(subject.keys()), ', '.join([':' + x for x in subject])), subject)
        if cursor.rowcount != 1:
            logger.error('Failed to Add movie: %s. ROLLBACK!', subject['title'])
            con.rollback()
            return False
        con.commit()
        return True

    def update_movie(self, subject_id: int, ignore_none=True, **kwargs):
        if ignore_none:
            for k, v in kwargs.copy().items():
                if v is None:
                    del kwargs[k]
        if len(kwargs) == 0:
            raise ValueError('No params to update')
        con = self.connection
        cursor = con.cursor()
        cursor.execute('UPDATE movie SET last_update=DATETIME(\'now\'), %s WHERE id = %d'
                       % (', '.join(['%s = :%s' % (k, k) for k in kwargs]), subject_id), kwargs)
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
                       (dst, location, subject_id))
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

    @staticmethod
    def __parse_subject(subject):
        if 'status' in subject and isinstance(subject['status'], str):
            subject['status'] = Status.from_name(Status, subject['status'])
        if 'subtype' in subject and isinstance(subject['subtype'], str):
            subject['subtype'] = Subtype.from_name(Subtype, subject['subtype'])
        if 'archived' in subject and isinstance(subject['archived'], str):
            subject['archived'] = Archived.from_name(Archived, subject['archived'])

    def __select_movie(self, order_by=None, desc='asc', ignore_blank=False, **params):
        sql = 'SELECT * FROM movie'
        if ignore_blank:
            for k, v in params.copy().items():
                if v is None or v == '':
                    del params[k]
        if params and len(params) > 0:
            self.__parse_subject(params)
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


def weight_video_file(filepath, subtype: Subtype, movie_durations=None):
    """
    Read related arguments from a file.
    """
    if not os.path.isfile(filepath):
        raise ValueError
    ext = os.path.splitext(filepath)[1]
    duration = get_duration(filepath) // 1000
    size = os.path.getsize(filepath)
    return weight_video(subtype, ext, movie_durations, size, duration)


def weight_video(subtype: Subtype, ext=None, movie_durations=None, size=-1, file_duration=-1):
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
    weight = 0
    if ext is not None:
        if ext not in VIDEO_SUFFIXES:
            return -1
        else:
            if ext in ('.mp4', '.mkv'):
                weight += 100
            else:
                weight += 50
    if movie_durations and len(movie_durations) > 0:
        durations = sorted([int(re.findall(r'\d+', d)[0]) for d in movie_durations])
        if file_duration >= 0:
            if subtype == Subtype.movie:
                for i, duration in enumerate(durations):
                    if abs(duration * 60 - file_duration) < movie_duration_error:
                        weight += (1000 * (i + 1) / len(durations))
                        break
                    if i == len(durations) - 1:
                        return -1
            else:
                dst_duration = durations[-1] * 60
                if file_duration < dst_duration:
                    percent = file_duration / dst_duration
                else:
                    percent = dst_duration / file_duration
                weight += (1000 * percent)
        if size >= 0:
            target_size = int(sum(durations) / len(durations) * (movie_standard_size if subtype == Subtype.movie else tv_standard_size))
            if size < (target_size // 2):
                return -1
            elif size <= target_size:
                weight += (10 * (size / target_size))
            elif size <= (target_size * 2):
                weight += (10 * (target_size / size))
            else:
                weight += (20 * (target_size / size) ** 2)
    return weight


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


def get_episode(name, episodes_count, current_season) -> int:
    """
    Get the episode number by the name, range: [1:episodes_count]
    The last and only matched numeral
    :param name: without suffix to avoid conflict like '.mp4'
    :return:i
    """
    match = re.search(r'E(\d+)', name)
    if match is not None:
        season_match = re.search(r'S(\d+)', name)
        if season_match is None or int(season_match.group(1)) == current_season:
            return int(match.group(1))

    ms = re.findall(r'\d+', name)
    if len(ms) == 1:
        i = int(ms[0])
        if 1 <= i <= episodes_count:
            return i
    elif len(ms) == 2:
        s = int(ms[0])
        i = int(ms[1])
        if s == current_season and 1 <= i <= episodes_count:
            return i
    return False


def remove_redundant_spaces(string):
    if isinstance(string, str):
        return re.sub(r'\s+', ' ', string.strip())
    if isinstance(string, list) or isinstance(string, tuple):
        for i, s in enumerate(string):
            string[i] = re.sub(r'\s+', ' ', s.strip())
        return string
    raise ValueError


def separate_srt(src: str):
    """
    Separate the .srt file with two languages to separated files.
    :param src: the path of the source file. Every 4 lines form a segment and segments are split by a space line.
    """
    if os.path.isfile(src) and src.lower().endswith('.srt'):
        root, ext = os.path.splitext(src)
        with open(src, mode='r', encoding='utf-8') as fp:
            with open(root + '_1' + ext, 'w', encoding='utf-8') as f1:
                with open(root + '_2' + ext, 'w', encoding='utf-8') as f2:
                    segment = []
                    for line in fp.readlines():
                        if line != '\n':
                            segment.append(line)
                        else:
                            if len(segment) != 4:
                                logger.info('Special lines in No. %s', segment[0])
                            f1.writelines([
                                segment[0], segment[1], segment[2], '\n'
                            ])
                            f2.writelines([
                                segment[0], segment[1], segment[3], '\n'
                            ])
                            segment = []


def print_size(size: int):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return '%.2f %s' % (size, unit)
        size /= 1024
    return '%.2f %s' % (size, 'PB')
