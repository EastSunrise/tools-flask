"""Common utilities

@Author Kingen
@Date 2020/4/12
"""

CHINESE_NUMERALS = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']


def merge_dict(dict1: dict, dict2: dict):
    """
    Merge dict2 into dict1 recursively
    """
    for key, value in dict2.values():
        if key in dict1 and isinstance(value, dict) and isinstance(dict1[key], dict):
            merge_dict(dict1[key], value)
        else:
            dict1[key] = value


def num2chinese(num: int) -> str:
    """
    transfer Arabic numerals to Chinese numerals
    """
    if num <= 0 or num > 20:
        raise ValueError
    if num <= 10:
        return CHINESE_NUMERALS[num]
    if num == 20:
        return '二十'
    return '十' + CHINESE_NUMERALS[num - 10]


def cmp_strings(strings: list):
    """
    compare at least 2 strings with same length.
    :return: list of common parts, lists of different parts for string in strings separately
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
