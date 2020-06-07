""" Enums of video module

@Author Kingen
@Date 2020/5/18
"""

from tools.utils.common import BaseEnum, BaseEnumValue


class Status(BaseEnum):
    unmarked = BaseEnumValue(0, '未标记')
    wish = BaseEnumValue(1, '想看')
    do = BaseEnumValue(2, '在看')
    collect = BaseEnumValue(3, '看过')


class Archived(BaseEnum):
    none = BaseEnumValue(-1, '没有资源')
    added = BaseEnumValue(0, '已添加')
    playable = BaseEnumValue(1, '可播放')
    idm = BaseEnumValue(2, 'IDM')
    downloading = BaseEnumValue(3, '下载中')


class Subtype(BaseEnum):
    movie = BaseEnumValue(0, '电影')
    tv = BaseEnumValue(1, '电视剧')


class Protocol(BaseEnum):
    unknown = BaseEnumValue(0, '未知')
    http = BaseEnumValue(1, 'HTTP/HTTPS')
    ftp = BaseEnumValue(2, 'FTP')
    torrent = BaseEnumValue(3, '种子')
    ed2k = BaseEnumValue(4, 'ed2k')
    magnet = BaseEnumValue(5, '磁力链接')
    pan = BaseEnumValue(6, '百度云')
