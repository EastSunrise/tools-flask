"""Common utilities

@Author Kingen
@Date 2020/4/12
"""
import types
from enum import Enum, unique


def read_config_from_py_file(filepath):
    d = types.ModuleType("config")
    d.__file__ = filepath
    try:
        with open(filepath, mode="rb") as config_file:
            exec(compile(config_file.read(), filepath, "exec"), d.__dict__)
    except IOError as e:
        e.strerror = "Unable to load configuration file (%s)" % e.strerror
        raise
    return d


def cmp_strings(strings: list):
    """
    compare at least 2 strings with same length.
    :return: list of common parts, lists of different parts for string in strings separately
        For example, ['abc02lkj', 'abd04kjj']
        return ['ab', '0', 'j'], [['c', '2lk'], ['d', '4kj']]
    """
    if strings is None or len(strings) < 2 or any((x is None or len(x) == 0 or len(x) != len(strings[0])) for x in strings):
        raise ValueError
    commons = ['']
    diff = [[] for i in range(len(strings))]
    last_common = True
    first_str: str = strings[0]
    for i in range(len(first_str)):
        if any(x[i] != first_str[i] for x in strings):
            if last_common:
                for d in diff:
                    d.append('')
                last_common = False
            for j, d in enumerate(diff):
                d[-1] += strings[j][i]
        else:
            if not last_common:
                commons.append('')
                last_common = True
            commons[-1] += first_str[i]
    return commons, diff


@unique
class BaseEnum(Enum):
    def to_code(self) -> int:
        return self.value.code

    def from_code(self, code):
        if code is None:
            return None
        if not isinstance(code, int):
            code = int(code)
        for m in self.__class__.__members__.values():
            if m.value.code == code:
                return m
        raise ValueError('Unknown code %d for %s' % (code, self.__class__.__name__))

    @staticmethod
    def from_name(clazz, name):
        if name is None:
            return None
        for n, m in clazz.__members__.items():
            if n == name:
                return m
        raise ValueError('Unknown name %s for %s' % (name, clazz))


class BaseEnumValue:

    def __init__(self, code: int, title: str) -> None:
        self.code = code
        self.title = title


def fail(msg: str):
    return {
        'success': False,
        'msg': msg
    }


def success(**kwargs):
    return {'success': True, **kwargs}
