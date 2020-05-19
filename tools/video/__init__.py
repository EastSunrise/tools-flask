""" initialization

@Author Kingen
@Date 2020/5/12
"""
import logging
import os
from urllib import error

from flask import Blueprint, request, g, render_template
from flask_cors import cross_origin

from instance.private import video_cdn, idm_path, douban_api_key, Cookie, video_db
from tools.internet.douban import Douban
from tools.video.enums import Status, Archived, Subtype
from .manager import VideoManager

video_blu = Blueprint('video', __name__, url_prefix='/video')

logger = logging.getLogger(__name__)

origins = ['https://movie.douban.com', 'http://localhost:63342', 'http://127.0.0.1:5000']

douban = Douban(douban_api_key)


@video_blu.route('/my')
def my_movies():
    params = request.args.copy()
    params['order_by'] = request.args.get('order_by', default='last_update')
    params['desc'] = request.args.get(
        'desc', default=('desc' if params['order_by'] == 'last_update' or params['order_by'] == 'tag_date' else 'asc'))
    subjects = manager().get_movies(ignore_blank=True, **params)
    return render_template(
        'my.jinja2', subjects=subjects, params=params,
        members={
            'archived': Archived.__members__,
            'status': Status.__members__,
            'subtype': Subtype.__members__
        }
    )


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
        return {
            'id': subject_id,
            'archived': movie['archived'],
            'location': movie['location']
        }
    return {
        'id': subject_id,
        'archived': None,
        'location': None
    }


@video_blu.route('/add')
@cross_origin(origins=origins)
def add():
    subject_id = request.args.get('id', type=int)
    try:
        subject = douban.movie_subject(subject_id)
    except error.HTTPError as e:
        if e.code == 404 and Cookie:
            subject = douban.movie_subject_with_cookie(subject_id, Cookie)
        else:
            return result(False)
    subject['status'] = request.args.get('status', type=Status)
    if subject['status'] is None:
        subject['status'] = 'unmarked'
    subject['tag_date'] = request.args.get('tag_date')
    return result(manager().add_movie(subject))


@video_blu.route('/search')
def search():
    subject_id = request.args.get('id', type=int)
    return render_template('search.jinja2', resources=manager().search_resources(subject_id))


@video_blu.route('/collect')
@cross_origin(origins=origins)
def collect():
    subject_id = request.args.get('id', type=int)
    return {
        'archived': manager().collect_resources(subject_id)
    }


@video_blu.route('/play')
@cross_origin(origins=origins)
def play():
    subject_id = request.args.get('id', type=int)
    movie = manager().get_movie(id=subject_id)
    if movie:
        location = movie['location']
        if movie['subtype'] == 'movie' and os.path.isfile(location):
            os.startfile(location)
            return result(True)
        elif movie['subtype'] == 'tv' and os.path.isdir(location) and len(os.listdir(location)) > 0:
            os.startfile(os.path.join(location, os.listdir(location)[0]))
            return result(True)
    return result(False)


@video_blu.route('/archive')
@cross_origin(origins=origins)
def archive():
    return {
        'archived': manager().archive(request.args.get('id', type=int))
    }


@video_blu.route('/temp')
@cross_origin(origins=origins)
def archive_temp():
    subject_id = request.args.get('id', type=int)
    return {
        'archived': manager().archive_temp(subject_id)
    }


@video_blu.teardown_request
def close_connection(e=None):
    if 'manager' in g and g.manager is not None:
        g.manager.close_connection()


def manager():
    if 'manager' not in g:
        g.manager = VideoManager(video_cdn, video_db, idm_path)
    return g.manager


def result(is_success: bool):
    return {
        'success': is_success
    }
