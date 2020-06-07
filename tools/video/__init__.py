""" initialization

@Author Kingen
@Date 2020/5/12
"""
import logging
import re
from urllib import error

from flask import Blueprint, request, render_template, g
from flask_cors import cross_origin

from tools.utils.common import success, fail, read_config_from_py_file
from .enums import Status, Archived, Subtype
from .manager import VideoManager

config = None

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
    user = request.args.get('user', type=int)
    if user:
        added_count, error_count = manager().update_my_movies(user, request.args.get('start'))
        return success(added=added_count, error=error_count)
    else:
        return fail('Unknown user id')


@video_blu.route('/archive_all')
def archive():
    a_c, una_c = manager().archive_all()
    return success(archived=a_c, unarchived=una_c)


@video_blu.route('/search')
def search():
    key = request.args.get('id', type=int)
    if key:
        return render_template('search.jinja2', resources=manager().search_resources(key))
    key = request.args.get('key', type=str)
    if key:
        return render_template('search.jinja2', resources=manager().search_resources(key))
    return render_template('search.jinja2')


@video_blu.route('/subject')
@cross_origin(origins=origins)
def is_archived():
    """
    params: id=<subject_id>
    :return: archived info of the subject
    """
    movie = manager().get_movie(id=request.args.get('id', type=int))
    if movie:
        return archived_result(movie['archived'])
    return fail('Not found')


@video_blu.route('/add')
@cross_origin(origins=origins)
def add():
    try:
        if manager().add_subject(request.args.get('id', type=int)):
            return archived_result(Archived.added)
        return archived_result('Failed to insert')
    except error.HTTPError as e:
        return archived_result(e.reason)


@video_blu.route('/collect')
@cross_origin(origins=origins)
def collect():
    return archived_result(manager().collect_resources(request.args.get('id', type=int)))


@video_blu.route('/play')
@cross_origin(origins=origins)
def play():
    return archived_result(manager().play(request.args.get('id', type=int)))


@video_blu.route('/temp')
@cross_origin(origins=origins)
def archive_temp():
    return archived_result(manager().archive_temp(request.args.get('id', type=int)))


@video_blu.teardown_request
def close_connection(e=None):
    if 'manager' in g and g.manager is not None:
        g.manager.close_connection()
    if e is not None:
        logger.error(e)


def manager():
    if 'manager' not in g:
        global config
        g.manager = VideoManager(config.cdn, config.video_db, config.idm_path, config.api_key, config.cookie)
    return g.manager


def init_manager(config_file):
    global config
    config = read_config_from_py_file(config_file)


def archived_result(result):
    if not result:
        return fail('Failed to update archived')
    if isinstance(result, Archived):
        return success(archived=result.name)
    return fail(result)
