from gevent import monkey, pywsgi
import gevent

import json
from flask import Flask, request, jsonify, redirect

import WXlib

app = Flask(__name__)
app_http = Flask(__name__)


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


@app.route('/wx_sock')
def wechat_socket(locat):
    if request.method == 'POST':
        post_data = request.get_json()
        res, code = app_router.route(
            target="sock", path=".", data=post_data)
        return jsonify(res), code


class router(object):
    def __init__(self, route_list):
        self.route_list = route_list

    def route(self, target, path, data):
        eval_string = self.route_list[target][path] + "(data)"
        res, code = eval(eval_string)
        return res, code


app_router = router(json.load(open("config/route.json", "r")))

if __name__ == '__main__':
    monkey.patch_all()
    server_http = pywsgi.WSGIServer(('0.0.0.0', 80), app_http)
    server = pywsgi.WSGIServer(('0.0.0.0', 443),
                               app,
                               keyfile='server.key',
                               certfile='server.crt')
    #server = pywsgi.WSGIServer(('127.0.0.1', 8088), app)
    server.serve_forever()
