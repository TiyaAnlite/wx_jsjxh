import os
import json

from SQLlib import mainSQL

class wx_hzjx(object):
    def __init__(self, resmod):
        self.resmod = resmod
        self.sql_conf = json.load(
            open(os.path.join("config", "sql_conf.json"), "r"))
        self.jitan_conf = json.load(
            open(os.path.join("config", "wx_conf.json"), "r"))
        self.sql = mainSQL(self.sql_conf["host"], self.sql_conf["port"],
                           self.sql_conf["user"], self.sql_conf["password"],
                           self.sql_conf["db"], self.sql_conf["charset"])