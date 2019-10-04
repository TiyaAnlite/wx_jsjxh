import os
import json
import hashlib

import WXlib

from SQLlib import mainSQL


class wx_hzjx(object):
    def __init__(self, resmod):
        self.resmod = resmod
        self.sql_conf = json.load(
            open(os.path.join("config", "sql_conf.json"), "r"))
        self.wx_conf = json.load(
            open(os.path.join("config", "jsjxh.json"), "r"))
        self.sql = mainSQL(self.sql_conf["host"], self.sql_conf["port"],
                           self.sql_conf["user"], self.sql_conf["password"],
                           self.sql_conf["db"], self.sql_conf["charset"])

    def verify(self, data):
        signature = data.get("signature")
        timestamp = data.get("timestamp")
        nonce = data.get("nonce")
        echostr = data.get("echostr")
        token = self.wx_conf["token"]
        queue = [token, timestamp, nonce]
        queue.sort()
        sha1 = hashlib.sha1()
        map(sha1.update, queue)
        hashcode = sha1.hexdigest()
        if hashcode == signature:
            return echostr, 200
        else:
            return "", 200
