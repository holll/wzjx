import hashlib
import os
import platform
import random
import re
from typing import Union

import requests
import urllib3
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

try:
    import redis

    hasRedis = True
    pool_db1 = redis.ConnectionPool(host='127.0.0.1', port=6379, db=2)
    r_l = redis.Redis(connection_pool=pool_db1)
except ModuleNotFoundError:
    hasRedis = False
from tools import const

urllib3.util.timeout.Timeout._validate_timeout = lambda *args: 10 if args[2] != 'total' else None


def string_to_hex(ac_str):
    hex_val = ""
    for char in ac_str:
        code = ord(char)
        hex_val += str(code)
    return hex_val


# 使用MD5加密
def md5_encode(word):
    md5_hash = hashlib.md5(word.encode()).hexdigest()
    return md5_hash


def is_in_list(arr: list, value: str):
    for web in arr:
        if web in value:
            return True
    return False


class myRequests:
    retries = urllib3.util.retry.Retry(total=3, backoff_factor=0.1)
    session = requests.session()
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'
    post_uri = ''

    def __init__(self, headers: Union[None, dict] = None):
        self.session.headers = {
            'user-agent': myRequests.user_agent,
        }
        if headers is not None:
            for k, v in headers:
                self.session.headers[k] = v
        self.session.trust_env = False
        self.session.mount('http://', HTTPAdapter(max_retries=myRequests.retries))
        self.session.mount('https://', HTTPAdapter(max_retries=myRequests.retries))
        rep = self.session.get(const.pan_domain)
        soup = BeautifulSoup(rep.text, 'html.parser')
        self.post_uri = soup.find('form', {'id': 'diskForm'})['action']

    def get(self, url: str, headers: Union[None, dict] = None, params=None) -> requests.models.Response:
        if headers is not None:
            copy_headers = self.session.headers
            for k, v in headers:
                copy_headers[k] = v
            return self.session.get(url, headers=copy_headers, params=params)
        return self.session.get(url, params=params)

    def post(self, url: str, headers: Union[None, dict] = None, data=None) -> requests.models.Response:
        if headers is not None:
            copy_headers = self.session.headers
            for k, v in headers:
                copy_headers[k] = v
            return self.session.post(url, headers=copy_headers, data=data)
        return self.session.post(url, data=data)


def select_link(links: list) -> str:
    if not os.getenv('auto_select'):
        all_domains = list()
        for link in links:
            link_domain = re.search(const.domain_reg, link).group()
            all_domains.append(link_domain)

        if len(all_domains) > 1:
            print("可选的下载服务器：")
            for i, domain in enumerate(all_domains):
                print(f"[{i}]: {domain}")
            while True:
                choice = input('请输入序号选择下载服务器：')
                if not choice.isdecimal():
                    print(f"请输入数字序号！0-{len(all_domains)}")
                    continue
                choice = int(choice)
                if 0 <= choice < len(all_domains):
                    return links[choice]
                else:
                    print(f"请输入正确的序号！0-{len(all_domains)}")
        else:
            return links[0]
    else:
        return random.choice(links)


async def jiexi(s: requests.sessions, url: str) -> dict:
    return_data = {'code': 200, 'raw_url': url, 'links': [], 'msg': '', 'cache': 'miss'}
    if not url.endswith('#re') and hasRedis:
        # 判断链接命中缓存
        link_cache = r_l.lrange(url, 0, -1)
        link_cache = [link.decode('utf-8') for link in link_cache]
        if link_cache:
            return_data['cache'] = 'hit'
            return_data['links'] = link_cache
            return return_data
    else:
        url = url.replace('#re', '')
    data = {
        'browser': '',
        'url': url,
        'card': os.environ['card']
    }
    try:
        rep = s.post(f'{const.pan_domain}{s.post_uri}', data=data)
    except Exception as e:
        print('下载链接解析失败', e.__class__.__name__)
        return_data['code'] = 500
        return_data['msg'] = '下载链接解析失败'
        return return_data
    if 'toCaptcha' in rep.url:
        print('遭遇到机器验证')
        return_data['code'] = 403
        return_data['msg'] = '遭遇到机器验证'
        if platform.system() == 'Windows':
            import pyperclip
            pyperclip.copy(f'{const.pan_domain}/toCaptcha/' + os.environ['card'])
            print('已将验证网址复制到剪贴板，程序将在5秒后退出')
        else:
            print(f'{const.pan_domain}/toCaptcha/' + os.environ['card'])
        return return_data
    soup = BeautifulSoup(rep.text, 'html.parser')
    # 解析出现预期内的异常
    error_html = soup.find('div', {'class': 'col text-center'})
    if error_html is not None:
        error_text = ''
        for p in error_html.findAll('p'):
            error_text += p.text.strip() + ' '
        return_data['code'] = 400
        return_data['msg'] = error_text.strip()
        return return_data
    try:
        scriptTags = soup.findAll('a', {'class': 'btn btn-info btn-sm'})
        end_time = soup.find('span', {'class': 'badge badge-pill badge-secondary'}).span.text
        return_data['end_time'] = end_time
    except Exception as e:
        print('错误类型是', e.__class__.__name__)
        print('错误明细是', e)
        print(soup)
        return_data['code'] = 500
        return_data['msg'] = e.__class__.__name__
        return return_data

    # 存储下载地址
    for script in scriptTags:
        if script.has_attr('aria2-link'):
            return_data['links'].append(script['aria2-link'])

    if len(return_data['links']) == 0:
        return_data['code'] = 400
        return_data['msg'] = '未获取到下载地址'
    else:
        if hasRedis:
            await r_l.rpush(url, *return_data['links'])
            await r_l.expire(url, 1 * 1 * 60 * 60)
    return return_data
