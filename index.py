import asyncio
import base64
import hashlib
import json
import os
import platform
import random
import re
import sys
import time

import pyperclip
import requests
import urllib3
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.util.timeout.Timeout._validate_timeout = lambda *args: 10 if args[2] != 'total' else None
if platform.system() == 'Windows':
    import toIdm

config_path = './config.json'
retries = Retry(total=3, backoff_factor=0.1)
main_domain = [
    'rosefile',
    'feimaoyun',
    'xueqiupan',
    '567file',
    'ownfile',
    'feiyupan',
    # 'xunniupan',
    'dufile',
    'xingyaopan',
    'kufile',
    'rarclouds',
    'dudujb',
    'xfpan',
    'skyfileos',
    'expfile'
]
pan_domain = 'http://haoduopan.cn'


def init():
    global s, proxies
    s = requests.session()
    s.headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36'
    }
    s.trust_env = False
    s.mount('http://', HTTPAdapter(max_retries=retries))
    s.mount('https://', HTTPAdapter(max_retries=retries))
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    for key in config:
        os.environ[key] = config[key]
    proxies = {
        'http': config.get('proxies'),
        'https': config.get('proxies')
    }
    print(f'初始化配置完成，打印关键参数(自动获取文件名：{os.environ["auto_name"]})')
    print(f'卡密：{os.environ["card"]}\nRPC地址：{os.environ["aria2_rpc"]}')
    print(f'aria2_token：{config.get("aria2_token")}\n下载地址：{config.get("download_path")}')
    sys.stdout.flush()


async def jiexi(url):
    data = {
        'browser': '',
        'url': url,
        'card': os.environ['card']
    }
    try:
        rep = s.post(f'{pan_domain}/doOrder4Card', data=data)
    except requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout:
        print('下载链接解析失败')
        return None
    if 'toCaptcha' in rep.url:
        print('遭遇到机器验证')
        if platform.system() == 'Windows':
            pyperclip.copy(f'{pan_domain}/toCaptcha/' + os.environ['card'])
            print('已将验证网址复制到剪贴板，程序将在5秒后退出')
        else:
            print(f'{pan_domain}/toCaptcha/' + os.environ['card'])
        time.sleep(5)
        exit(1)
    soup = BeautifulSoup(rep.text, 'html.parser')
    if 'confirm' not in rep.url:
        err_text = soup.find('div', {'class': 'col text-center'}).findAll('p')[-1].text
        print(err_text)
        return None
    try:
        scriptTags = soup.findAll('a', {'class': 'btn btn-info btn-sm'})
        end_time = soup.find('span', {'class': 'badge badge-pill badge-secondary'}).span.text
    except Exception as e:
        print('错误类型是', e.__class__.__name__)
        print('错误明细是', e)
        print(soup)
        sys.stdout.flush()
        time.sleep(5)
        exit(1)
        return

    # 存储下载地址
    aria2_link = list()
    for script in scriptTags:
        if script.has_attr('aria2-link'):
            aria2_link.append(script['aria2-link'])

    # 下载地址列表为空
    if len(aria2_link) == 0:
        print('未获取到下载链接', url)
        print(rep.text)
        sys.stdout.flush()
        return

    # 对rosefile特殊处理，down-node使用的是sharepoint，速度更快
    # down_link = aria2_link[0]
    down_link = random.choice(aria2_link)
    # down-node偶尔会出现错误，增加重试机制
    # 当程序第二次解析同一个链接时，禁用down-node节点
    # if os.environ['rosefile'] is None:
    #     try:
    #         _ = os.environ[url]
    #         isFirst = False
    #     except KeyError:
    #         isFirst = True
    #     # isFirst = False
    #     if 'rosefile' in url and isFirst:
    #         for temp_url in aria2_link:
    #             if 'down-node' in temp_url:
    #                 down_link = temp_url
    #                 # 赋值任意数据均可，目的是让环境变量不为空
    #                 os.environ[url] = '1'
    #                 break
    # else:
    #     for temp_url in aria2_link:
    #         if 'down-node' not in temp_url:
    #             down_link = temp_url
    url_domain = re.search('(http|https)://(www.)?(\w+(\.)?)+', down_link).group()
    print(f'获取下载链接{url_domain}/...成功\n{end_time}，请记得及时续费', flush=True)
    return down_link


