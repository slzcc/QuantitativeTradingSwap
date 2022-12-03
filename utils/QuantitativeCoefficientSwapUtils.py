#***********************************************
#
#      Filename: main_utils.py
#
#        Author: shilei@hotstone.com.cn
#   Description: main 参数引用
#
#        Create: 2022-10-10 16:53:32
# Last Modified: 2022-10-10 16:53:32
#
#***********************************************

import os
import re
import sys
import argparse
import datetime
import getpass
from contextlib import contextmanager

if sys.version > '3':
    PY3PLUS = True
else:
    PY3PLUS = False

def is_valid_datetime(string):
    try:
        datetime.datetime.strptime(string, "%Y-%m-%d %H:%M:%S")
        return True
    except:
        return False

def parse_args():
    """parse args for binlog2sql"""

    parser = argparse.ArgumentParser(description='Parse Quantitative Trading Swap.', add_help=False)
    connect_setting = parser.add_argument_group('symbol setting')
    connect_setting.add_argument('-k', '--key', dest='key', type=str,
                                 help='凭证 key', default='')
    connect_setting.add_argument('-s', '--secret', dest='secret', type=str,
                                 help='凭证 secret', default='')
    connect_setting.add_argument('-t', '--token', dest='token', type=str,
                                 help='当前任务识别身份', default='')
    parser.add_argument('--help', dest='help', action='store_true', help='help information', default=False)

    return parser

def command_line_args(args):
    need_print_help = False if args else True
    parser = parse_args()
    args = parser.parse_args(args)
    if args.help or need_print_help:
        parser.print_help()
        sys.exit(1)
    if not args.key:
        raise ValueError('缺少用户凭证 key!')
    if not args.secret:
        raise ValueError('缺少用户凭证 secret!')
    if not args.token:
        raise ValueError('缺少用户凭证 secret!')        
    return args

def compare_items(items):
    # caution: if v is NULL, may need to process
    (k, v) = items
    if v is None:
        return '`%s` IS %%s' % k
    else:
        return '`%s`=%%s' % k

def fix_object(value):
    """Fixes python objects so that they can be properly inserted into SQL queries"""
    if isinstance(value, set):
        value = ','.join(value)
    if PY3PLUS and isinstance(value, bytes):
        try:
            return value.decode('utf-8')
        except:
            return value.decode("ISO-8859-2")
    elif not PY3PLUS and isinstance(value, unicode):
        return value.encode('utf-8')
    else:
        return value

