""" initialization

@Author Kingen
@Date 2020/5/12
"""
import logging
import os
import re
from urllib import error

from flask import Blueprint, request, g, render_template
from flask_cors import cross_origin

from tools.internet.douban import Douban
from tools.utils.common import success, fail
from tools.video.enums import Status, Archived, Subtype
from .manager import VideoManager

video_config = None

video_blu = Blueprint('video', __name__, url_prefix='/video')

logger = logging.getLogger(__name__)

origins = ['https://movie.douban.com', 'http://localhost:63342', 'http://127.0.0.1:5000']


@video_blu.route('/my')
def my_movies():
    params = request.args.copy()
    params['order_by'] = request.args.get('order_by', default='last_update')
    params['desc'] = request.args.get(
        'desc', default=('desc' if params['order_by'] == 'last_update' or params['order_by'] == 'tag_date' else 'asc'))
    subjects = manager().get_movies(ignore_blank=True, **params)
    for subject in subjects:
        subject['durations'] = [re.search(r'\d+', x).group(0) for x in subject['durations']]
    return render_template(
        'my.jinja2', subjects=subjects, params=params,
        members={
            'archived': Archived.__members__,
            'status': Status.__members__,
            'subtype': Subtype.__members__
        }
    )


@video_blu.route('/update')
def update_my_movies():
    if video_config['COOKIE']:
        return success(count=manager().update_my_movies(Douban(video_config['API_KEY']), video_config['USER_ID'], video_config['COOKIE']))
    return fail('No cookie')


@video_blu.route('/search')
def search():
    subject_id = request.args.get('id', type=int)
    return render_template('search.jinja2', resources=manager().search_resources(subject_id))


@video_blu.route('/subject')
@cross_origin(origins=origins)
def is_archived():
    """
    params: id=<subject_id>
    :return: archived info of the subject
    """
    subject_id = request.args.get('id', type=int)
    movie = manager().get_movie(id=subject_id)
    if movie:
        return archived_result(movie['archived'])
    return fail('Not found')


@video_blu.route('/add')
@cross_origin(origins=origins)
def add():
    subject_id = request.args.get('id', type=int)
    douban = Douban(video_config['API_KEY'])
    try:
        subject = douban.movie_subject(subject_id)
    except error.HTTPError as e:
        if e.code == 404 and video_config['COOKIE']:
            subject = douban.movie_subject_with_cookie(subject_id, video_config['COOKIE'])
        else:
            return archived_result('Not Found')
    if subject.get('status', None) is None:
        subject['status'] = Status.unmarked
    if manager().add_movie(subject):
        return archived_result(Archived.added)
    return archived_result('Failed to insert')


@video_blu.route('/collect')
@cross_origin(origins=origins)
def collect():
    subject_id = request.args.get('id', type=int)
    return archived_result(manager().collect_resources(subject_id))


@video_blu.route('/play')
@cross_origin(origins=origins)
def play():
    subject_id = request.args.get('id', type=int)
    movie = manager().get_movie(id=subject_id)
    if movie:
        location = movie['location']
        if movie['subtype'] == Subtype.movie and os.path.isfile(location):
            os.startfile(location)
            return archived_result(Archived.playable)
        elif movie['subtype'] == Subtype.tv and os.path.isdir(location) and len(os.listdir(location)) > 0:
            os.startfile(os.path.join(location, os.listdir(location)[0]))
            return archived_result(Archived.playable)
    return archived_result('Not found')


@video_blu.route('/archive')
@cross_origin(origins=origins)
def archive():
    return archived_result(manager().archive(request.args.get('id', type=int)))


@video_blu.route('/temp')
@cross_origin(origins=origins)
def archive_temp():
    return archived_result(manager().archive_temp(request.args.get('id', type=int)))


@video_blu.teardown_request
def close_connection(e=None):
    if 'manager' in g and g.manager is not None:
        g.manager.close_connection()


def init_config(config, config_file):
    global video_config
    video_config = config
    video_config.from_pyfile(config_file)


def manager():
    if 'manager' not in g:
        g.manager = VideoManager(video_config['CDN'], video_config['VIDEO_DB'], video_config['IDM_PATH'])
    return g.manager


def archived_result(result):
    if not result:
        return fail('Failed to update archived')
    if isinstance(result, Archived):
        return success(archived=result.name)
    return fail(result)
