""" Enums of video module

@Author Kingen
@Date 2020/5/18
"""
from enum import Enum

from tools.utils.common import BaseEnum


class Status(Enum):
    unmarked = BaseEnum(0, '未标记')
    wish = BaseEnum(1, '想看')
    do = BaseEnum(2, '在看')
    collect = BaseEnum(3, '看过')


class Archived(Enum):
    none = BaseEnum(-1, '没有资源')
    added = BaseEnum(0, '已添加')
    playable = BaseEnum(1, '可播放')
    idm = BaseEnum(2, 'IDM')
    downloading = BaseEnum(3, '下载中')
