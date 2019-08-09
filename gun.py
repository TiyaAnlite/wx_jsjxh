# import multiprocessing
import os
import gevent.monkey
gevent.monkey.patch_all()


debug = False
loglevel = 'info'
bind = '0.0.0.0:443'
pidfile = 'log/gunicorn.pid'
logfile = 'log/debug.log'
certfile = 'server.crt'
keyfile = 'server.key'

# 启动的进程数
# workers = multiprocessing.cpu_count() * 2 + 1
workers = 1
worker_class = 'gunicorn.workers.ggevent.GeventWorker'

x_forwarded_for_header = 'X-FORWARDED-FOR'
