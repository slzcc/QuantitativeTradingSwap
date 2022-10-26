#***********************************************
#
#      Filename: toolsMethod.py
#
#        Author: shilei@hotstone.com.cn
#   Description: tools 方法
#
#        Create: 2022-10-26 16:30:32
# Last Modified: 2022-10-26 16:30:32
#
#***********************************************
from decimal import Decimal

def checkListDetermine(llist, determine, count=0, setp=0, length=1):
    """
    获取 列表 中的参数值是否可以得到 determine 的值

    :param   llist       # 传入一个列表 (不区分 float 或 or)
    :param   determine   # 判断值, 在列表中获取与此值相等的索引位
    :return  (False/True, [])
    """
    if len(llist) == length:
        return False, [], []
    if len(llist) -1 < setp:
        setp = 0
        length += 1
    if count == 0:
        _checkType = False
        for index, item in enumerate(llist):
            if item == determine:
                return True, [index], [item]
        if not _checkType:
            return checkListDetermine(llist, determine, count=count + 1)
    else:
        _checkType = False
        _number = 0.0
        _index = []
        _item = []
        for index, item in enumerate(llist[setp::length]):
            _number = Decimal(str(item)) + Decimal(str(_number))
            _index.append(index + setp + length)
            _item.append(item)
            if _number == Decimal(str(determine)):
                return True, _index, _item
        if not _checkType:
            return checkListDetermine(llist, determine, count=count, setp=setp + 1, length=length)