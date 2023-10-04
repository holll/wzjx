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
from bs4 import BeautifulSoup

import tools.tool
from tools import const,get_name

if platform.system() == 'Windows':
    import toIdm

config_path = './config.json'



def init():
    global s,proxies
    s = tools.tool.myRequests()
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
        rep = s.post(f'{const.pan_domain}/doOrder4Card', data=data)
    except Exception as e:
        print('下载链接解析失败', e.__class__.__name__)
        return None
    if 'toCaptcha' in rep.url:
        print('遭遇到机器验证')
        if platform.system() == 'Windows':
            pyperclip.copy(f'{const.pan_domain}/toCaptcha/' + os.environ['card'])
            print('已将验证网址复制到剪贴板，程序将在5秒后退出')
        else:
            print(f'{const.pan_domain}/toCaptcha/' + os.environ['card'])
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


async def main():
    init()
    while True:
        url = input('\n请输入下载链接/续传码：')
        if 'XC://' in url:
            download('', '', '', is_xc=url)
        else:
            name, down_link = await asyncio.gather(get_name.get_name(url), jiexi(url))
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
