import os
import json
import hashlib
import time
import requests
import urllib
import random
import string

import WXlib

from SQLlib import mainSQL


class Base(object):
    def __init__(self):
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
            params = dict(appid=Appid, secret=key,
                          grant_type="client_credential")
            response = requests.get(
                "https://api.weixin.qq.com/cgi-bin/token?", params=params)
            nowtime = int(time.time())
            resdata = response.json()
            if not resdata["errcode"] == 0:
                raise CodeLabError(
                    "Func:getToken:Wechat return errorcode {}".format(resdata["errcode"]))
            new_token = resdata["access_token"]
            use_time = resdata["expires_in"]
            timeout = nowtime + use_time
            self.sql.adder_single(fulltext_mode=[True], line=["Token", "Timeout"], table="wx", value=[
                                  new_token, timeout], keyword_line=["Appid"], keyword=[Appid])
            return new_token

    def login(self, post_data):
        '''微信OAuth2.0授权登录验证'''
        # 登录并获得授权用户openid
        params = dict(appid=self.wx_conf["appid"], secret=self.wx_conf["secret"],
                      code=post_data["code"], grant_type="authorization_code")
        response = requests.post(
            "https://api.weixin.qq.com/sns/oauth2/access_token?", params=params)
        resdata = response.json()
        if "openid" in resdata:
            openid = resdata["openid"]
        else:
            raise CodeLabError(
                "Func:login:Wechat return errorcode {}".format(resdata["errcode"]))

        # 查询用户信息和授权情况
        linkid = self.sql.finder_single(fulltext_mode=[], table="wxCard", keyword_line=[
                                        "openId"], keyword=[openid], line=["dataId"])  # User Id
        if not linkid:
            return {"code": 403, "message": "Unregisted user"}, 403
        linkid = linkid[0]["dataId"]

        check = self.sql.finder_single(fulltext_mode=[], table=["wxMamger"], keyword_line=[
                                       "cardTable"], keyword=[linkid], line=["dataId"])

        if not check:
            return {"code": 403, "message": "Permission denied"}, 403
        check = check[0]["dataId"]

        # 生成会话密钥，并建立登录会话
        session = ""
        while len(session) < 128:
            session += random.choice(string.ascii_letters +
                                     string.digits)  # 随机128位session生成算法
        self.sql.adder_single(fulltext_mode=[], table="wxMamger", keyword_line=[
                              "dataId"], keyword=[check], line=["session"], value=[session])
        self.logAction(linkid, "onLogin")
        return {"code": 200, "session": session}

    def loginCheck(self, session):
        '''登录态检查'''
        doUser = self.sql.finder_single(fulltext_mode=[], table="wxMamger", keyword_line=[
                                        "session"], keyword=[session], line=["cardTable"])  # User Id
        if not doUser:
            raise CodeLabError({"code": 403, "message": "Permission denied"})
        else:
            doUser = doUser[0]["cardTable"]
            return doUser

    def logAction(self, doUser, action):
        '''记录用户操作日志'''
        nowtime = int(time.time())
        self.sql.adder_single(fulltext_mode=[], table="wxLog", keyword_line=["cardTable", "Action", "timestamp"], keyword=[
                              doUser, action, nowtime], line=["cardTable", "Action", "timestamp"], value=[doUser, action, nowtime])  # Mark Log
        return


