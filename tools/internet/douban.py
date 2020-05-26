""" Spider for douban.com

Refer to <https://eastsunrise.gitee.io/wiki-kingen/dev/apis/douban.html>.
Functions whose names start with 'collect' is an extension to get all data once.
Json files in the 'douban' directory are examples  for each functions

@Author Kingen
@Date 2020/5/6
"""
import json
import os
import re
from urllib import parse
from urllib.request import Request

import bs4

from . import logger
from .spider import get_soup, do_request


class Douban:
    COUNT = 20
    START_DATE = '2005-03-06'

    def __init__(self, api_key, pause=12) -> None:
        self.__api_key = api_key
        self.__base_params = {
            'apikey': self.__api_key
        }
        self.__headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.132 Safari/537.36',
        }
        self.__pause = pause

    def collect_user_movies(self, my_id, start_date=START_DATE):
        """
        collect my movies data since start_date with cookie got manually.
        :return: {'<id>': {<simple-subject>},...}
        """
        subjects = {}
        for record_cat in ['wish', 'do', 'collect']:
            start = 0
            while True:
                done = False
                records = self.__parse_collections_page(my_id, catalog='movie', record_cat=record_cat, sort_by='time', start=start)
                for subject in records['subjects']:
                    if subject['tag_date'] >= start_date:
                        subjects[subject['id']] = subject
                    else:
                        done = True
                        break
                start += records['count']
                if start >= records['total'] or done:
                    break
        return subjects

    def collect_hit_movies(self):
        """
        collect current hit movies
        :return: {'<id>': {<simple-subject>},...}
        """
        start = 0
        movies = {}
        while True:
            data = self.movie_in_theaters(start=start)
            for subject in data['subjects']:
                if subject['id'] not in movies:
                    movies[subject['id']] = subject
            start += data['count']
            if start >= data['total']:
                break

        data = self.movie_new_movies()
        for subject in data['subjects']:
            if subject['id'] not in movies:
                movies[subject['id']] = subject

        data = self.movie_weekly()
        for subject in [subject['subject'] for subject in data['subjects']]:
            if subject['id'] not in movies:
                movies[subject['id']] = subject

        return movies

    def movie_people_celebrities(self, user_id, start=0):
        return self.__parse_creators_page(user_id, cat='movie', start=start)

    def movie_people_wish(self, user_id, start=0):
        return self.__parse_collections_page(user_id, catalog='movie', record_cat='wish', start=start)

    def movie_people_do(self, user_id, start=0):
        return self.__parse_collections_page(user_id, catalog='movie', record_cat='do', start=start)

    def movie_people_collect(self, user_id, start=0):
        return self.__parse_collections_page(user_id, catalog='movie', record_cat='collect', start=start)

    def movie_subject(self, subject_id):
        return self.__get_result('/v2/movie/subject/{id}', {'id': subject_id})

    def movie_subject_with_cookie(self, subject_id, cookie):
        """
        This is a backup for movies that can't be found by self.movie_subject().
        The movie is probably x-rated and restricted to be accessed only after logging in.
        :return:
        """
        url = self.__get_url('/subject/{id}', 'movie', path_params={'id': subject_id})
        soup = get_soup(Request(url, headers=dict(self.__headers, Cookie=cookie), method='GET'), pause=self.__pause)
        wrapper = soup.find('div', id='wrapper')
        subject = {}

        keywords = [x.strip() for x in soup.find('meta', name='keywords')['content'].split(',')]
        subject['title'] = keywords[0]
        subject['original_title'] = keywords[1]
        subject['year'] = wrapper.find('h1').find('span', class_='year').get_text().strip().strip('()')

        spans = dict([(span_pl.get_text().strip(), span_pl) for span_pl in wrapper.find('div', id='info').find_all('span', class_='pl')])
        for pl in ['导演', '编剧', '主演']:
            if pl in spans:
                celebrities = []
                for celebrity_a in spans[pl].find_next('span', class_='attrs').find_all('a'):
                    celebrities.append({
                        'name': celebrity_a.get_text().strip(),
                        'alt': self.__get_url(parse.unquote(celebrity_a['href']), netloc_cat='movie')
                    })
                celebrity_key = 'directors' if pl == '导演' else 'writers' if pl == '编剧' else 'casts'
                subject[celebrity_key] = celebrities
        subject['genres'] = [span.get_text().strip() for span in spans['类型:'].find_all_next('span', property='v:genre')]
        subject['countries'] = [name.strip() for name in str(spans['制片国家/地区:'].next_sibling).split('/')]
        subject['languages'] = [name.strip() for name in str(spans['语言:'].next_sibling).split('/')]
        subject['aka'] = [name.strip() for name in str(spans['又名:'].next_sibling).split(' / ')]
        if '上映日期:' in spans:
            subject['subtype'] = 'movie'
            subject['pubdates'] = [span['content'] for span in spans['上映日期:'].find_all_next('span', property='v:initialReleaseDate')]
            if '片长:' in spans:
                span = spans['片长:'].find_next('span', property='v:runtime')
                subject['durations'] = [span.get_text().strip()]
                if not isinstance(span.next_sibling, bs4.Tag):
                    subject['durations'] += [d.strip() for d in str(span.next_sibling).strip('/').split('/')]
            else:
                subject['durations'] = []
            subject['current_season'] = None
            subject['seasons_count'] = None
            subject['episodes_count'] = None
        elif '首播:' in spans:
            subject['subtype'] = 'tv'
            subject['pubdates'] = [span['content'] for span in spans['首播:'].find_all_next('span', property='v:initialReleaseDate')]
            subject['durations'] = [x.strip() for x in str(spans['单集片长:'].next_sibling).split('/')]
            subject['episodes_count'] = str(spans['集数:'].next_sibling).strip()
            if '季数:' in spans:
                next_sibling = spans['季数:'].next_sibling
                if isinstance(next_sibling, bs4.NavigableString):
                    subject['current_season'] = str(next_sibling)
                    subject['seasons_count'] = None
                elif isinstance(next_sibling, bs4.Tag) and next_sibling.name == 'select':
                    subject['current_season'] = next_sibling.find('option', selected='selected').get_text().strip()
                    subject['seasons_count'] = len(next_sibling.find_all('option'))
                else:
                    logger.error('Info of seasons is not specified')
                    raise ValueError
            else:
                subject['current_season'] = None
                subject['seasons_count'] = None
        else:
            logger.error('Subtype is not specified')
            raise ValueError

        if '官方网站:' in spans:
            subject['website'] = spans['官方网站:'].find_next('a')['href']
        if 'IMDb链接:' in spans:
            subject['imdb'] = spans['IMDb链接:'].find_next('a')['href']

        return subject

    def movie_subject_photos(self, subject_id, start=0, count=20):
        return self.__get_result('/v2/movie/subject/{id}/photos', {'id': subject_id}, {'start': start, 'count': count})

    def movie_subject_reviews(self, subject_id, start=0, count=20):
        return self.__get_result('/v2/movie/subject/{id}/reviews', {'id': subject_id}, {'start': start, 'count': count})

    def movie_subject_comments(self, subject_id, start=0, count=20):
        return self.__get_result('/v2/movie/subject/{id}/comments', {'id': subject_id}, {'start': start, 'count': count})

    def movie_celebrity(self, celebrity_id):
        return self.__get_result('/v2/movie/celebrity/{id}', {'id': celebrity_id})

    def movie_celebrity_photos(self, celebrity_id, start=0, count=20):
        return self.__get_result('/v2/movie/celebrity/{id}/photos', {'id': celebrity_id}, {'start': start, 'count': count})

    def movie_celebrity_works(self, celebrity_id, start=0, count=20):
        return self.__get_result('/v2/movie/celebrity/{id}/works', {'id': celebrity_id}, {'start': start, 'count': count})

    def movie_top250(self, start=0, count=COUNT):
        return self.__get_result('/v2/movie/top250', query_params={
            'start': start,
            'count': count
        })

    def movie_weekly(self):
        return self.__get_result('/v2/movie/weekly')

    def movie_new_movies(self):
        return self.__get_result('/v2/movie/new_movies')

    def movie_in_theaters(self, start=0, count=COUNT, city='北京'):
        """
        :param city: name or number id of the city
        """
        return self.__get_result('/v2/movie/in_theaters', query_params={
            'start': start,
            'count': count,
            'city': city
        })

    def movie_coming_soon(self, start=0, count=COUNT):
        return self.__get_result('/v2/movie/coming_soon', query_params={
            'start': start,
            'count': count
        })

    def __parse_creators_page(self, user_id, cat='movie', start=0):
        """
        :param user_id:
        :param cat: movie/book/music
        :param start:
        :return:
        """
        catalogs = {'movie': 'celebrities', 'book': 'authors', 'music': 'musicians'}
        url = self.__get_url('/people/{id}/{cat}', cat, {'id': user_id, 'cat': catalogs[cat]}, {'start': start})
        soup = get_soup(Request(url, headers=self.__headers, method='GET'), pause=self.__pause)
        results = []
        content = soup.find('div', id='content')
        for div in content.find('div', class_='article').find_all('div', class_='item'):
            a = div.find('div', class_='info').find('li', class_='title').find('a')
            results.append({
                'id': os.path.basename(a['href'].strip('/')),
                'name': a.get_text().strip(),
            })
        h1 = str(content.find('div', id='db-usr-profile').find('div', class_='info').find('h1').get_text())
        total = int(re.search(r'\(\d+\)', h1)[0])
        return {
            'start': start,
            'count': len(results),
            'total': total,
            'subjects': results
        }

    def __parse_collections_page(self, user_id, catalog='movie', record_cat='wish', sort_by='time', start=0):
        """
        Get user records with cookie
        :param user_id:
        :param catalog: movie/book/music/..
        :param record_cat: wish/do/collect
        :param sort_by: time/rating/title
        :param start: start index
        :return: {
                    'start': start, 'count': count, 'total': total,
                    'subjects': [{'id': id, 'title': title, 'aka': aka, 'alt': alt, 'tag_date': '2010-01-01', 'status': status},...]
                }
        """
        url = self.__get_url(path='/people/{id}/{cat}', netloc_cat=catalog, path_params={'id': user_id, 'cat': record_cat},
                             query_params={'sort': sort_by, 'start': start, 'mode': 'list'})
        soup = get_soup(Request(url, headers=self.__headers, method='GET'), pause=self.__pause)
        results = []
        for li in soup.find('ul', class_='list-view').find_all('li'):
            div = li.div.div
            mov_a = div.a
            titles = [title.strip() for title in mov_a.get_text().strip().split('/')]
            results.append({
                'id': os.path.basename(mov_a['href'].strip('/')),
                'title': titles[0],
                'aka': titles[1:],
                'alt': mov_a['href'],
                'tag_date': div.find_next('div').get_text().strip(),
                'status': record_cat
            })
        num_str = soup.find('span', class_='subject-num').get_text().strip()
        nums = [int(part) for part in re.split('[/-]', num_str)]
        return {
            'start': nums[0] - 1,
            'count': nums[1] - nums[0] + 1,
            'total': nums[2],
            'subjects': results
        }

    def __get_url(self, path, netloc_cat='api', path_params=None, query_params=None):
        """
        get a full encoded url by join netloc and href
        """
        netloc = '%s.douban.com' % netloc_cat
        if netloc_cat == 'api':
            if query_params is None:
                query_params = self.__base_params
            else:
                query_params.update(self.__base_params)
        if path_params is not None:
            path = path.format(**path_params)
        query = parse.urlencode(query_params) if query_params is not None else ''
        return parse.urlunsplit(('https', netloc, path, query, None))

    def __get_result(self, relative_url, path_params=None, query_params=None):
        url = self.__get_url(path=relative_url, netloc_cat='api', path_params=path_params, query_params=query_params)
        req = Request(url, headers=self.__headers, method='GET')
        return json.loads(do_request(req, self.__pause), encoding='utf-8')
