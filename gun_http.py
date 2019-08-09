# import multiprocessing
import os
import gevent.monkey
gevent.monkey.patch_all()


debug = False
loglevel = 'info'
bind = '0.0.0.0:80'
pidfile = 'log/gunicorn_http.pid'
logfile = 'log/debug_http.log'

# 启动的进程数
# workers = multiprocessing.cpu_count() * 2 + 1
workers = 1
worker_class = 'gunicorn.workers.ggevent.GeventWorker'

x_forwarded_for_header = 'X-FORWARDED-FOR'
