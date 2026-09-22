import asyncio
import base64
import hashlib
import json
import os
import platform
import re
import sys
import time
import traceback
from datetime import datetime

import tools.tool as tool
from tools import const, get_name

if platform.system() == 'Windows':
    import toIdm
    import pyperclip

config_path = './config.json'
s = tool.MyRequests()


def init():
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    for key in config:
        os.environ[key] = config[key]
    print(f'初始化配置完成(自动获取文件名：{config.get("auto_name")})')
    print(f'RPC地址：{config.get("aria2_rpc")}')
    print(f'下载路径：{config.get("download_path")}')
    sys.stdout.flush()


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


def run_server():
    """启动 API 服务器模式：python index.py -server [config_path]"""
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        print('Flask 未安装，请执行: pip install flask')
        sys.exit(1)

    init()
    _client = tool.MyRequests()

    app = Flask(__name__)

    @app.route('/api/parse', methods=['POST'])
    def parse():
        data = request.get_json(silent=True)
        if not data or 'url' not in data:
            print('[parse] 缺少 url 参数', flush=True)
            return jsonify({'code': 400, 'msg': '缺少 url 参数'}), 400
        url = data['url']
        try:
            result = asyncio.run(tool.jiexi(_client, url))
        except Exception as e:
            print(f'[parse] 解析异常 {e.__class__.__name__}: {e}', flush=True)
            traceback.print_exc()
            return jsonify({'code': 500, 'msg': str(e)}), 500
        # 失败信息此前只放在响应体里，日志只能看到 HTTP 200，排查无迹可寻
        level = 'OK' if result.get('code') == 200 else 'FAIL'
        print(f"[parse] {level} code={result.get('code')} cache={result.get('cache')} "
              f"lines={len(result.get('lines') or [])} links={len(result.get('links') or [])} "
              f"msg={result.get('msg') or '-'} url={url}", flush=True)
        return jsonify(result)

    @app.route('/api/health', methods=['GET'])
    def health():
        return jsonify({'status': 'ok'})

    host = os.environ.get('API_HOST', '127.0.0.1')
    port = int(os.environ.get('API_PORT', 5000))
    print(f'API 服务启动: http://{host}:{port}')
    app.run(host=host, port=port)


async def main():
    init()
    while True:
        url = input('\n请输入下载链接/续传码：')
        if 'XC://' in url:
            download('', '', '', is_xc=url)
        else:
            name, return_data = await asyncio.gather(get_name.get_name(url), tool.jiexi(s, url))
            if return_data['code'] != 200:
                print(return_data['msg'])
                continue
            down_link = tool.select_link(return_data['links'], return_data.get('lines'))
            _m = re.search(const.domain_reg, down_link)
            url_domain = _m.group() if _m else down_link[:60]
            print(f'获取下载链接{url_domain}...成功\n{return_data.get("end_time")}，请记得及时续费', flush=True)
            exp = return_data.get('expire_at')
            if exp:
                print(f'直链失效时间 {datetime.fromtimestamp(exp):%Y-%m-%d %H:%M:%S}'
                      f'（剩 {int((exp - time.time()) / 60)} 分钟）', flush=True)
            download(down_link, name[1], name[0], is_xc='')


if __name__ == '__main__':
    args = sys.argv
    if len(args) >= 2 and args[1] == '-server':
        if len(args) >= 3:
            config_path = args[2]
        run_server()
    else:
        if len(args) == 1:
            config_path = './config.json'
        else:
            config_path = args[1]
        if sys.version_info < (3, 7):
            asyncio.get_event_loop().run_until_complete(main())
        else:
            asyncio.run(main())