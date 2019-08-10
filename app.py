from gevent import monkey, pywsgi
import gevent

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


@app.route('/test', methods=['POST'])
def test():
    if request.method == 'POST':
        return request.data, 200


if __name__ == '__main__':
    monkey.patch_all()
    server_http = pywsgi.WSGIServer(('0.0.0.0', 80), app_http)
    server = pywsgi.WSGIServer(('0.0.0.0', 443),
                               app,
                               keyfile='server.key',
                               certfile='server.crt')
    #server = pywsgi.WSGIServer(('127.0.0.1', 8088), app)
    server.serve_forever()
