from gevent import monkey, pywsgi
import gevent

import json
import os
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS

from WXlib import receive
import handle
from handle import CodeLabError

app = Flask(__name__)
app_http = Flask(__name__)
CORS(app, resources=r'/*')
CORS(app_http, resources=r'/*')


@app_http.before_request
def https_route():
    if request.url.startswith('http://'):
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)


@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')


@app.route('/')
def index():
    return '<h1>Hello!</h1>'


@app.route('/wx_sock', methods=['POST', 'GET'])
def wechat_socket():
    if request.method == 'POST':
        xml_data = receive.parse_xml(request.get_data())
        res, code = app_router.route(
            target="sock", path=xml_data.MsgType, data=xml_data)  # 传入XML结构对象
        return res, code
    if request.method == 'GET':
        get_data = dict(request.args)
        for k in get_data:
            get_data[k] = get_data[k][0]
        res, code = app_router.route(
            target="sock_get", path=".", data=get_data)  # 传入字典对象
        return res, code


@app.route('/wx_api/<path:app_path>', methods=['POST'])
def codelabApi(app_path):
    if request.method == 'POST':
        data = request.get_json()
    res, code = app_router.route(
        target="api", path=app_path, data=data)
    return jsonify(res), code

@app.route('/interface/<path:app_path>', methods=['GET'])
def userInterface(app_path):
    if request.method == 'GET':
        data = dict(request.args)
        for k in data:
            data[k] = data[k][0]
    res, code = app_router.route(
        target="interface", path=app_path, data=data)
    return res, code

@app.route('/faceCheckIn')
def faceCheckIn():
    return app.send_static_file('checkin.html')


@app.route('/faceCheckIn/MP_verify_BFxk9aicA2tZgujI.txt')
def wxCheck():
    return app.send_static_file('wxCheck.txt')


@app.route('/static/<path:app_path>')
def staticRoute(app_path):
    return app.send_static_file(app_path)


class router(object):
    def __init__(self, route_list):
        self.route_list = route_list

    def route(self, target, path, data):
        try:
            eval_string = self.route_list[target][path] + "(data)"
        except KeyError:
            res = {"code": 404}
            code = 404
        try:
            res, code = eval(eval_string)
        except CodeLabError as err:
            res = {"code": 400, "message": err.message}
            code = 400
            print(err.message)
        return res, code


HZJX = handle.wx_hzjx()
app_router = router(json.load(open(os.path.join("config", "route.json"), "r")))

if __name__ == '__main__':
    monkey.patch_all()
    server_http = pywsgi.WSGIServer(('0.0.0.0', 80), app_http)
    server = pywsgi.WSGIServer(('0.0.0.0', 443),
                               app,
                               keyfile='server.key',
                               certfile='server.crt')
    #server = pywsgi.WSGIServer(('127.0.0.1', 8088), app)
    server.serve_forever()