class hzjx_card(hzjx_common):
    def decryptCode(self, encrypt_code):
        token = self.getToken()
        data = dict(encrypt_code=encrypt_code)
        while True:
            params = dict(access_token=token)
            response = requests.post(
                "https://api.weixin.qq.com/card/code/decrypt?", params=params, json=data)
            resdata = response.json()
            if resdata["errcode"] == 40014:
                token = self.getToken(force_update=True)
            elif resdata["errcode"] == 0:
                break
            else:
                raise CodeLabError(
                    "Func:decryptCode:Wechat return errorcode {}".format(resdata["errcode"]))
        code = resdata["code"]
        self.sql.adder_single(fulltext_mode=[True], table="wxCard", line=[
                              "cardCode_crypt"], value=[encrypt_code], keyword_line=["cardCode"], keyword=[code])
        return code

    def UserGetCard(self, wpost_data):
        openid = wpost_data.FromUserName
        timestamp = int(wpost_data.CreateTime)
        cardId = wpost_data.rawData.find("CardId").text
        cardCode = int(wpost_data.rawData.find("UserCardCode").text)
        self.sql.adder_single(fulltext_mode=[], table="wxCard", line=["openId", "timestamp", "cardId", "cardCode"], value=[
                              openid, timestamp, cardId, cardCode], keyword_line=["openId", "cardId"], keyword=[openid, cardId])  # 新建并绑定用户的openid和code
        return "success", 200

    def updateMember(self, post_data):
        '''提交会员信息，并更新会员数据库，准备激活'''
        # 第一步：先拉取微信端填写的会员信息
        token = self.getToken()
        ticket_decoded = urllib.parse.unquote(
            post_data["activate_ticket"])  # URLdecode
        data = dict(activate_ticket=ticket_decoded)
        while True:
            params = dict(access_token=token)
            response = requests.post(
                "https://api.weixin.qq.com/card/membercard/activatetempinfo/get?", params=params, json=data)
            resdata = response.json()
            if resdata["errcode"] == 40014:
                token = self.getToken(force_update=True)
            elif resdata["errcode"] == 0:
                break
            else:
                raise CodeLabError(
                    "Func:updateMember:Wechat return errorcode {}".format(resdata["errcode"]))
        for i in resdata["info"]["common_field_list"]:  # 格式化类目
            if i["name"] == "USER_FORM_INFO_FLAG_NAME":  # 姓名
                name = i["value"]
            if i["name"] == "USER_FORM_INFO_FLAG_MOBILE":  # 手机
                phone = i["value"]

        department = False
        for x in resdata["info"]["custom_field_list"]:  # 自定义类目
            if x["name"] == "学号":
                sid = x["value"]
            if x["name"] == "宿舍楼":
                roomfloor = x["value"]
            if x["name"] == "宿舍号":
                room = x["value"]
            if x["name"] == "志愿部门":
                department = x["value"]

        # 第二步：解码加密code
        code_decoded = urllib.parse.unquote(
            resdata["encrypt_code"])  # URLdecode
        code = self.decryptCode(code_decoded)

        # 第三步：查找在库卡数据
        check = self.sql.finder_single(fulltext_mode=[], table="wxCard", line=["dataId"], keyword_line=[
                                       "openId", "cardId", "cardCode"], keyword=[resdata["openid"], resdata["card_id"], code])
        if not check:
            raise CodeLabError("Func:updateMember:Cannot find user's card")
        check = check[0]["dataId"]

        # 第四步：更新新会员信息
        self.sql.adder_single(fulltext_mode=[], table="wxUser", keyword_line=["cardTable"], keyword=[check["dataId"]], line=[
                              "cardTable", "name", "sId", "roomId", "phone", "department"], value=[check["dataId"], name, sid, int(roomfloor + room), phone, department])

        return {"code": 200, "name": name, "sid": sid}, 200

    def doActiveCard(self, code, order_id=0):
        '''调用微信接口激活微信会员卡'''
        # 生成卡号
        while True:
            num = "A0{}0".format(order_id)
            while len(num) < 12:
                num += random.choice(string.digits)
            # 查重
            if not self.sql.finder_single(fulltext_mode=[], table="wxCard", keyword_line=["cardNum"], keyword=[num], line=["dataId"]):
                break

        # 读取学号头，确认有效期
        sid = self.sql.multi_table_find(fulltext_mode=[], table=["wxCard", "wxUser"], bind_key=[
                                        "dataId", "cardTable"], keyword_line=["cardCode"], keyword=[code], line=["sId"])[0]["sId"]
        use_year = 4 - \
            (int(time.strftime("%Y", time.localtime())) - int(str(sid)[:4]))
        start_time = 1567267200
        if use_year == 4:
            end_time = 1694707200
        if use_year == 3:
            end_time = 1663171200
        if use_year == 2:
            end_time = 1631635200
        if use_year == 1:
            end_time = 1600099200

        # 调用API激活
        data = dict(membership_number=num, code=code,
                    activate_begin_time=start_time, activate_end_time=end_time)
        token = self.getToken()
        while True:
            params = dict(access_token=token)
            response = requests.post(
                "https://api.weixin.qq.com/card/membercard/activate?", params=params, json=data)
            resdata = response.json()
            if resdata["errcode"] == 40014:
                token = self.getToken(force_update=True)
            elif resdata["errcode"] == 0:
                break
            else:
                raise CodeLabError(
                    "Func:doActiveCard:Wechat return errorcode {}".format(resdata["errcode"]))
        self.sql.adder_single(fulltext_mode=[], table="wxCard", keyword_line=[
                              "cardCode"], keyword=[code], line=["isActive_wx"], value=[1])
        return


class hzjx_mamger(hzjx_card):

    def cardInfo(self, post_data):
        '''查询卡片信息，传入code已经被解码'''
        try:
            doUser = self.loginCheck(post_data["session"])
        except CodeLabError as err:
            return err.message, 403

        infoData = self.sql.multi_table_find(fulltext_mode=[], table=["wxCard", "wxUser"], bind_key=["dataId", "cardTable"], keyword_line=[
                                             "cardCode_crypt"], keyword=[post_data["code"]], line=["timestamp_reg", "isActive", "isActive_wx", "name", "sId", "roomId", "phone", "department"])
        self.logAction(doUser, "onInfo_code")
        return infoData[0], 200

    def activeCard(self, post_data):
        '''激活卡片，传入code已经被解码'''
        try:
            doUser = self.loginCheck(post_data["session"])
        except CodeLabError as err:
            return err.message, 403

        code = self.sql.finder_single(fulltext_mode=[], table="wxCard", keyword_line="cardCode_crypt", keyword=[
                                      post_data["code"]], line=["cardCode"])[0]["cardCode"]
        self.sql.adder_single(fulltext_mode=[], table="wxCard", keyword_line=[
                              "cardCode"], keyword=code, line=["isActive"], value=[1])
        self.logAction(doUser, "onActive")
        if "order_id" in post_data:
            self.doActiveCard(code, post_data["order_id"])
        else:
            self.doActiveCard(code)
        self.logAction(doUser, "onActive_wx")
        return {"code": 200}, 200


class wx_hzjx(hzjx_mamger):
    def __init__(self):
        Base.__init__(self)
        self.funcRoute = self.funcRoute["HZJX"]

    def eventEnter(self, wpost_data):
        try:
            eval_string = "self." + \
                self.funcRoute[wpost_data.rawData.find(
                    'Event').text] + "(wpost_data)"
            res, code = eval(eval_string)
        except KeyError:
            res = "success"
            code = 200
        return res, code

    def textEnter(self, wpost_data):
        return "success", 200

    def imageEnter(self, wpost_data):
        return "success", 200


class CodeLabError(Exception):
    '''自定义异常类
    获得函数错误信息'''

    def __init__(self, CLmessage):
        self.message = CLmessage

    def __str__(self):
        return self.message
