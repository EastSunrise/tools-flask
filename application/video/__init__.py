""" initialization

@Author Kingen
@Date 2020/5/12
"""
import os

from flask import Blueprint, request
from flask_cors import cross_origin

from application.internet.douban import Douban
from instance.private import video_cdn, idm_path, douban_api_key
from .manager import VideoManager, get_movie, movie_subject, add_movie

video_blu = Blueprint('video', __name__, url_prefix='/video')

origins = ['https://movie.douban.com', 'http://localhost:63342']

douban = Douban(douban_api_key)
manager = VideoManager(video_cdn, idm_path)


@video_blu.route('/<subject_id>')
@cross_origin()
def archived(subject_id):
    """
    params: id=<subject_id>
    :return: archived info of the subject
    """
    subject_id = int(subject_id)
    movie = get_movie(id=subject_id)
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
@cross_origin()
def add():
    subject_id = int(request.args.get('id'))
    cookies = request.args.get('cookies')
    subject = movie_subject(subject_id, douban, cookies)
    if subject is None:
        return result(False)
    subject['status'] = request.args.get('status')
    if subject['status'] is None:
        subject['status'] = 'unmarked'
    subject['tag_date'] = request.args.get('tag_date')
    return result(add_movie(subject))


@video_blu.route('/search')
@cross_origin()
def search():
    subject_id = int(request.args.get('id'))
    return {
        'code': manager.search_resources(subject_id)
    }


@video_blu.route('/<subject_id>/play')
@cross_origin()
def play(subject_id):
    subject_id = int(subject_id)
    movie = get_movie(id=subject_id)
    if movie:
        location = movie['location']
        if movie['subtype'] == 'movie' and os.path.isfile(location):
            os.startfile(location)
            return result(True)
        elif movie['subtype'] == 'tv' and os.path.isdir(location) and len(os.listdir(location)) > 0:
            os.startfile(os.path.join(location, os.listdir(location)[0]))
            return result(True)
    return result(False)


@video_blu.route('/temp')
@cross_origin()
def archive_temp():
    subject_id = int(request.args.get('id'))
    return {
        'code': manager.archive_temp(subject_id)
    }


def result(is_success: bool):
    return {
        'success': is_success
    }
