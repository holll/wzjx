import asyncio
import base64
import hashlib
import json
import os
import platform
import re
import sys

from bs4 import BeautifulSoup

import tools.tool
from tools import const, get_name

if platform.system() == 'Windows':
    import toIdm
    import pyperclip

config_path = './config.json'
s = tools.tool.myRequests()


def init():
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    for key in config:
        os.environ[key] = config[key]
    rep = s.get(const.pan_domain)
    soup = BeautifulSoup(rep.text, 'html.parser')
    s.post_uri = soup.find('form', {'id': 'diskForm'})['action']
    print(f'初始化配置完成，打印关键参数(自动获取文件名：{os.getenv("auto_name")})')
    print(f'卡密：{os.environ["card"]}\nRPC地址：{os.environ["aria2_rpc"]}')
    print(f'aria2_token：{config.get("aria2_token")}\n下载地址：{config.get("download_path")}')
    sys.stdout.flush()


async def jiexi(url):
    return_data = {'code': 0, 'links': [], 'msg': ''}
    data = {
        'browser': '',
        'url': url,
        'card': os.environ['card']
    }
    try:
        rep = s.post(f'{const.pan_domain}{s.post_uri}', data=data)
    except Exception as e:
        print('下载链接解析失败', e.__class__.__name__)
        return_data['code'] = 1
        return_data['msg'] = '下载链接解析失败'
        return return_data
    if 'toCaptcha' in rep.url:
        print('遭遇到机器验证')
        return_data['code'] = 1
        return_data['msg'] = '遭遇到机器验证'
        if platform.system() == 'Windows':
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
        return_data['code'] = 1
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
        return_data['code'] = 1
        return_data['msg'] = e.__class__.__name__
        return return_data

    # 存储下载地址
    aria2_link = list()
    for script in scriptTags:
        if script.has_attr('aria2-link'):
            aria2_link.append(script['aria2-link'])

    return_data['links'] = aria2_link
    return return_data


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
            name, return_data = await asyncio.gather(get_name.get_name(url), jiexi(url))
            if return_data['code'] != 0:
                print(return_data['msg'])
                continue
            down_link = tools.tool.select_link(return_data['links'])
            url_domain = re.search(const.domain_reg, down_link).group()
            print(f'获取下载链接{url_domain}...成功\n{return_data["end_time"]}，请记得及时续费', flush=True)
            download(down_link, name[1], name[0], is_xc='')


if __name__ == '__main__':
    args = sys.argv
    if len(args) == 1:
        config_path = './config.json'
    else:
        config_path = args[1]
    if sys.version_info < (3, 7):
        asyncio.get_event_loop().run_until_complete(main())
    else:
        asyncio.run(main())
