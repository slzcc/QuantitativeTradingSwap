#***********************************************
#
#      Filename: redisMethod.py
#
#        Author: shilei@hotstone.com.cn
#   Description: redis utils 方法
#
#        Create: 2022-10-22 10:27:32
# Last Modified: 2022-10-22 10:27:32
#
#***********************************************
import redis


class redisUtils:

    def __init__(self):

        self.client = redis.Redis(host='47.57.13.9', port=6379, decode_responses=True, db=0)

    def setKey(self, key, data, expire=None):
        """
        string 数据
        set 一条数据
        ex – 过期时间（秒）
        px – 过期时间（毫秒）
        nx – 如果设置为True，则只有name不存在时，当前set操作才执行
        xx – 如果设置为True，则只有name存在时，当前set操作才执行
        """
        if expire:
            return self.client.set(key, data, ex=expire)
        else:
            return self.client.set(key, data)

    def getKey(self, key):
        """
        string 数据
        获取 key 内容
        """
        return self.client.get(key)

    def delKey(self, key):
        """
        string 数据
        删除 key
        """
        return self.client.delete(key)

    def setKeyExpire(self, key, expire):
        """
        对 key 设置超时时间
        """
        return self.client.expire(key, expire)

    def lpushKey(self, key, data=None):
        """
        list 数据
        data: 原始请求内容
        """
        return self.client.lpush(key, data)

    def lrangeKey(self, key, start=0, stop=-1):
        """
        list 数据
        """
        return self.client.lrange(key, start, stop)

    def lsetKey(self, key, index=None, data=None):
        """
        list 数据
        """
        return self.client.lset(key, index, data)
    
    def brpopKey(self, key):
        """
        list 数据
        删除 key 最后一个数据
        """
        return self.client.brpop(key)

    def blpopKey(self, key):
        """
        list 数据
        删除 key 最前一个数据
        """
        return self.client.blpop(key)

    def llenKey(self, key):
        """
        list 数据
        获取 list 长度
        """
        return self.client.llen(key)

    def lremKey(self, key, data, index=0):
        """
        list 数据
        移除 key 中索引位置的值
        """
        return self.client.lrem(key, data, index)

    def getKeys(self, keys=None):
        """
        获取 keys 列表
        """
        if keys:
            return self.client.keys(keys)
        else:
            return self.client.keys()

    def delKey(self, key):
        """
        删除某个 key
        """
        return self.client.delete(key)

    def incrKey(self, key):
        """
        自增 key 数据
        """
        return self.client.incr(key)

    def decrKey(self, key):
        """
        自减 key 数据
        """
        return self.client.decr(key)