def download(url, referer, name, is_xc: str):
    def downl_idm(url, referer, name):
        toIdm.download(url, os.environ['download_path'], name, referer)

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
        '''
        # 如果需要启用代理访问aria2RPC，取消注释本段代码
        s_with_env = requests.session()
        s_with_env.mount('http://', HTTPAdapter(max_retries=retries))
        s_with_env.mount('https://', HTTPAdapter(max_retries=retries))
        response = s_with_env.post(url=RPC_url, data=json_rpc)
        '''
        try:
            response = s.post(url=RPC_url, data=json_rpc)
            if response.status_code == 200:
                print(f'下载任务{name}添加成功\n', flush=True)
            else:
                print(f'下载任务{name}创建失败', name, flush=True)
                print(f'续传码：XC://{xc_ma}', flush=True)
                if platform.system() == 'Windows':
                    pyperclip.copy(f'XC://{xc_ma}')
                    print('已将续传码复制到剪贴板', flush=True)
        except Exception as e:
            print(f'添加任务失败，错误原因{e.__class__.__name__}', flush=True)
            print(f'续传码：XC://{xc_ma}', flush=True)
            if platform.system() == 'Windows':
                pyperclip.copy(f'XC://{xc_ma}')
                print('已将续传码复制到剪贴板', flush=True)
            else:
                print(f'XC://{xc_ma}', flush=True)

    if is_xc != '':
        xc_ma = is_xc.replace('XC://', '')
        tmp_data = base64.b64decode(xc_ma).decode().split('###')
        url = tmp_data[0]
        referer = tmp_data[1]
        name = tmp_data[2]
    else:
        xc_ma = base64.b64encode(f'{url}###{referer}###{name}'.encode()).decode()
    if os.environ.get('xc') is not None:
        print(f'XC://{xc_ma}')
        return
    if len(os.environ['aria2_rpc']) == 0:
        downl_idm(url, referer, name)
    else:
        downl_aria2(url, referer, name)


