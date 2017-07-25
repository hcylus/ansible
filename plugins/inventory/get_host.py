#!/usr/bin/env python
#  -*- coding: utf-8 -*-
import time
import json
import re
import requests
import sys
import os
import logging
from contextlib import contextmanager


__version__ = "2016011546"
__author__ = 'smartwang@digisky.com'
__doc__ = """
usage: get_host.py [args]
    args:
        --list [production_short_name]:     输出能被ansible解析的inventory数据
        -v, --version:                      显示版本号
        -h, --help:                         显示帮助信息

get_host.py 环境变量说明
==========

    USE_PRIVATE_IP:  为1的时候，返回的ip为内网ip，否则为公网ip

    USE_GROUP_AS_HOST: 如果为1，则以应用作为最小管理单元进行的业务建模，这种方式是同我们的CMDB业务模型匹配的模式，并非ansible的标准方式
    举例来说：
    A业务的5个大区都搭建在同一台服务器上，我们希望用一个playbook配置来对这5个大区中的不确定数量的大区进行管理，
    但ansible的默认方式是按照IP进行管理的，5个区最终只会解析到1个ip，在一个playbook无法区分应该对这个ip进行何种操作（也可能是我们没有找到方法，虽然我们找遍了各种文档，也看了ansible的代码）
    此时就需要曲线救国了：
    给每个应用分配一个域名，inventory中的host就是这个域名而非ip了，这时ansible就会把不同的域名当成不同的主机来对待了（虽然最终都是解析到目标服务器ip上）。
    然后再利用我们自己的dns服务器对这个域名进行解析，就可以实现对每个应用进行操作了。

    CACHE_MODEL:
        0: 不使用缓存
        1: 根据过期时间决定是否使用缓存
        2: 强制使用缓存
    CACHE_TIME: 缓存时间，默认3600，单位为秒
    CACHE_DIR: 缓存目录，默认为/tmp

    ANSIBLE_INVENTORY_LOG: 日志目录。默认为/tmp
    ANSIBLE_PROJECT: 用于指定项目，无默认值，如果没有设置，则需要--list 后指定项目(用项目的缩写)
    ESB_HOST: esb的地址，外网使用esb.open.digi-sky.com，内网使用esb.service.digi-sky.com
    ESB_PORT: esb的端口，外网使用6100， 内网使用80

主机属性中的app_meta说明：
============
如果设置了USE_GROUP_AS_HOST=1, app_meta中的数据格式为：


"app_meta": {
    "process": {
        <process_name>: { // cmdb中配置的对应应用下的进程名
            "work_dir": "......" //cmdb中配置的对应进程的工作路径
            "attribute": {} // cmdb中自定义的key-value进程属性
            "config_file": [{"path": "....", "id": x} //根据配置文件id，通过配置文件获取接口得到配置文件内容
        }
    }
}


否则，就会按照这种格式：


"app_meta": {
    <ansible_expr>: {
        "process": {
            <process_name>: { // cmdb中配置的对应应用下的进程名
                "work_dir": "......" //cmdb中配置的对应进程的工作路径
                "attribute": {} // cmdb中自定义的key-value进程属性
                "config_file": [{"path": "....", "id": x} //根据配置文件id，通过配置文件获取接口得到配置文件内容
            }
        }
    }
}


"""

PROJECT = os.environ.get('ANSIBLE_PROJECT', None)
LOG_PATH = os.environ.get('ANSIBLE_INVENTORY_LOG', "/tmp/ansible_inventory_%s.log" % PROJECT)
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S',
                    filename=LOG_PATH,
                    filemode='w')

ESB_PORT = os.environ.get("ESB_PORT", "6100")
ESB_HOST = os.environ.get("ESB_HOST", "esb.open.digi-sky.com")
CMDB_ESB_URL = "http://%s:%s/esb/cmdb/get_host/" % (ESB_HOST, ESB_PORT)

CACHE_DIR = os.environ.get("CACHE_DIR", '/tmp')
CACHE_MODEL = os.environ.get('CACHE_MODEL', '0')  # 0: no cache, 1: normal cache, 2: use cache only
CACHE_TIME = int(os.environ.get('CACHE_TIME', 3600))  # 缓存时长(单位: s)
USE_GROUP_AS_HOST = os.environ.get("USE_GROUP_AS_HOST", '0')


