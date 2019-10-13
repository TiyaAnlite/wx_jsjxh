import os
import json
import hashlib
import time
import requests
import urllib
import random
import string

from WXlib import reply

from SQLlib import mainSQL


class Base(object):
    def __init__(self):
        self.sql_conf = json.load(
            open(os.path.join("config", "sql_conf.json"), "r"))
        self.wx_conf = json.load(
            open(os.path.join("config", "jsjxh.json"), "r"))
        self.funcRoute = json.load(
            open(os.path.join("config", "route.json"), "r"))
        self.msgmod = json.load(
            open(os.path.join("config", "msgMod.json"), "r", encoding='utf-8'))
        self.sql = mainSQL(self.sql_conf["host"], self.sql_conf["port"],
                           self.sql_conf["user"], self.sql_conf["password"],
                           self.sql_conf["db"], self.sql_conf["charset"])
        self.xmlMsg = reply.Msg()


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
            if "errcode" in resdata:
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

        check = self.sql.finder_single(fulltext_mode=[], table="wxMamger", keyword_line=[
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
        return {"code": 200, "session": session}, 200

    def loginCheck(self, session):
        '''登录态检查'''
        doUser = self.sql.finder_single(fulltext_mode=[], table="wxMamger", keyword_line=[
                                        "session"], keyword=[session], line=["cardTable"])  # User Id
        if not doUser:
            raise CodeLabError({"code": 403, "message": "Permission denied"})
        else:
            doUser = doUser[0]["cardTable"]
            return doUser

    def loginCheck_openid(self, openid):
        '''登录态检查(仅openid检查)
        返回的元组包含运行结果和数据'''
        doUser = self.sql.finder_single(fulltext_mode=[], table="wxCard", keyword_line=[
                                        "openId"], keyword=[openid], line=["dataId"])  # User Id
        if not doUser:
            return -1, False
        doUser = doUser[0]["dataId"]

        check = self.sql.finder_single(fulltext_mode=[], table="wxMamger", keyword_line=[
                                       "cardTable"], keyword=[doUser], line=["dataId"])

        if not check:
            return -2, False
        else:
            return 0, doUser

    def logAction(self, doUser, action):
        '''记录用户操作日志'''
        nowtime = int(time.time())
        self.sql.adder_single(fulltext_mode=[], table="wxLog", keyword_line=["cardTable", "Action", "timestamp_check"], keyword=[
                              doUser, action, nowtime], line=["cardTable", "Action", "timestamp_check"], value=[doUser, action, nowtime])  # Mark Log
        return

    def subscribe(self, wpost_data):
        '''关注自动回复消息'''
        xmlImg = reply.TextMsg(wpost_data.FromUserName, wpost_data.ToUserName,
                               "欢迎来到计协的自留地！\nヾ(≧▽≦*)o")
        return xmlImg.send(), 200

    def doGetToken(self, post_data):
        doUser = self.loginCheck(post_data["session"])
        self.getToken(force_update=True)
        self.logAction(doUser, "updateSession")
        return {"code": 200}, 200


class hzjx_msg(hzjx_common):
    def modPush(self, model, model_data, openid):
        '''推送模版消息'''
        # 填入模版
        msg = self.msgmod[model]
        msg["touser"] = openid
        for i in model_data:
            msg["data"][i]["value"] = model_data[i]

        token = self.getToken()
        while True:
            params = dict(access_token=token)
            response = requests.post(
                "https://api.weixin.qq.com/cgi-bin/message/template/send?", params=params, json=msg)
            resdata = response.json()
            if resdata["errcode"] == 40014:
                token = self.getToken(force_update=True)
            elif resdata["errcode"] == 0:
                break
            else:
                raise CodeLabError(
                    "Func:modPush:Wechat return errorcode {}".format(resdata["errcode"]))
        return


class hzjx_func(hzjx_msg):
    def faceCheckIn(self, post_data, inputType="code"):
        '''面试签到功能，兼容CardNumber直签'''
        # 登录并获得授权用户openid(默认模式)
        if inputType == "code":
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
        elif inputType == "CardNumber":
            openid = self.sql.finder_single(fulltext_mode=[], table="wxCard", keyword_line=[
                                            "cardNum"], keyword=[post_data["CardNumber"]], line=["openId"])[0]["openId"]

        # 签入
        uid = self.sql.finder_single(fulltext_mode=[], table="wxCard", keyword_line=[
                                     "openId"], keyword=[openid], line=["dataId"])
        if uid:
            uid = uid[0]["dataId"]
        else:
            return {"code": -2}, 400  # 未领卡
        name = self.sql.finder_single(fulltext_mode=[], table="wxUser", keyword_line=[
            "cardTable"], keyword=[uid], line=["name"])
        if name:
            name = name[0]["name"]
        else:
            return {"code": -1}, 400  # 未填信息
        self.sql.adder_single(fulltext_mode=[], table="wxCheck", keyword_line=["cardTable"], keyword=[
                              uid], line=["cardTable", "checkIn", "checkOut"], value=[uid, 1, 0])

        # 推送信息
        queue_num = self.sql.finder_single(fulltext_mode=[], table="wxCheck", keyword_line=[
                                           "cardTable"], keyword=[uid], line=["dataId"])[0]["dataId"]  # 序号
        people = self.sql.finder_single(fulltext_mode=[], table="wxCheck", keyword_line=[
            "checkIn", "checkOut"], keyword=[1, 0], line=["dataId"])  # 前方人数
        if people:
            people = len(people)
        else:
            people = 0
        req_data = dict(keyword1=name, keyword2=time.strftime(
            "%Y-%m-%d %H:%M", time.localtime()), remark="你的序号是第{}号，预计前方还有{}人".format(queue_num, people))
        self.modPush(model="check_in", model_data=req_data, openid=openid)

        # 兼容接口回传数据
        if inputType == "CardNumber":
            return dict(queue_num=queue_num, Name=name)
        else:
            return {"code": 200}, 200

    def faceCheckIn_scan(self, scanData):
        '''签到功能-扫码推兼容接口'''
        # 权限检查
        status, doUser = self.loginCheck_openid(scanData["FromUserName"])
        if not status == 0:
            if status == -1:
                res = reply.TextMsg(
                    scanData["FromUserName"], scanData["ToUserName"], content="该账户还未领取会员卡")
            if status == -2:
                res = reply.TextMsg(
                    scanData["FromUserName"], scanData["ToUserName"], content="该账户没有操作权限")
            return res.send(), 200

        # 接口兼容转换
        reqData = dict(CardNumber=scanData["ScanResult"])
        callback = self.faceCheckIn(reqData, inputType="CardNumber")
        content = "[签到操作完成]\n序号：{queue_num}\n姓名：{Name}"
        res = reply.TextMsg(
            scanData["FromUserName"], scanData["ToUserName"], content=content.format(**callback))

        self.logAction(doUser, "faceCheckIn_scan")
        return res.send(), 200


class hzjx_card(hzjx_msg):
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
            elif resdata["errcode"] == 40056:
                raise CodeLabError("Func:doActiveCard:40056")
            elif resdata["errcode"] == 0:
                break
            else:
                raise CodeLabError(
                    "Func:decryptCode:Wechat return errorcode {}".format(resdata["errcode"]))
        code = resdata["code"]
        self.sql.adder_single(fulltext_mode=[True], table="wxCard", line=[
                              "cardCode_crypt"], value=[encrypt_code], keyword_line=["cardCode"], keyword=[code])
        return code

    def sendCardMsg(self, wpost_data):
        '''触发客服消息为用户发卡'''
        openid = wpost_data.FromUserName
        token = self.getToken()
        data = dict(touser=openid, msgtype="wxcard", wxcard=dict(
            card_id="pYABYsxX1J9OO7dlcPocD35EW7T4"))
        while True:
            params = dict(access_token=token)
            response = requests.post(
                "https://api.weixin.qq.com/cgi-bin/message/custom/send?", params=params, json=data)
            resdata = response.json()
            if resdata["errcode"] == 40014:
                token = self.getToken(force_update=True)
            elif resdata["errcode"] == 0:
                break
            else:
                raise CodeLabError(
                    "Func:sendCardMsg:Wechat return errorcode {}".format(resdata["errcode"]))
        return self.xmlMsg.send(), 200

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
        sid = False  # 学号不再是必填项
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
            post_data["encrypt_code"])  # URLdecode
        code = self.decryptCode(code_decoded)

        # 第三步：查找在库卡数据
        check = self.sql.finder_single(fulltext_mode=[], table="wxCard", line=["dataId"], keyword_line=[
                                       "openId", "cardId", "cardCode"], keyword=[post_data["openid"], post_data["card_id"], code])
        if not check:
            raise CodeLabError("Func:updateMember:Cannot find user's card")
        check = check[0]["dataId"]

        # 第四步：更新新会员信息
        if sid:
            self.sql.adder_single(fulltext_mode=[], table="wxUser", keyword_line=["cardTable"], keyword=[check], line=[
                "cardTable", "name", "sId", "roomId", "phone", "department"], value=[check, name, sid, int(roomfloor + room), phone, department])

            return {"code": 200, "name": name, "sid": sid}, 200
        else:
            self.sql.adder_single(fulltext_mode=[], table="wxUser", keyword_line=["cardTable"], keyword=[check], line=[
                "cardTable", "name", "roomId", "phone", "department"], value=[check, name, int(roomfloor + room), phone, department])

            return {"code": 200, "name": name}, 200

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
        self.sql.adder_single(fulltext_mode=[], table="wxCard", keyword_line=[
                              "cardCode"], keyword=[code], line=["cardNum"], value=[num])

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
            elif resdata["errcode"] == 40056:
                raise CodeLabError("Func:doActiveCard:40056")
            elif resdata["errcode"] == 0:
                break
            else:
                raise CodeLabError(
                    "Func:doActiveCard:Wechat return errorcode {}".format(resdata["errcode"]))
        self.sql.adder_single(fulltext_mode=[], table="wxCard", keyword_line=[
                              "cardCode"], keyword=[code], line=["isActive_wx"], value=[1])

        # 发送激活信息
        get_data = self.sql.multi_table_find(fulltext_mode=[], table=["wxCard", "wxUser"], bind_key=[
            "dataId", "cardTable"], keyword_line=["cardCode"], keyword=[code], line=["openId", "name", "phone"])[0]
        send_data = dict(
            keyword1=get_data["name"], keyword2=get_data["phone"], keyword3=num)
        self.modPush(model="new_member", model_data=send_data,
                     openid=get_data["openId"])
        return

    def WXupdateMember(self, get_data):
        '''会员信息更新GET兼容接口
        对于之前未成功激活会员会自动激活'''
        # 对于提交的数据，先进行检查
        token = self.getToken()
        ticket_decoded = urllib.parse.unquote(
            get_data["activate_ticket"])  # URLdecode
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
                return "<h1>信息提交失败：内部错误</h1><h2>Func:WXupdateMember:Wechat return errorcode {}</h2>".format(resdata["errcode"]), 200
        for x in resdata["info"]["custom_field_list"]:  # 自定义类目
            if x["name"] == "宿舍号":
                room = x["value"]
        try:
            int(room)
        except ValueError:
            return "<h1>信息提交失败：宿舍号'{}'不是纯数字</h1><h2>宿舍号只能是三位数门牌号（不包括宿舍楼）</h2>".format(room), 200
        if not len(room) == 3:
            return "<h1>信息提交失败：{}不是三位数门牌号</h1><h2>宿舍号只能是三位数门牌号（不包括宿舍楼）</h2>".format(room), 200

        # 内部调用原始接口进行上传
        try:
            res, code = self.updateMember(get_data)
            del res
        except CodeLabError as err:
            return "<h1>信息提交失败：内部错误</h1><h2>{}</h2>".format(err.message), 200

        # 若符合条件，将会自动激活(适用于完善信息)
        code_decoded = urllib.parse.unquote(
            get_data["encrypt_code"])  # URLdecode
        try:
            code = self.decryptCode(code_decoded)
        except CodeLabError as err:
            if err.message == "Func:doActiveCard:40056":
                return "<h1>信息提交失败：你的原始卡片信息似乎有问题</h1><h2>请删除卡片后重新领取</h2>", 200
            else:
                return "<h1>信息提交失败：内部错误</h1><h2>{}</h2>".format(err.message), 200
        check = self.sql.finder_single(fulltext_mode=[], table="wxCard", keyword_line=["cardCode"], keyword=[code], line=["isActive", "timestamp"])[0]
        if check["isActive"]:
            order = 0
            if check["timestamp"] < 1570618800:
                order = 1
            try:
                self.doActiveCard(code, order_id=order)
            except CodeLabError as err:
                if err.message == "Func:doActiveCard:40056":
                    return "<h1>信息提交失败：你的原始卡片信息似乎有问题</h1><h2>请删除卡片后重新领取</h2>", 200
                else:
                    return "<h1>信息提交失败：内部错误</h1><h2>{}</h2>".format(err.message), 200
            return "<h1>自助激活成功，请留意下发通知</h1>", 200
        else:
            return "<h1>信息完善完成</h1>", 200

        


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

        code = self.sql.finder_single(fulltext_mode=[], table="wxCard", keyword_line=["cardCode_crypt"], keyword=[
                                      post_data["code"]], line=["cardCode"])[0]["cardCode"]
        self.sql.adder_single(fulltext_mode=[], table="wxCard", keyword_line=[
                              "cardCode"], keyword=[code], line=["isActive"], value=[1])
        self.logAction(doUser, "onActive")
        if "order_id" in post_data:
            self.doActiveCard(code, post_data["order_id"])
        else:
            self.doActiveCard(code)
        self.logAction(doUser, "onActive_wx")
        return {"code": 200}, 200

    def getFaceList(self, post_data):
        '''签到组件查询功能'''
        try:
            self.loginCheck(post_data["session"])
        except CodeLabError as err:
            return err.message, 403

        resdata = self.sql.multi_table_find(fulltext_mode=[], table=["wxCheck", "wxUser"], bind_key=["cardTable", "cardTable"], keyword_line=[
                                            "checkIn", "checkOut"], keyword=[1, 0], line=["wxCheck.dataId", "name", "department"])
        return resdata, 200

    def faceCheckOut(self, post_data):
        '''签出功能'''
        try:
            doUser = self.loginCheck(post_data["session"])
        except CodeLabError as err:
            return err.message, 403

        self.sql.adder_single(fulltext_mode=[], table="wxCheck", keyword_line=["dataId"], keyword=[
                              post_data["checkid"]], line=["checkIn", "checkOut"], value=[1, 1])
        self.logAction(doUser, "faceCheckOut")
        return {"code": 200}, 200

    def getFaceInfo(self, post_data):
        '''查询面试信息'''
        try:
            self.loginCheck(post_data["session"])
        except CodeLabError as err:
            return err.message, 403

        if post_data["checkid"] == 0:
            resdata = self.sql.multi_table_find(fulltext_mode=[], table=["wxCheck", "wxUser"], bind_key=["cardTable", "cardTable"], keyword_line=[
                                                "checkIn", "checkOut"], keyword=[1, 0], line=["wxCheck.dataId", "name", "department"])
        else:
            resdata = self.sql.multi_table_find(fulltext_mode=[], table=["wxCheck", "wxUser"], bind_key=["cardTable", "cardTable"], keyword_line=[
                                                "wxCheck.dataId", "checkIn", "checkOut"], keyword=[post_data["checkid"], 1, 0], line=["wxCheck.dataId", "name", "department"])
        return resdata, 200


class wx_hzjx(hzjx_func, hzjx_mamger):
    def __init__(self):
        Base.__init__(self)
        self.funcRoute = self.funcRoute["HZJX"]
        self.scanRoute = self.funcRoute["ScanPush"]
        self.clickRoute = self.funcRoute["ClickEvent"]

    def eventEnter(self, wpost_data):
        '''二级微信事件路由'''
        try:
            eval_string = "self." + \
                self.funcRoute[wpost_data.Event] + "(wpost_data)"
            res, code = eval(eval_string)
        except KeyError:
            res = "success"
            code = 200
        return res, code

    def textEnter(self, wpost_data):
        return self.xmlMsg.send(), 200

    def imageEnter(self, wpost_data):
        return self.xmlMsg.send(), 200

    def scanPush(self, wpost_data):
        '''扫码推事件细分路由'''
        try:
            scanData = dict(FromUserName=wpost_data.FromUserName)
            scanData["ToUserName"] = wpost_data.ToUserName
            scanData["ScanResult"] = wpost_data.rawData.find(
                'ScanCodeInfo').find('ScanResult').text
            EventKey = wpost_data.rawData.find('EventKey').text
            eval_string = "self." + \
                self.scanRoute[EventKey] + "(scanData)"
            res, code = eval(eval_string)
        except KeyError:
            res = "success"
            code = 200
        return res, code

    def clickEvent(self, wpost_data):
        '''点击事件细分路由'''
        try:
            EventKey = wpost_data.rawData.find('EventKey').text
            eval_string = "self." + \
                self.clickRoute[EventKey] + "(wpost_data)"
            res, code = eval(eval_string)
        except KeyError:
            res = "success"
            code = 200
        return res, code


class CodeLabError(Exception):
    '''自定义异常类
    获得函数错误信息'''

    def __init__(self, CLmessage):
        self.message = CLmessage

    def __str__(self):
        return self.message
