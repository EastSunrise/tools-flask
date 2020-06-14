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
from .spider import BaseSite


class Douban(BaseSite):
    COUNT = 20
    START_DATE = '2005-03-06'

    def __init__(self, api_key) -> None:
        super().__init__('Douban', 'douban.com', interval=5)
        self.__api_key = api_key

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
            data = self.api_movie_in_theaters(start=start)
            for subject in data['subjects']:
                if subject['id'] not in movies:
                    movies[subject['id']] = subject
            start += data['count']
            if start >= data['total']:
                break

        data = self.api_movie_new_movies()
        for subject in data['subjects']:
            if subject['id'] not in movies:
                movies[subject['id']] = subject

        data = self.api_movie_weekly()
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
        """
        This is a backup for movies that can't be found by self.api_movie_subject().
        The movie is probably x-rated and restricted to be accessed only after logging in.
        :raise HTTPError(404)
        :return:
        """
        url = self._get_url('/subject/{id}', low_domain='movie', path_params={'id': subject_id})
        req = Request(url, method='GET')
        soup = self.get_soup(req)
        wrapper = soup.find('div', id='wrapper')
        subject = {}

        keywords = [x.strip() for x in soup.find('meta', {'name': 'keywords'})['content'].split(',')]
        subject['title'] = keywords[0]
        subject['original_title'] = keywords[1]
        subject['year'] = int(wrapper.find('h1').find('span', class_='year').get_text().strip('( )'))

        spans = dict([(span_pl.get_text().strip(), span_pl) for span_pl in wrapper.find('div', id='info').find_all('span', class_='pl')])
        for pl in ['导演', '编剧', '主演']:
            if pl in spans:
                celebrities = []
                for celebrity_a in spans[pl].find_next('span', class_='attrs').find_all('a'):
                    celebrities.append({
                        'name': celebrity_a.get_text().strip(),
                        'alt': self._get_url(parse.unquote(celebrity_a['href']), low_domain='movie')
                    })
                celebrity_key = 'directors' if pl == '导演' else 'writers' if pl == '编剧' else 'casts'
                subject[celebrity_key] = celebrities
        if '类型:' in spans:
            subject['genres'] = [span.get_text().strip() for span in spans['类型:'].find_all_next('span', property='v:genre')]
        subject['countries'] = [name.strip() for name in str(spans['制片国家/地区:'].next_sibling).split('/')]
        subject['languages'] = [name.strip() for name in str(spans['语言:'].next_sibling).split('/')]
        subject['aka'] = [] if '又名:' not in spans else [name.strip() for name in str(spans['又名:'].next_sibling).split(' / ')]
        if '上映日期:' in spans:
            subject['subtype'] = 'movie'
            subject['pubdates'] = [span['content'] for span in spans['上映日期:'].find_all_next('span', property='v:initialReleaseDate')]
            if '片长:' in spans:
                span = spans['片长:'].find_next('span', property='v:runtime')
                subject['durations'] = [span.get_text().strip()]
                if not isinstance(span.next_sibling, bs4.Tag):
                    subject['durations'] += [d.strip() for d in str(span.next_sibling).strip('/ ').split('/')]
            else:
                subject['durations'] = []
            subject['current_season'] = None
            subject['seasons_count'] = None
            subject['episodes_count'] = None
        elif '首播:' in spans:
            subject['subtype'] = 'tv'
            subject['pubdates'] = [span['content'] for span in spans['首播:'].find_all_next('span', property='v:initialReleaseDate')]
            if '单集片长:' in spans:
                subject['durations'] = [x.strip() for x in str(spans['单集片长:'].next_sibling).strip('/ ').split('/')]
            else:
                subject['durations'] = []
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
                    raise ValueError('Info of seasons is not specified')
            else:
                subject['current_season'] = None
                subject['seasons_count'] = None
        else:
            logger.error('Subtype is not specified')
            raise ValueError('Subtype is not specified')

        if '官方网站:' in spans:
            subject['website'] = spans['官方网站:'].find_next('a')['href']
        if 'IMDb链接:' in spans:
            subject['imdb'] = spans['IMDb链接:'].find_next('a')['href']

        return subject

    def api_movie_subject(self, subject_id):
        return self.__get_api_result('/v2/movie/subject/{id}', {'id': subject_id})

    def api_movie_subject_photos(self, subject_id, start=0, count=20):
        return self.__get_api_result('/v2/movie/subject/{id}/photos', {'id': subject_id}, {'start': start, 'count': count})

    def api_movie_subject_reviews(self, subject_id, start=0, count=20):
        return self.__get_api_result('/v2/movie/subject/{id}/reviews', {'id': subject_id}, {'start': start, 'count': count})

    def api_movie_subject_comments(self, subject_id, start=0, count=20):
        return self.__get_api_result('/v2/movie/subject/{id}/comments', {'id': subject_id}, {'start': start, 'count': count})

    def api_movie_celebrity(self, celebrity_id):
        return self.__get_api_result('/v2/movie/celebrity/{id}', {'id': celebrity_id})

    def api_movie_celebrity_photos(self, celebrity_id, start=0, count=20):
        return self.__get_api_result('/v2/movie/celebrity/{id}/photos', {'id': celebrity_id}, {'start': start, 'count': count})

    def api_movie_celebrity_works(self, celebrity_id, start=0, count=20):
        return self.__get_api_result('/v2/movie/celebrity/{id}/works', {'id': celebrity_id}, {'start': start, 'count': count})

    def api_movie_top250(self, start=0, count=COUNT):
        return self.__get_api_result('/v2/movie/top250', query_params={
            'start': start,
            'count': count
        })

    def api_movie_weekly(self):
        return self.__get_api_result('/v2/movie/weekly')

    def api_movie_new_movies(self):
        return self.__get_api_result('/v2/movie/new_movies')

    def api_movie_in_theaters(self, start=0, count=COUNT, city='北京'):
        """
        :param city: name or number id of the city
        """
        return self.__get_api_result('/v2/movie/in_theaters', query_params={
            'start': start,
            'count': count,
            'city': city
        })

    def api_movie_coming_soon(self, start=0, count=COUNT):
        return self.__get_api_result('/v2/movie/coming_soon', query_params={
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
        url = self._get_url('/people/{id}/{cat}', low_domain=cat, path_params={'id': user_id, 'cat': catalogs[cat]},
                            query_params={'start': start})
        soup = self.get_soup(url)
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
        Get user records
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
        url = self._get_url(path='/people/{id}/{cat}', low_domain=catalog, path_params={'id': user_id, 'cat': record_cat},
                            query_params={'sort': sort_by, 'start': start, 'mode': 'list'})
        soup = self.get_soup(url)
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

    def _get_url(self, path, low_domain='', path_params=None, query_params=None):
        if low_domain == 'api':
            if query_params is None:
                query_params = {}
            query_params['apikey'] = self.__api_key
        return super()._get_url(path, low_domain, path_params, query_params)

    def __get_api_result(self, relative_url, path_params=None, query_params=None):
        url = self._get_url(path=relative_url, low_domain='api', path_params=path_params, query_params=query_params)
        return json.loads(self.do_request(url), encoding='utf-8')


class IMDb(BaseSite):

    def __init__(self) -> None:
        super().__init__('IMDb', 'imdb.com', interval=5)

    def title_technical(self, tt: int):
        title = {'id': tt, 'durations': []}
        url = 'https://www.imdb.com/title/tt%07d/technical' % tt
        table = self.get_soup(url).find('div', id='technical_content').find('table')
        if table is not None:
            for tr in table.find_all('tr'):
                label = tr.find('td', class_='label')
                if label is not None and label.get_text().strip() == 'Runtime':
                    for d in label.find_next('td').get_text().strip().split('\n'):
                        d = d.strip()
                        match = re.fullmatch(r'\d+ hr( \d+ min)? \((\d+ min)\)(.*)', d)
                        if match is not None:
                            d = match.group(2) + match.group(3)
                        title['durations'].append(d)
                    break
        return title