@contextmanager
def response_check(response):
    """"""
    if response.status_code == 200:
        response = json.loads(response.text)
        if not response['result']:
            logging.error('request return error, error msg: %s' % response['data'])
            raise Exception('request return error, error msg: %s' % response['data'])
    else:
        logging.error('request failed, status_code=%s' % response.status_code)
        raise Exception('request failed, status_code=%s' % response.status_code)    
    yield response


class DigiskyInventory(object):
    def __init__(self, PROJECT):
        self.cache = dict()
        self.inventory = dict()
        self._inv = dict()
        self.PROJECT = PROJECT
        self.cache_file_path = os.path.join(CACHE_DIR, "inventory_%s.cache" % self.PROJECT)
        self.cache = dict()

    def _find_private_ip(self, ip_list, public_ip):
        pattern = r'(127\.0\.0\.1)|(localhost)|(10\.\d{1,3}\.\d{1,3}\.\d{1,3})|(172\.((1[6-9])|(2\d)|(3[01]))\.\d{1,3}\.\d{1,3})|(192\.168\.\d{1,3}\.\d{1,3})'
        for ip in ip_list:
            if re.match(pattern, ip):
                return ip
        return "PRIVATE_IP_NOT_FOUND_FOR_%s" % public_ip  # 返回 PRIVATE_IP_NOT_FOUND 只是用于提示运维存在异常

    def get_project_list(self):
        output_fields = ['app']
        query_condition = {
            "project_ab": [self.PROJECT, ]
        }
        app_list = []
        r = requests.post(CMDB_ESB_URL,
                          data=json.dumps({'output_fields': output_fields, 'query_condition': query_condition}))
        if r.status_code == 200:
            try:
                response = json.loads(r.text)
            except Exception as e:
                logging.error(str(e))
                logging.debug(r.text)
            if response['result']:
                for host_item in response['data']:
                    for app_string in host_item['app']:
                        if app_string not in app_list:
                            app_list.append(app_string)
        return app_list

    def load_inventory(self):
        # self.inventory = {
        #     "group1": [
        #         "192.168.2.170",
        #     ],
        #     "group2": {'hosts': ['x.x.x.x'], 'vars': {} },
        #     "_meta": {
        #         "hostvars": {
        #             "192.168.2.170": {
        #                 "var1": "value1",
        #                 "var2": "value2"
        #             },
        #         },
        #         "group1": {
        #             "children": [
        #                 "group2"
        #             ]
        #         }
        #     }
        # }

        # NOTE: ansible1.7之后，可以在list中一次性返回所有数据，如果没有hostvars，会触发多次--host，导致性能下降
        # 固在未实现hostvar之前，将这个变量置空，避免性能问题
        self.inventory['_meta'] = {"hostvars": {}}
        # NOTE: 已知bug：当返回的app_string中包含中文字符时, ansible会出错，因此需要业务避免这种情况出现
        output_fields = ['ip', 'app', 'cabinet', 'other_ip', 'app_meta']
        query_condition = {
            "project_ab": [self.PROJECT, ]
        }

        def update_inventory(host_list):
            if USE_GROUP_AS_HOST == "1":    # 这种方式是以应用作为最小管理单元进行的业务建模,需要配合自定义的dns服务使用
                for host_item in host_list:
                    _ip = host_item['ip']
                    for app_string in host_item['app']:
                        self.inventory.setdefault(app_string, {"hosts": [], "vars": {'ansible_expr': app_string}})
                        self._inv.setdefault(app_string, [])
                        if os.environ.get("USE_PRIVATE_IP") == "1":
                            _ip = self._find_private_ip(host_item['other_ip'], host_item['ip'])
                            if not _ip:
                                continue
                        if "%s.%s.cmdb" % (_ip, app_string) not in self._inv[app_string]:
                            self._inv[app_string].append("%s.%s.cmdb" % (_ip, app_string))
                            self.inventory[app_string]['hosts'].append("%s.%s.cmdb" % (_ip, app_string))
                        if not _ip:
                            continue
                        self.inventory['_meta']["hostvars"].update({
                            "%s.%s.cmdb" % (_ip, app_string): {
                                "cabinet_name": host_item['cabinet']['name'],
                                "app": host_item['app'],
                                "region_ab": host_item['cabinet']['region']['ab'],
                                "plat_ab": host_item['cabinet']['region']['plat']['ab'],
                                "other_ip": host_item['other_ip'],
                                "ip": host_item['ip'],
                                "ansible_ssh_host": _ip,
                                "app_meta": host_item['app_meta'].get(app_string, {}),
                            }
                        })
            else:   # 这种方式是以ip作为最小管理单元进行的业务建模，是ansible的标准方式
                for host_item in host_list:
                    _ip = host_item['ip']
                    for app_string in host_item['app']:
                        self.inventory.setdefault(app_string, {"hosts": [], "vars": {'ansible_expr': app_string}})
                        self._inv.setdefault(app_string, [])
                        if os.environ.get("USE_PRIVATE_IP") == "1":
                            _ip = self._find_private_ip(host_item['other_ip'], host_item['ip'])
                            if not _ip:
                                continue
                        if _ip not in self._inv[app_string]:
                            self._inv[app_string].append(_ip)
                            self.inventory[app_string]['hosts'].append(_ip)
                    if not _ip:
                        continue
                    self.inventory['_meta']["hostvars"].update({
                        _ip: {
                            "cabinet_name": host_item['cabinet']['name'],
                            "app": host_item['app'],
                            "region_ab": host_item['cabinet']['region']['ab'],
                            "plat_ab": host_item['cabinet']['region']['plat']['ab'],
                            "other_ip": host_item['other_ip'],
                            "ip": host_item['ip'],
                            "ansible_ssh_host": _ip,
                            "app_meta": host_item['app_meta'],
                        }
                    })

        update_inventory(self.load_data())

    def _get_data(self):
        # 获取产品和版本的属性
        ATTRIBUTE_URL = "http://%s:%s/esb/cmdb/list_attributes/" % (ESB_HOST, ESB_PORT)
        r = requests.get(ATTRIBUTE_URL, params={'usage_ab': self.PROJECT})
        with response_check(r) as response:
            attribute_data = response['data']

        output_fields = ['ip', 'app', 'cabinet', 'other_ip', 'app_meta']
        query_condition = {
            "project_ab": [self.PROJECT, ]
        }
        r = requests.post(CMDB_ESB_URL,
                          data=json.dumps({'output_fields': output_fields, 'query_condition': query_condition}))
        
        with response_check(r) as response:
            data = response['data']

        for index in xrange(len(data)):
            for k, v in data[index]['app_meta'].items():
                ver_id = v['ver_info']['id']
                for ver_attribute in attribute_data['ver_attribute']:
                    if ver_attribute['ver_id'] == ver_id:
                        data[index]['app_meta'][k]['ver_info'].setdefault('ver_attribute', {})
                        data[index]['app_meta'][k]['ver_info']['ver_attribute'].update({ver_attribute['name']: ver_attribute['value']})
        return data

    def update_cache(self):
        data = self._get_data()
        with open(self.cache_file_path, 'w') as f:
            f.write(json.dumps({
                "last_modify": time.time(),
                "data": data,
            }))
        return data

    def load_data(self):
        if CACHE_MODEL == "1":
            try:
                with open(self.cache_file_path, 'r') as f:
                    data = json.loads(f.read())
                if time.time() - data.get('last_modify') < CACHE_TIME:  # 直接使用缓存
                    return data.get('data')
            except IOError:
                return self.update_cache()
            else:
                return self.update_cache()
        elif CACHE_MODEL == "2":    # 强制使用缓存
            try:
                with open(self.cache_file_path, 'r') as f:
                    data = json.loads(f.read())
                    return data.get('data')
            except IOError:
                return self.update_cache()
        else:   # no cache
            return self._get_data() or []

    def print_data(self):
        #print json.dumps(self.inventory)
        print(json.dumps(self.inventory, ensure_ascii=False, indent=4))


if __name__ == "__main__":
    reload(sys)
    sys.setdefaultencoding('utf-8')
    action = sys.argv[1]  # --list or --host or --project
    project_ab = PROJECT

    if action in ["-v", "--version"]:
        print(__version__)
        sys.exit(0)
    elif action in ['-h', '--help']:
        print(__doc__)
        sys.exit(0)

    if len(sys.argv) > 2:
        project_ab = sys.argv[2]

    if not project_ab:
        logging.error("ANSIBLE_PROJECT empty")
        sys.exit(2)

    inventory = DigiskyInventory(project_ab)

    if action == "--list":
        inventory.load_inventory()
        inventory.print_data()
    elif action == '--host':
        # TODO: to be implemented
        pass
    elif action == '--project':
        print " ".join(inventory.get_project_list())


