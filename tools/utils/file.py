""" Utilities for file operations

@Author Kingen
@Date 2020/5/14
"""
import hashlib
import os

from win32comext.shell import shell
from win32comext.shell.shellcon import FO_DELETE, FOF_ALLOWUNDO, FO_COPY

from . import logger

st_blksize = 1048576  # 1MB


def copy(src, dst):
    """
    Copy a big file
    :return:
    """
    if os.path.isfile(dst):
        logger.warning('File exists: %s', dst)
        return 1, 'exists'
    src_md5 = get_md5(src)
    logger.info('Copy file from %s to %s', src, dst)
    code, msg = shell_file_operation(0, FO_COPY, src, dst, FOF_ALLOWUNDO)
    if code != 0:
        logger.error('Code: %d, msg: %s', code, msg)
        return code, msg
    if get_md5(dst) != src_md5:
        logger.error('File corrupted while copying')
        return 2, 'corrupted'
    return 0, 'ok'


def get_md5(path, block_size=st_blksize):
    """
    Get the md5 value of the file.
    """
    md5obj = hashlib.md5()
    with open(path, 'rb') as fp:
        read_size = 0
        size = os.path.getsize(path)
        while True:
            block = fp.read(block_size)
            read_size += block_size
            print('\rComputing md5: %.2f%%' % (read_size * 100 / size), end='', flush=True)
            if block is None or len(block) == 0:
                print()
                break
            md5obj.update(block)
        md5value = md5obj.hexdigest()
        return md5value


def delete_file(filepath, undo: bool):
    if undo:
        logger.info('Delete to recycle bin: %s', filepath)
        return shell_file_operation(0, FO_DELETE, filepath, None, FOF_ALLOWUNDO)
    logger.info('Delete file: %s', filepath)
    return os.remove(filepath)


def shell_file_operation(file_handle, func, p_from, p_to, flags, name_dict=None, progress_title=None):
    """

    :param file_handle:
    :param func: FO_COPY/FO_RENAME/FO_MOVE/FO_DELETE
    :param p_from:
    :param p_to:
    :param flags: FOF_FILESONLY | FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI
                    | FOF_RENAMEONCOLLISION | FOF_SILENT | FOF_WANTMAPPINGHANDLE
    :param name_dict: new_filepath-old_filepath dict
    :param progress_title: title of progress dialog
    :return:
    """
    code = shell.SHFileOperation((file_handle, func, p_from, p_to, flags, name_dict, progress_title))[0]
    if code == 0:
        return 0, 'OK'
    if code == 2:
        return 2, 'File Not Found'
    return code, 'Unknown Error'
