""" Video views

@Author Kingen
@Date 2020/5/13
"""
import os

from flask import request
from flask_cors import cross_origin

from . import get_movie, add_subject, manager, video_blu


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
    cookie = request.args.get('cookie')  # todo cookie
    return result(add_subject(subject_id, cookie))


@video_blu.route('/search')
@cross_origin()
def search():
    subject_id = int(request.args.get('id'))
    cookie = request.args.get('cookie')  # todo cookie
    return {
        'code': manager.search_resources(subject_id, cookie)
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
def temp():
    subject_id = int(request.args.get('id'))
    return {
        'code': manager.archive_temp(subject_id)
    }


def result(is_success: bool):
    return {
        'success': is_success
    }
