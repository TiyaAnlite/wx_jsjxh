import copy

import pymysql


class mainSQL(object):
    def __init__(self, host, port, user, password, database, charset):
        '''MySQL核心服务'''
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.charset = charset
        self.db = pymysql.connect(host=self.host,
                                  port=self.port,
                                  user=self.user,
                                  passwd=self.password,
                                  db=self.database,
                                  charset=self.charset)

    def find(self, mode, line, table, keyword_line, keyword):
        '''搜索数据
        模式：FULLTEXT(精确匹配) DIM(模糊搜索)
        未找到匹配的值时返回False
        line：匹配后提取的列
        table：查询的表
        keyword_line：需要匹配的列
        keyword：需要匹配的关键字
        输出格式:[结果列表[每列结果]]'''

        fill_data = dict(line=line, table=table,
                         keyword_line=keyword_line, keyword=keyword)
        sql = "SELECT {line} FROM {table} WHERE {keyword_line}"
        if mode == "FULLTEXT":
            sql += "'{keyword}'"
        if mode == "DIM":
            sql += "LIKE '%%%%{keyword}%%%%'"
        sql = sql.format(**fill_data)

        self._link_checkout()
        cursor = self.db.cursor()
        try:
            cursor.execute(sql)
            results = cursor.fetchall()
            self.db.commit()
            cursor.close()
            return results
        except:
            return False

    def multires_finds(self, line, table, keyword_line, keyword, compare_mode="="):
        '''搜索数据（多结果版）
        【由一个匹配结果输出多个列数据】
        模式：FULLTEXT(精确匹配)
        未找到匹配的值时返回False
        line：匹配后提取的列【列表元素】
        table：查询的表
        keyword_line：需要匹配的列
        keyword：需要匹配的关键字
        compare_mode:比较模式，支持<,>,=，默认=  
        输出格式:[{列名:结果, 列名:结果...}]'''

        fill_data = dict(table=table, keyword_line=keyword_line,
                         compare_mode=compare_mode, keyword=keyword)
        sql = "SELECT "
        index = 1

        # 1234 >> ["1","2","3","4"] >> ["1",",","2",",","3",",","4"] >> 1,2,3,4
        while index < len(line):
            line.insert(index, ',')
            index += 2
        for x in line:
            sql += x

        sql += " FROM {table} WHERE {keyword_line} {compare_mode} "
        if isinstance(keyword, (int, float)):
            sql += "{keyword}"
        else:
            sql += "'{keyword}'"
        sql = sql.format(**fill_data)

        self._link_checkout()
        cursor = self.db.cursor(pymysql.cursors.DictCursor)
        try:
            cursor.execute(sql)
            results = cursor.fetchall()
            self.db.commit()
            cursor.close()
            # return tuple(results[0])
            return list(results)
        except:
            results = []
            [results.append(False) for x in range(len(line))]
            return tuple(results)

    def multi_finds(self, fulltext_mode, line, table, keyword_line, keyword, compare_mode=[]):
        '''搜索数据（多关键字多结果版）
        【支持多关键字】
        【支持多关键行】
        【支持输出单列结果//已阉割】
        【支持输出多个结果】
        ｛实用版｝
        fulltext模式：True(精确匹配) False(模糊搜索)
        compare模式：>,<,=(仅有=时模糊搜索生效，未指定时为默认值=)
        未找到匹配的值时返回False
        line：匹配后提取的列
        table：查询的表
        keyword_line：需要匹配的列【列表元素】
        keyword：需要匹配的关键字【列表元素】
        输出格式:[结果, 结果...]
        注：keyword_line与keyword数目必须一致，匹配模式数目不足默认按FULLTEXT模式填充'''

        sql = ""
        sql = self._sel_part(sql, [line], table)
        # Processing keyword&line
        sql = self._where_part(
            sql, fulltext_mode, keyword_line, keyword, compare_mode)

        self._link_checkout()
        cursor = self.db.cursor()
        try:
            cursor.execute(sql)
            results_raw = cursor.fetchall()
            self.db.commit()
            cursor.close()
            results = []
            [results.extend(list(x)) for x in results_raw]
            return results
        except:
            return False

    # 以上为旧版功能实现函数

    def _sel_part(self, sql_sent, line, table):
        '''分离构造：SELECT FROM 部分，多结果
        内置WHERE，因此必须拼接条件'''
        sql_sent += "SELECT "
        index = 1
        dot = 0
        line_queue = copy.deepcopy(line)

        # 1234 >> ["1","2","3","4"] >> ["1",",","2",",","3",",","4"] >> 1,2,3,4
        while index < len(line) + dot:
            line_queue.insert(index, ',')
            index += 2
            dot += 1
        for x in line_queue:
            sql_sent += x
        sql_sent += " FROM {} WHERE ".format(table)
        return sql_sent

    def _del_part(self, sql_sent, table):
        '''分离构造：DELETE FROM 部分
        内置WHERE'''
        sql_sent += "DELETE FROM {} WHERE ".format(table)
        return sql_sent

    def _ins_part(self, sql_sent, line, value, table):
        '''分离构造：INSERT INTO 部分，多列数据'''
        index = 0
        queue_line = "("
        for i in line:
            queue_line += i
            index += 1
            if index < len(line):
                queue_line += ","
        queue_line += ")"
        # 需要额外进行拼接防止line列变为单字符串而导致引号问题

        if len(value) == 1:
            val = "('{}')".format(tuple(value)[0])  # 此处为了修复仅有单个元素转换时残留一个逗号问题
        else:
            val = tuple(value)
        sql_sent += "INSERT INTO {table_name} {field} VALUES {value}".format(
            table_name=table, field=queue_line, value=str(val))
        return sql_sent

    def _up_part(self, sql_sent, line, value, table):
        '''分离构造：UPDATE SET 部分，多列数据
        内置WHERE，因此必须拼接条件'''
        sql_sent += "UPDATE {table_name} SET ".format(table_name=table)

        index = 0
        for k, v in zip(line, value):
            if isinstance(v, (int, float)):
                sql_sent += "{field}={value}".format(field=k, value=v)
            else:
                sql_sent += "{field}='{value}'".format(field=k, value=v)
            index += 1
            if index < len(line):
                sql_sent += ", "

        sql_sent += " WHERE "
        return sql_sent

    def _where_part(self, sql_sent, fulltext_mode, keyword_line, keyword, compare_mode=[]):
        '''分离构造：WHERE 部分(不会自动加WHERE),多条件
        逻辑判断仅有AND方式
        分离WHERE的目的是为了主调函数在之前追加额外条件（如表拼接）'''
        if len(fulltext_mode) < len(keyword):
            [
                fulltext_mode.append(True)
                for i in range(len(keyword) - len(fulltext_mode))
            ]  # Auto fill 'false' when mode_list not enough
        if len(compare_mode) < len(keyword):
            [
                compare_mode.append("=")
                for i in range(len(keyword) - len(compare_mode))
            ]  # Auto fill '=' when compare_mode not enough by defult

        index = 0
        for m, n, l, w in zip(fulltext_mode, compare_mode, keyword_line, keyword):
            fill_data = dict(compare_mode=n, keyword_line=l, keyword=w)
            sql_sent += "{keyword_line} "
            if n == "=" and not m:
                sql_sent += "LIKE '%%%%{keyword}%%%%'"
            else:
                sql_sent += " {compare_mode} "
                if isinstance(w, (int, float)):
                    sql_sent += "{keyword}"
                else:
                    sql_sent += "'{keyword}'"
            index += 1
            if index < len(keyword):
                sql_sent += " AND "
            sql_sent = sql_sent.format(**fill_data)
        return sql_sent

    def _link_checkout(self):
        '''分离构造：自动连接检查机制'''
        try:
            self.db.ping()
        except self.db.OperationalError:
            self.__init__(self.host, self.port, self.user, self.password,
                          self.database, self.charset)

    def multi_table_find(self, fulltext_mode, line, table, keyword_line,
                         keyword, bind_key, compare_mode=[]):
        '''搜索数据（多关键字多结果版以及表联结专版）
        【支持多关键字】
        【支持多关键行】
        【支持输出多列结果//史诗版继承者】
        【支持输出多个结果】
        【多表拼接专用，目前仅支持联结两个表】
        ｛专用版｝
        fulltext模式：True(精确匹配) False(模糊搜索)
        compare模式：>,<,=(仅有=时模糊搜索生效，为指定时为默认值=)
        未找到匹配的值时返回False
        line：匹配后提取的列【列表元素】
        table：查询的表【两个列表元素】
        keyword_line：需要匹配的列【列表元素】
        keyword：需要匹配的关键字【列表元素】
        bind_key：联结使用的绑定键【两个列表元素】
        输出格式:[{列名:结果, 列名:结果...}]
        注：keyword_line与keyword数目必须一致，匹配模式数目不足默认按FULLTEXT模式填充'''

        sql = ""
        index = 1
        index = 1
        str_table = ""
        while index < len(table):  # table
            table.insert(index, ',')
            index += 2
        for x in table:
            str_table += x
        sql = self._sel_part(sql, line, str_table)
        sql += '{}.{} = {}.{} AND '.format(table[0], bind_key[0], table[-1:][0],
                                           bind_key[1])
        sql = self._where_part(
            sql, fulltext_mode, keyword_line, keyword, compare_mode)

        self._link_checkout()
        cursor = self.db.cursor(pymysql.cursors.DictCursor)
        try:
            cursor.execute(sql)
            results = cursor.fetchall()
            self.db.commit()
            cursor.close()
            return list(results)
        except:
            # print(e)
            return False

    def epic_finds(self, fulltext_mode, line, table, keyword_line, keyword):
        '''搜索数据（多关键字多结果版）
        【支持多关键字】
        【支持多关键行】
        【支持输出多列结果】
        【支持输出多个结果】
        ｛究极终极版（现在不是了）//完全无阉割｝
        模式：True(精确匹配) False(模糊搜索)
        未找到匹配的值时返回False
        line：匹配后提取的列【列表元素】
        table：查询的表
        keyword_line：需要匹配的列【列表元素】
        keyword：需要匹配的关键字【列表元素】
        输出格式:[{列名:结果, 列名:结果...}]
        注：keyword_line与keyword数目必须一致，匹配模式数目不足默认按FULLTEXT模式填充'''

        sql = "SELECT "
        index = 1
        # Processing lines
        # 1234 >> ["1","2","3","4"] >> ["1",",","2",",","3",",","4"] >> 1,2,3,4
        while index < len(line):
            line.insert(index, ',')
            index += 2
        for x in line:
            sql += x
        # Processing table
        sql += ' FROM %s WHERE ' % table
        # Processing keyword&line
        index = 1
        if len(fulltext_mode) < len(keyword):
            [
                fulltext_mode.append(False)
                for i in range(len(keyword) - len(fulltext_mode))
            ]  # Auto fill 'false' when mode_list not enough
        for m, l, w in zip(fulltext_mode, keyword_line, keyword):
            if m:
                sql += "%s = '%s'" % (l, w)
                index += 1
            else:
                sql += "%s LIKE '%%%%%s%%%%'" % (l, w)
                index += 1
            if index < len(keyword):
                sql += " AND "

        self._link_checkout()
        cursor = self.db.cursor(pymysql.cursors.DictCursor)
        try:
            cursor.execute(sql)
            results = cursor.fetchall()
            self.db.commit()
            cursor.close()
            # return tuple(results[0])
            return results
        except:
            return False

    def finder_single(self, fulltext_mode, line, table, keyword_line, keyword, compare_mode=[],):
        '''数据库搜索器（单表最终版）
        支持多关键字，关键行，多列结果和多个结果
        {高度兼容版}
        table：查询的表
        【以下变量均使用列表元素】
        fulltext模式：True(精确匹配) False(模糊搜索)
        compare模式：>,<,=(仅有=时模糊搜索生效，未指定时为默认值=)
        line：匹配后提取的列
        keyword_line：需要匹配的列
        keyword：需要匹配的关键字
        输出格式:[{列名:结果, 列名:结果...}] #数组对象
        当hook参数启用时，变为数据库选择器，返回构造语句
        【未找到匹配的值时返回False】
        '''
        sql = ""
        sql = self._sel_part(sql, line, table)
        sql = self._where_part(
            sql, fulltext_mode, keyword_line, keyword, compare_mode)

        self._link_checkout()
        cursor = self.db.cursor(pymysql.cursors.DictCursor)
        try:
            cursor.execute(sql)
            results = cursor.fetchall()
            self.db.commit()
            cursor.close()
            return list(results)
        except:
            return False

    def adder_single(self, fulltext_mode, line, table, value, keyword_line, keyword, compare_mode=[]):
        '''数据库添加/更新器（单表型）
        支持多关键字，关键行，多列结果和多输入数据
        会根据请求的数据存在情况使用插入或者更新操作
        table：操作的表
        【以下变量均使用列表元素】
        fulltext模式：True(精确匹配) False(模糊搜索)
        compare模式：>,<,=(仅有=时模糊搜索生效，未指定时为默认值=)
        line：匹配后操作的列
        value:插入/更新内容
        {列和内容必须严格匹配}
        keyword_line：需要匹配的列
        keyword：需要匹配的关键字
        输出格式：操作成功时，按照实际操作情况为 INS(插入)， UP(更新)，失败时返回False
        '''

        if not len(line) == len(value):
            return False

        sql = ""
        operation = ""
        if self.finder_single(fulltext_mode, line, table, keyword_line, keyword, compare_mode):
            sql = self._up_part(sql, line, value, table)
            sql = self._where_part(sql, fulltext_mode, keyword_line, keyword)
            operation = "UP"
        else:
            sql = self._ins_part(sql, line, value, table)
            operation = "INS"

        self._link_checkout()
        cursor = self.db.cursor(pymysql.cursors.DictCursor)
        try:
            cursor.execute(sql)
            cursor.fetchall()
            self.db.commit()
            cursor.close()
            return operation
        except:
            self.db.rollback()
            return False

    def delete_single(self, fulltext_mode, table, keyword_line, keyword, compare_mode=[]):
        '''
        删除器
        支持多关键字，关键行
        table：查询的表
        【以下变量均使用列表元素】
        fulltext模式：True(精确匹配) False(模糊搜索)
        compare模式：>,<,=(仅有=时模糊搜索生效，未指定时为默认值=)
        keyword_line：需要匹配的列
        keyword：需要匹配的关键字
        无输出数据库内容
        【根据执行情况输出True和False】
        '''

        sql = ""
        sql = self._del_part(sql, table)
        sql = self._where_part(
            sql, fulltext_mode, keyword_line, keyword, compare_mode)

        self._link_checkout()
        cursor = self.db.cursor(pymysql.cursors.DictCursor)
        try:
            cursor.execute(sql)
            cursor.fetchall()
            self.db.commit()
            cursor.close()
            return True
        except:
            return False