async def get_name(url):
    def is_in_list(arr: list, value: str):
        for web in arr:
            if web in value:
                return True
        return False

    name = None
    if os.environ['auto_name'] == 'false':
        domain = url.split('/')[2]
        if not is_in_list(main_domain, domain):
            rep = s.get(url)
            if rep.status_code != 200:
                print('网盘访问失败，可以关闭自动解析文件名再次尝试', flush=True)
                return name
            # 针对301或302跳转
            url = rep.url
        return name, url

    rep = requests.models.Response
    # 白名单模式
    if not is_in_list(['rosefile', 'koalaclouds', 'feimaoyun', 'expfile'], url):
        rep = s.get(url)
        # 针对301或302跳转
        url = rep.url
        # 针对200状态码的跳转
        soup = BeautifulSoup(rep.text, 'html.parser')
        if soup.find('meta').get('http-equiv') == 'refresh':
            # META http-equiv="refresh" 实现网页自动跳转
            url = re.search(r'[a-zA-z]+://\S*', soup.find('meta').get('content')).group()
            rep = s.get(url)
        if rep.status_code != 200:
            print('网盘访问失败，可以关闭自动解析文件名再次尝试', flush=True)
            return name, url
    try:
        if is_in_list(['rosefile', 'koalaclouds'], url):
            # https://rosefile.net/pm98zjeu2b/xa754.rar.html
            # https://koalaclouds.com/971f6c37836c82fb/xm1901.part1.rar
            if 'rosefile' in url:
                name = url.split('/')[-1][:-5]
            elif 'koalaclouds' in url:
                name = url.split('/')[-1]
        elif 'feimaoyun' in url:
            # https://www.feimaoyun.com/s/398y7f0l
            key = url.split('/')
            rep = s.post('https://www.feimaoyun.com/index.php/down/new_detailv2', data={'code': key})
            if rep.status_code == 200:
                name = rep.json()['data']['file_name']
            else:
                name = input(f'解析失败，请手动填写文件名({url})')
        elif is_in_list(['xueqiupan', '567file', 'ownfile', 'feiyupan', 'xunniu'], url):
            # http://www.xueqiupan.com/file-531475.html
            # https://www.567file.com/file-1387363.html
            # https://ownfile.net/files/T09mMzQ5ODUx.html
            # http://www.feiyupan.com/file-1400.html
            # http://www.xunniupan.com/file-2475170.html
            soup = BeautifulSoup(rep.text, 'html.parser')
            name = soup.find('div', {'class': 'row-fluid'}).div.h1.text
        elif 'dufile' in url:
            # https://dufile.com/file/0c7184f05ecdce0f.html
            soup = BeautifulSoup(rep.text, 'html.parser')
            name = soup.find('h2', {'class': 'title'}).text.split('  ')[-1]
        elif is_in_list(['xingyao', 'xywpan', 'kufile', 'rar'], url):
            # http://www.xingyaopan.com/fs/tuqlqxxnyzggaag
            # http://www.kufile.net/file/QUExNTM5NDg1.html
            # http://www.rarclouds.com/file/QUExNTE5Mjgz.html
            soup = BeautifulSoup(rep.text, 'html.parser')
            name = soup.find('title').text.split(' - ')[0]
            file_type = soup.find('img', {'align': 'absbottom'})['src'].split('/')[-1].split('.')[0]
            name = f'{name}.{file_type}'
        elif 'dudujb' in url:
            # https://www.dudujb.com/file-1105754.html
            soup = BeautifulSoup(rep.text, 'html.parser')
            soup = soup.findAll('input', {'class': 'txtgray'})[-1]['value']
            name = BeautifulSoup(soup, 'html.parser').text
        elif is_in_list(['xfpan', 'skyfileos'], url):
            # http://www.xfpan.cc/file/QUExMzE4MDUx.html
            # https://www.skyfileos.com/90ea219698c62ea5
            rep = s.get(url.replace(r'/file/', r'/down/'), headers={'Referer': url})
            if rep.status_code == 200:
                soup = BeautifulSoup(rep.text, 'html.parser')
                name = soup.find('title').text.split(' - ')[0]
            else:
                name = input(f'解析失败，请手动填写文件名({url})')
        elif 'expfile' in url:
            # http://www.expfile.com/file-1464062.html
            url = url.replace('file-', 'down2-')
            rep = s.get(url)
            if rep.status_code == 200:
                soup = BeautifulSoup(rep.text, 'html.parser')
                name = soup.find('title').text.split(' - ')[0]
                name = name
            else:
                name = input(f'解析失败，请手动填写文件名({url})')
        elif 'baigepan' in url:
            # https://www.baigepan.com/s/iU36ven9Wu
            soup = BeautifulSoup(rep.text, 'html.parser')
            name = soup.find('title').text.split(' - ')[0]
        else:
            name = input(f'暂不支持该网盘自动解析文件名，请手动填写({url})')
        print(f'获取文件名{name}成功', flush=True)
    except:
        return None, url
    return name, url


async def main():
    init()
    while True:
        url = input('\n请输入下载链接/续传码：')
        if 'XC://' in url:
            download('', '', '', is_xc=url)
        else:
            name, down_link = await asyncio.gather(get_name(url), jiexi(url))
            if down_link is None:
                continue
            download(down_link, name[1], name[0], is_xc='')


if __name__ == '__main__':
    args = sys.argv
    if len(args) == 1:
        config_path = './config.json'
    else:
        config_path = args[1]
    asyncio.run(main())
