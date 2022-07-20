import hashlib
import json
import os
import re

import requests
from bs4 import BeautifulSoup

import toIdm

proxies = dict()
config_path = './config.json'


def init():
    global proxies
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    for key in config:
        os.environ[key] = config[key]
    if config.get('proxies'):
        proxies = {
            'http': config.get('proxies'),
            'https': config.get('proxies')
        }
    else:
        proxies = None
    print('初始化配置完成，打印关键参数')
    print(f'卡密：{os.environ["card"]}\nRPC地址：{os.environ["aria2_rpc"]}')
    print(f'aria2_token：{os.environ["aria2_token"]}\n下载地址：{os.environ["download_path"]}\n代理地址：{proxies}\n')


def jiexi(url, name):
    data = {
        'browser': '',
        'url': url,
        'card': os.environ['card']
    }
    rep = requests.post('http://disk.codest.me/doOrder4Card', data=data, verify=False)
    soup = BeautifulSoup(rep.text, 'html.parser')
    scriptTags = soup.findAll('a', {'class': 'btn btn-info btn-sm'})

    # 存储下载地址
    aria2_link = list()
    for script in scriptTags:
        if script.has_attr('aria2-link'):
            aria2_link.append(script['aria2-link'])

    # 下载地址列表为空
    if len(aria2_link) == 0:
        print('未获取到下载链接', url, name)
        print(rep.text)
        return

    # 对rosefile特殊处理，down-node使用的是sharepoint，速度更快
    if 'rosefile' in url:
        down_link = aria2_link[0]
        for temp_url in aria2_link:
            if 'down-node' in temp_url:
                down_link = temp_url
                break
    else:
        down_link = aria2_link[0]
    if len(os.environ['aria2_rpc']) == 0:
        downl_idm(down_link, url, name)
    else:
        downl_aria2(down_link, url, name)


def downl_aria2(url, referer, name):
    RPC_url = os.environ['aria2_rpc']
    json_rpc = json.dumps({
        'id': hashlib.md5(url.encode(encoding='UTF-8')).hexdigest(),
        'jsonrpc': '2.0',
        'method': 'aria2.addUri',
        'params': [
            f'token:{os.environ["aria2_token"]}',
            [url],
            {'dir': os.environ['download_path'], 'out': name, 'referer': referer}]
    })
    response = requests.post(url=RPC_url, data=json_rpc, proxies=None)
    if response.status_code == 200:
        print(f'下载任务{name}添加成功')
    else:
        print(f'下载任务{name}创建失败', url)


def downl_idm(url, referer, name):
    toIdm.download(url, os.environ['download_path'], name, referer)


def get_name(url):
    if 'rosefile' in url:
        # https://rosefile.net/pm98zjeu2b/xa754.rar.html
        return url.split('/')[-1][:-5]
    elif 'kufile' in url:
        # http://www.kufile.net/file/QUExNTM5NDg1.html
        rep = requests.get(url)
        if rep.status_code == 200:
            name = re.search(r'<title.*?>(.+?)</title>', rep.text).groups()[0].replace(' - 库云,您值得拥有|KuFile', '')
            file_type = re.search(r'类型：.+?<', rep.text).group()[3:-1]
            return f'{name}.{file_type}'
        else:
            return input(f'解析失败，请手动填写文件名({url})')
    else:
        return input(f'暂不支持该网盘自动解析文件名，请手动填写({url})')


if __name__ == '__main__':
    init()
    while True:
        url = input('请输入下载链接：')
        name = get_name(url)
        jiexi(url, name)
