""" Thunder, IDM, and custom downloader

@Author Kingen
@Date 2020/5/13
"""
import os
import threading
import time
from subprocess import run, CompletedProcess
from urllib.request import urlopen, Request

from win32com.client import Dispatch

from . import logger
from .spider import quote_url, pre_download, base_headers


class IDM:
    """
    Use local IDM to add_task resources by calling command lines.
    """

    def __init__(self, client_path, default_path='') -> None:
        self.__client = client_path  # full path is required if not added to environment paths of system
        self.default_path = default_path

    @property
    def default_path(self):
        return self.__default_path

    @default_path.setter
    def default_path(self, path):
        if not os.path.isdir(path):
            path = './'
        self.__default_path = path

    def add_task(self, url, path='', filename='', silent=False, queue=True):
        """
        :param url: only http/https
        :param path: local path to save the file. self.default_path will be used if specific path doesn't exist.
        :param filename: local file name. Basename will be truncated if filename contains '/'
        :param silent: whether to turn on the silent mode when IDM does't ask any questions.
                    When it occurs to duplicate urls, there is a warning dialog if silent is False.
                    Otherwise, add a duplicate task whose downloaded file will replace the former one.
        :param queue: whether to add this to add_task queue and not to start downloading automatically
        :return:
        """
        commands = [self.__client, '/d', quote_url(url)]
        if not os.path.isdir(path):
            path = self.default_path
        if path is not None:
            commands += ['/p', path]
        if filename != '':
            filename = os.path.basename(filename)
            root, ext = os.path.splitext(filename)
            if ext == '':
                ext = os.path.splitext(url)[1]
            commands += ['/f', root + ext]
        if silent:
            commands.append('/n')
        if queue:
            commands.append('/a')
        return self.__capture_output(run(commands, capture_output=True, timeout=30, check=True))

    def start_queue(self):
        return self.__capture_output(run([self.__client, '/s']))

    @staticmethod
    def __capture_output(cp: CompletedProcess):
        if cp.stdout != b'':
            logger.info(cp.stdout)
        if cp.returncode != 0:
            logger.error('Error command: %s', ' '.join(cp.args))
            logger.error(cp.stderr)
        return cp.returncode


class Downloader:
    """
    A custom downloader for downloading files through urls
    Speed up the process with multi-threads if the file size is larger than self.bound_size
    """

    def __init__(self, cdn, thread_count=4) -> None:
        self.cdn = cdn
        self.bound_size = 1024 * 1024 * 8  # 1MB
        self.thread_count = thread_count

    @property
    def cdn(self):
        return self.__cdn

    @cdn.setter
    def cdn(self, cdn):
        if not os.path.isdir(cdn):
            self.__cdn = './'

    @property
    def bound_size(self):
        return self.__thread_size

    @bound_size.setter
    def bound_size(self, thread_size):
        if thread_size > 0:
            self.__thread_size = thread_size

    @property
    def thread_count(self):
        return self.__thread_count

    @thread_count.setter
    def thread_count(self, thread_count):
        if 1 < thread_count < 20:
            self.__thread_count = thread_count

    def download(self, url, path='', filename=''):
        """
        Download a file by the url
        Use multi threads to download if
        :return: (code, msg)
        """
        if not os.path.isdir(path):
            path = self.cdn
        if filename == '':
            filename = os.path.basename(url.rstrip('/'))
        filepath = os.path.join(path, filename)
        if os.path.isfile(filepath):
            return 409, 'File exists: %s' % filepath
        code, msg, args = pre_download(url)
        if code != 200:
            return code, msg
        total_size = args['size']

        # single thread to download small files
        if total_size <= self.bound_size:
            logger.info('Downloading from %s to %s', url, filepath)
            with open(filepath, 'wb') as fp:
                with urlopen(Request(quote_url(url), headers=base_headers, method='GET')) as r:
                    fp.write(r)
            logger.info('Success downloading: %s', filepath)
            return 200, 'OK'

        thread_size = total_size // self._DownloadThread.block_size + 1
        threads = []
        for i in range(self.thread_count):
            fp = open(filepath, 'wb')
            thread = self._DownloadThread(url, i * thread_size, thread_size, fp)
            threads.append(thread)
            thread.start()

        queue = [(time.time(), 0)] * 10
        total_size_str = self.__size2str(total_size)
        while not all([t.done for t in threads]):
            done_size = sum([t.done_size for t in threads])
            queue.pop(0)
            queue.append((time.time(), done_size))
            current_speed = (queue[-1][1] - queue[0][1]) / (queue[-1][0] - queue[0][0])
            left_time = (total_size - done_size) // current_speed
            print('\rDownloading: %s/s, %.2f%%, %s, %s' % (self.__size2str(current_speed), done_size / total_size, self.__time2str(left_time), total_size_str),
                  end='', flush=True)
            time.sleep(0.1)

    @staticmethod
    def __size2str(size):
        for u in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return '%.2f %s' % (size, u)
            size /= 1024
        return '%.2f TB' % size

    @staticmethod
    def __time2str(seconds):
        m, s = divmod(seconds, 60)
        time_str = '%d s' % s
        if m > 0:
            h, m = divmod(m, 60)
            time_str = '%d min %s' % (m, time_str)
            if h > 0:
                time_str = '%d h %s' % (h, time_str)
        return time_str

    class _DownloadThread(threading.Thread):

        block_size = 1024

        def __init__(self, url, start: int, size: int, fp):
            super().__init__()
            self.__url = url
            self.__fp = fp
            self.__fp.seek(start)
            self.__start = start
            self.__size = size
            self.__done_size = 0

        def run(self) -> None:
            with urlopen(self.__url) as response:
                response.seek(self.__start)
                while self.done < self.__size:
                    block = response.read(self.block_size)
                    if block is None or len(block) == 0:
                        break
                    self.__fp.write(block)
                    self.__done_size += len(block)
                self.__fp.close()

        @property
        def done_size(self):
            return self.__done_size

        @property
        def done(self):
            return self.done_size >= self.__size


class Thunder:
    """
    Call local Thunder COM object to add_task resources by using apis of win32com
    Version of Thunder needs to 9/X.
    """

    def __init__(self) -> None:
        self.__client = Dispatch('ThunderAgent.Agent64.1')

    def add_task(self, url, filename, refer_url=''):
        """
        add add_task task
        :param filename: basename of target file. It will be completed automatically if an extension isn't included.
            This is valid only when popping up a add_task panel.
        :param refer_url: netloc referred to
        :return:
        """
        self.__client.addTask(url, filename, '', '', refer_url, -1, 0, -1)

    def commit_tasks(self):
        """
        It is configurable in the Settings whether to pop up a add_task panel.
        """
        return self.__client.commitTasks()

    def cancel_tasks(self):
        """
        cancel all tasks added by self.add_task()
        """
        self.__client.cancelTasks()
