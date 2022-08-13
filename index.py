import hashlib
import json
import os
import platform
import re

import requests
from bs4 import BeautifulSoup

if platform.system() == 'Windows':
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
    print(f'卡密：{os.environ["card"]}\nRPC地址：{os.environ["aria2_rpc"]}\n自动获取文件名：{os.environ["auto_name"]}')
    print(f'aria2_token：{os.environ["aria2_token"]}\n下载地址：{os.environ["download_path"]}\n代理地址：{proxies}\n')


def jiexi(url, name):
    data = {
        'browser': '',
        'url': url,
        'card': os.environ['card']
    }
    rep = requests.post('http://disk.codest.me/doOrder4Card', data=data, verify=False)
    soup = BeautifulSoup(rep.text, 'html.parser')
    try:
        scriptTags = soup.findAll('a', {'class': 'btn btn-info btn-sm'})
        end_time = soup.find('span', {'class': 'badge badge-pill badge-secondary'}).span.text
    except Exception as e:
        print('错误类型是', e.__class__.__name__)
        print('错误明细是', e)
        return

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
    down_link = aria2_link[0]

    if 'rosefile' in url:
        for temp_url in aria2_link:
            if 'down-node' in temp_url:
                down_link = temp_url
                break
    print(f'获取下载链接{down_link[:40]}...成功\n{end_time}，请记得及时续费')

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
        print(f'下载任务{name}添加成功\n')
    else:
        print(f'下载任务{name}创建失败', url)


def downl_idm(url, referer, name):
    toIdm.download(url, os.environ['download_path'], name, referer)


def get_name(url):
    def is_in_list(arr: list, value: str):
        for web in arr:
            if web in value:
                return True
        return False

    rep = requests.get(url)
    # 针对301或302跳转
    url = rep.url
    if os.environ['auto_name'] == 'false':
        return url, None
    # 针对200状态码的跳转
    soup = BeautifulSoup(rep.text, 'html.parser')
    if soup.find('meta').get('http-equiv') == 'refresh':
        # META http-equiv="refresh" 实现网页自动跳转
        url = re.search(r'[a-zA-z]+://\S*', soup.find('meta').get('content')).group()
        rep = requests.get(url)
    if 'rosefile' in url:
        # https://rosefile.net/pm98zjeu2b/xa754.rar.html
        return url, url.split('/')[-1][:-5]
    elif 'feimaoyun' in url:
        # https://www.feimaoyun.com/s/398y7f0l
        key = url.split('/')
        rep = requests.post('https://www.feimaoyun.com/index.php/down/new_detailv2', data={'code': key})
        if rep.status_code == 200:
            return url, rep.json()['data']['file_name']
        else:
            return url, input(f'解析失败，请手动填写文件名({url})')
    elif is_in_list(['xueqiupan', '567file', 'ownfile', 'feiyupan', 'xunniupan'], url):
        # http://www.xueqiupan.com/file-531475.html
        # https://www.567file.com/file-1387363.html
        # https://ownfile.net/files/T09mMzQ5ODUx.html
        # http://www.feiyupan.com/file-1400.html
        # http://www.xunniupan.com/file-2475170.html
        if rep.status_code == 200:
            soup = BeautifulSoup(rep.text, 'html.parser')
            return url, soup.find('div', {'class': 'row-fluid'}).div.h1.text
        else:
            return url, input(f'解析失败，请手动填写文件名({url})')
    elif 'dufile' in url:
        # https://dufile.com/file/0c7184f05ecdce0f.html
        if rep.status_code == 200:
            soup = BeautifulSoup(rep.text, 'html.parser')
            return url, soup.find('h2', {'class': 'title'}).text.split('  ')[-1]
        else:
            return url, input(f'解析失败，请手动填写文件名({url})')
    elif is_in_list(['xingyaopan', 'kufile', 'rarclouds'], url):
        # http://www.xingyaopan.com/fs/tuqlqxxnyzggaag
        # http://www.kufile.net/file/QUExNTM5NDg1.html
        # http://www.rarclouds.com/file/QUExNTE5Mjgz.html
        if rep.status_code == 200:
            soup = BeautifulSoup(rep.text, 'html.parser')
            name = soup.find('title').text.split(' - ')[0]
            file_type = soup.find('img', {'align': 'absbottom'})['src'].split('/')[-1].split('.')[0]
            return url, f'{name}.{file_type}'
        else:
            return url, input(f'解析失败，请手动填写文件名({url})')
    elif 'dudujb' in url:
        # https://www.dudujb.com/file-1105754.html
        if rep.status_code == 200:
            soup = BeautifulSoup(rep.text, 'html.parser')
            soup = soup.findAll('input', {'class': 'txtgray'})[-1]['value']
            return url, BeautifulSoup(soup, 'html.parser').text
        else:
            return url, input(f'解析失败，请手动填写文件名({url})')
    elif 'xfpan' in url:
        # http://www.xfpan.cc/file/QUExMzE4MDUx.html
        if rep.status_code == 200:
            rep = requests.get(url.replace(r'/file/', r'/down/'), headers={'Referer': url})
            if rep.status_code == 200:
                soup = BeautifulSoup(rep.text, 'html.parser')
                return url, soup.find('title').text.split(' - ')[0]
            else:
                return url, input(f'解析失败，请手动填写文件名({url})')
        else:
            return url, input(f'解析失败，请手动填写文件名({url})')
    elif 'expfile' in url:
        # http://www.expfile.com/file-1464062.html
        url = url.replace('file-', 'down2-')
        rep = requests.get(url)
        if rep.status_code == 200:
            soup = BeautifulSoup(rep.text, 'html.parser')
            name = soup.find('title').text.split(' - ')[0]
            return url, name
        else:
            return url, input(f'解析失败，请手动填写文件名({url})')
    else:
        return url, input(f'暂不支持该网盘自动解析文件名，请手动填写({url})')


if __name__ == '__main__':
    init()
    while True:
        url = input('请输入下载链接：')
        url, name = get_name(url)
        print(f'获取文件名{name}成功')
        jiexi(url, name)
