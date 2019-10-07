import os
import json
import hashlib
import time
import requests

import WXlib

from SQLlib import mainSQL


class Base(object):
    def __init__(self, resmod):
        self.resmod = resmod
        self.sql_conf = json.load(
            open(os.path.join("config", "sql_conf.json"), "r"))
        self.wx_conf = json.load(
            open(os.path.join("config", "jsjxh.json"), "r"))
        self.funcRoute = json.load(
            open(os.path.join("config", "route.json"), "r"))
        self.sql = mainSQL(self.sql_conf["host"], self.sql_conf["port"],
                           self.sql_conf["user"], self.sql_conf["password"],
                           self.sql_conf["db"], self.sql_conf["charset"])


class hzjx_common(Base):
    def verify(self, wget_data):
        signature = wget_data["signature"]
        timestamp = wget_data["timestamp"]
        nonce = wget_data["nonce"]
        echostr = wget_data["echostr"]
        token = self.wx_conf["token"]
        queue = [token, timestamp, nonce]
        queue.sort()
        sha1 = hashlib.sha1()
        sha1.update("".join(queue).encode('utf-8'))
        hashcode = sha1.hexdigest()
        if hashcode == signature:
            return echostr, 200
        else:
            return "", 200

    def getToken(self, force_update=False):
        '''Token获取，检验，存储一体器，自动处理token有效期以及获取
        传入force_update可以强制更新'''
        Appid = self.wx_conf["appid"]
        old_token = self.sql.finder_single(
            fulltext_mode=[True], line=["Timeout", "Token"], table="wx", keyword_line=["Appid"], keyword=[Appid])[0]
        nowtime = int(time.time())
        if int(old_token["Timeout"]) > nowtime and not force_update:
            return old_token["Token"]
        else:
            key = self.wx_conf["secret"]
            params = dict(appid=Appid, secret=key, grant_type="client_credential")
            response = requests.get(
                "https://api.weixin.qq.com/cgi-bin/token?", params=params)
            nowtime = int(time.time())
            resdata = response.json()
            new_token = resdata["access_token"]
            use_time = resdata["expires_in"]
            timeout = nowtime + use_time
            self.sql.adder_single(fulltext_mode=[True], line=["Token", "Timeout"], table="wx", value=[
                                  new_token, timeout], keyword_line=["Appid"], keyword=[Appid])
            return new_token
            

class hzjx_card(Base):
    def UserGetCard(self, wpost_data):
        openid = wpost_data.FromUserName
        timestamp = int(wpost_data.CreateTime)
        cardId = wpost_data.rawData.find("CardId").text
        cardCode = int(wpost_data.rawData.find("UserCardCode").text)
        self.sql.adder_single(fulltext_mode=[], table="wxCard", line=["openId", "timestamp", "cardId", "cardCode"], value=[
                              openid, timestamp, cardId, cardCode], keyword_line=["openId", "cardId"], keyword=[openid, cardId])  # 新建并绑定用户的openid和code
        return "success", 200


class wx_hzjx(hzjx_common):
    def __init__(self, resmod):
        Base.__init__(resmod)
        self.funcRoute = self.funcRoute["HZJX"]

    def eventEnter(self, wpost_data):
        eval_string = "self." + \
            self.funcRoute[wpost_data.rawData.find(
                'Event').text] + "(wpost_data)"
        res, code = eval(eval_string)
        return res, code
