"""解析站点(haoduopan.com)交互封装。

2026-09 站点改版记录（旧逻辑失效原因）：
  1. 首页 form#diskForm 的 action 每次渲染都不同，必须先 GET 首页再提交；
  2. 结果页下载按钮 class=btn btn-info btn-sm，真实直链以 base64url 编码放在
     href 的 l(站点中转) / link(Motrix) 参数里，解码后是 S3 预签名直链（2 小时有效）；
  3. **旧版的 aria2-link 属性已被移除**，原 `a['aria2-link']` 取值方式完全失效；
  4. 错误页容器由 div.col.text-center 改为 div.col-12.text-center；
  5. 服务端不校验 fingerprint（实测随机 32 位 hex 同样可以正常解析）。
"""

import base64
import hashlib
import json
import os
import platform
import re
import secrets
from typing import List, Optional, Tuple, Union
from urllib.parse import unquote, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

try:
    import redis

    hasRedis = True
    pool_db1 = redis.ConnectionPool(host='127.0.0.1', port=6379, db=2)
    r_l = redis.Redis(connection_pool=pool_db1)
except Exception:
    hasRedis = False
from tools import const


def string_to_hex(ac_str):
    return ''.join(str(ord(char)) for char in ac_str)


def md5_encode(word):
    """使用MD5加密"""
    return hashlib.md5(word.encode()).hexdigest()


def is_in_list(arr: list, value: str) -> bool:
    """value 中是否包含 arr 里的任一子串"""
    return any(web in value for web in arr)


def b64url_decode(s: str) -> str:
    """站点把 S3 预签名直链以 base64url 形式塞在 l / link 参数中"""
    s = s.replace('-', '+').replace('_', '/').strip()
    s += '=' * ((-len(s)) % 4)
    return base64.b64decode(s).decode('utf-8', 'replace')


PAN_HOST = const.pan_domain.split('//')[-1].split('/')[0]


def load_cookies(session: requests.Session, cookie_str: str) -> None:
    """把 "k=v; k2=v2" 形式的 cookie 串注入 session。

    解析站前置了阿里云 WAF，其中 acw_sc__v2 需要浏览器执行 JS 才能生成，
    Python 侧无法自动获取，因此支持从配置手工粘贴注入（实测当前非必需，
    但 WAF 策略收紧时可作为兜底）。
    """
    if not cookie_str:
        return
    host = PAN_HOST
    for item in cookie_str.split(';'):
        item = item.strip()
        if not item or '=' not in item:
            continue
        k, _, v = item.partition('=')
        session.cookies.set(k.strip(), v.strip(), domain=host)
    # cookie 串里可能残留旧卡密，统一以当前配置为准
    if os.getenv('card'):
        session.cookies.set('card', os.environ['card'], domain=host)


class MyRequests:
    retries = urllib3.util.retry.Retry(total=3, backoff_factor=0.1)
    user_agent = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36')

    def __init__(self, headers: Union[None, dict] = None):
        # 每个实例独立的 session（修复原类变量共享 session 的隐患）
        self.session = requests.session()
        self.session.headers = {
            'user-agent': MyRequests.user_agent,
        }
        if headers is not None:
            self.session.headers.update(headers)
        self.session.trust_env = False
        self.session.mount('http://', HTTPAdapter(max_retries=MyRequests.retries))
        self.session.mount('https://', HTTPAdapter(max_retries=MyRequests.retries))
        # 懒加载：延迟到首次使用时获取解析接口地址
        self._post_uri = None

    def _ensure_post_uri(self):
        """懒加载：首次调用时获取解析接口地址，避免构造函数中阻塞网络请求"""
        if self._post_uri is None:
            try:
                rep = self.session.get(const.pan_domain, timeout=20)
                soup = BeautifulSoup(rep.text, 'html.parser')
                form = soup.find('form', {'id': 'diskForm'})
                if form is None or not form.get('action'):
                    raise RuntimeError('首页未找到 diskForm，站点结构可能已变更')
                self._post_uri = form['action']
            except Exception as e:
                print(f'获取解析接口地址失败: {e.__class__.__name__}: {e}')
                raise

    @property
    def post_uri(self):
        """每次解析都要重新取，因为 action 里的订单 ID 是一次性的"""
        self._post_uri = None
        self._ensure_post_uri()
        return self._post_uri

    def _merge_headers(self, extra_headers):
        """合并 session headers 和额外 headers，使用副本避免引用污染"""
        merged = dict(self.session.headers)
        if isinstance(extra_headers, dict):
            merged.update(extra_headers)
        else:
            # 修复原 `for k, v in extra_headers` 把 dict 迭代成 key 再解包报错的问题
            merged.update(dict(extra_headers))
        return merged

    def get(self, url: str, headers: Union[None, dict] = None, params=None) -> requests.models.Response:
        if headers is not None:
            return self.session.get(url, headers=self._merge_headers(headers), params=params, timeout=30)
        return self.session.get(url, params=params, timeout=30)

    def post(self, url: str, headers: Union[None, dict] = None, data=None) -> requests.models.Response:
        if headers is not None:
            return self.session.post(url, headers=self._merge_headers(headers), data=data, timeout=60)
        return self.session.post(url, data=data, timeout=60)


def parse_download_lines(soup: BeautifulSoup, buttons=None) -> Tuple[List[dict], List[str]]:
    """解析结果页的全部下载线路。

    返回 (lines, links)：
      lines 每项 {label, route, url, en, btn[, idm_cmd|thunder]}
      links 为**去重后的真实直链**，可直接交给 aria2 / IDM 使用。

    站点有 7 个线路 tab（专用/高速/Motrix/IDM/迅雷/迅雷新/Gopeed），
    但底层只有 2 个真实存储地址（阿里云 S3 + Cloudflare R2 备份），
    16 个按钮转发的是同一批预签名直链，因此按直链去重。
    """
    lines: List[dict] = []
    links: List[str] = []
    seen = set()

    def _add(line: dict, direct: str):
        lines.append(line)
        if direct and direct not in seen:
            seen.add(direct)
            links.append(direct)

    if buttons is None:
        buttons = soup.find_all('a', {'class': const.download_btn_class})
    for a in buttons:
        href = (a.get('href') or '').strip()
        btn = a.get_text(strip=True)

        # 1) 站点中转: /master/download?l=<b64>&en=<sig>  (含 /s3 /download /direct /toAria2)
        if href.startswith('/') or href.startswith('http'):
            path = href if href.startswith('http') else href
            m = re.search(r'[?&](?:l|link)=([^&]+)', path)
            if not m:
                continue
            try:
                direct = b64url_decode(unquote(m.group(1)))
            except Exception:
                continue
            route = path.split('?')[0]
            en_m = re.search(r'[?&]en=([^&]+)', path)
            _add({'label': const.route_label.get(route, route), 'route': route,
                  'url': direct, 'en': en_m.group(1) if en_m else '', 'btn': btn}, direct)

        # 2) IDM: ef2://<base64(命令行)>  命令行内含直链/Referer/UA/-sign
        elif href.startswith('ef2://'):
            try:
                cmd = b64url_decode(href[len('ef2://'):])
            except Exception:
                continue
            m = re.search(r'-u\s+"?([^"\s]+)', cmd)
            if not m:
                continue
            _add({'label': const.route_label['ef2://'], 'route': 'ef2://',
                  'url': m.group(1), 'en': '', 'btn': btn, 'idm_cmd': cmd}, m.group(1))

        # 3) 迅雷新: ct://<base64(JSON)>  JSON 内含 link/name/key/referer
        elif href.startswith('ct://'):
            try:
                obj = json.loads(b64url_decode(href[len('ct://'):]))
            except Exception:
                continue
            direct = obj.get('link', '')
            if not direct:
                continue
            _add({'label': const.route_label['ct://'], 'route': 'ct://',
                  'url': direct, 'en': '', 'btn': btn, 'thunder': obj}, direct)

    return lines, links


def extract_error_text(soup: BeautifulSoup) -> str:
    """从站点提示页提取文案。

    层级形如 div.alert.alert-white.my_container > div.alert.alert-secondary > p...
    按 const.error_msg_class_list 优先级取首个命中的容器，先拼 <p>；容器里没有 <p>
    时退化为整块文本（避免像 "返回首页" 这类占位容器返回空串）。
    """
    for sel in const.error_msg_class_list:
        node = soup.find('div', {'class': sel})
        if node is None:
            continue
        # 标题也要带上（如"文件正在为您准备中"就在 h1 里，只取 <p> 会丢掉最关键的结论）
        text = ' '.join(tag.get_text(' ', strip=True)
                        for tag in node.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p']))
        text = ' '.join(text.split())
        if not text:
            text = ' '.join((node.get_text(' ', strip=True) or '').split())
        if text:
            return text[:300]
    return ''


def _host_of(url: str) -> str:
    """安全取主机名，畸形直链不抛异常"""
    return urlparse(url).netloc or (url[:60] if url else '(空)')


def dump_fail_page(rep, soup, return_data: dict) -> None:
    """解析失败时落盘结果页并打印诊断信息（站点改版/异地访问排查用）。

    日志里只有 HTTP 访问行、看不到失败原因，是因为失败信息此前只放进了响应体。
    这里统一打印 code/msg/标题/落点/正文摘要，并把页面存成 result_page.html
    （已在 .gitignore 中），便于直接比对站点结构。
    """
    title = soup.title.get_text(strip=True) if soup.title else ''
    body = ' '.join((soup.get_text(' ', strip=True) or '').split())[:200]
    path = 'result_page.html'
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(rep.text)
    except Exception as e:
        path = f'(保存失败 {e.__class__.__name__}: {e})'
    print(f'解析失败: code={return_data["code"]} msg={return_data["msg"]!r} '
          f'HTTP={rep.status_code} 落点={rep.url} 页面已保存至 {path}\n'
          f'  标题: {title!r}\n  正文摘要: {body!r}', flush=True)


def select_link(links: list, lines: Optional[list] = None, auto_select: Optional[bool] = None) -> str:
    """选择一条直链。多线路时交互式选择，auto_select 开启时自动挑一条。"""
    if auto_select is None:
        # 配置值是字符串，不能直接 bool()：bool('false') 结果也是 True
        auto_select = str(os.getenv('auto_select', '')).strip().lower() in ('1', 'true', 'yes', 'on')

    if auto_select:
        # 站点按线路优先级返回，第一条即专用线路，优先使用
        picked = links[0]
        print(f'已自动选择直链：{_host_of(picked)}', flush=True)
        return picked

    if len(links) == 1:
        return links[0]

    label_map = {}
    if lines:
        for line in lines:
            label_map.setdefault(line['url'], line['label'])

    print('可选的下载服务器：')
    for i, link in enumerate(links):
        label = label_map.get(link, '')
        print(f'[{i}]: {_host_of(link)}' + (f'  ({label})' if label else ''))
    while True:
        choice = input('请输入序号选择下载服务器：')
        if not choice.isdecimal():
            print(f'请输入数字序号！0-{len(links) - 1}')
            continue
        choice = int(choice)
        if 0 <= choice < len(links):
            return links[choice]
        print(f'请输入正确的序号！0-{len(links) - 1}')


async def jiexi(s: MyRequests, url: str) -> dict:
    """解析网赚盘链接，获取真实下载地址"""
    return_data = {'code': 200, 'raw_url': url, 'links': [], 'lines': [],
                   'msg': '', 'cache': 'miss'}
    if not url.endswith('#re') and hasRedis:
        link_cache = r_l.lrange(url, 0, -1)
        link_cache = [link.decode('utf-8') for link in link_cache]
        if link_cache:
            return_data['cache'] = 'hit'
            return_data['links'] = link_cache
            # 缓存命中时补回会员到期时间（原逻辑只缓存了直链，end_time 会丢失）
            meta = r_l.get(f'{url}#meta')
            if meta:
                return_data['end_time'] = json.loads(meta).get('end_time', '')
            return return_data
    else:
        url = url.replace('#re', '')

    # 可选：首次解析时注入配置里的 cookie（WAF 兜底，见 load_cookies 说明）
    if not getattr(s, '_cookies_loaded', False):
        load_cookies(s.session, os.getenv('cookies', ''))
        s._cookies_loaded = True

    fingerprint = s.session.cookies.get('fingerprint', '')
    if not fingerprint:
        # 站点不校验指纹（实测随机值同样可解析），用密码学随机数即可
        fingerprint = secrets.token_hex(16)
        s.session.cookies.set('fingerprint', fingerprint, domain=PAN_HOST)
        print(f'已生成临时设备指纹: {fingerprint}', flush=True)

    data = {
        'url': url,
        'fingerprint': fingerprint,
        'card': os.environ['card']
    }
    try:
        rep = s.post(f'{const.pan_domain}{s.post_uri}', data=data,
                     headers={'Referer': const.pan_domain + '/', 'Origin': const.pan_domain})
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
    download_btns = soup.find_all('a', {'class': const.download_btn_class})

    # 提示/错误页：仅在整页没有任何下载按钮时才认定。
    # （col-12 是 bootstrap 通用栅格类，正常结果页也可能存在同名容器，
    #   旧版按 col-12 直接判定会把正常页误判成错误页）
    if not download_btns:
        error_text = extract_error_text(soup)
        if error_text:
            return_data['code'] = 400
            return_data['msg'] = error_text
            dump_fail_page(rep, soup, return_data)
            return return_data

    # 会员到期时间
    try:
        end_time_tag = soup.find('span', {'class': const.end_time_class})
        if end_time_tag and end_time_tag.span:
            return_data['end_time'] = end_time_tag.span.text.strip()
    except Exception as e:
        print('获取到期时间失败', e.__class__.__name__)

    try:
        lines, links = parse_download_lines(soup, download_btns)
        # 兜底：老版页面的 aria2-link 属性（站点若回滚仍可用）
        if not links:
            for tag in soup.find_all(attrs={'aria2-link': True}):
                links.append(tag['aria2-link'])
    except Exception as e:
        print('解析下载地址异常', e.__class__.__name__, e)
        return_data['code'] = 500
        return_data['msg'] = e.__class__.__name__
        return return_data

    return_data['lines'] = lines
    return_data['links'] = links

    if not links:
        return_data['code'] = 400
        return_data['msg'] = '未获取到下载地址'
        dump_fail_page(rep, soup, return_data)
    elif hasRedis:
        # 同步 redis 库，不使用 await（原代码的 await 会导致 TypeError）
        r_l.rpush(url, *links)
        r_l.expire(url, 3600)
        r_l.set(f'{url}#meta', json.dumps({'end_time': return_data.get('end_time', '')}), ex=3600)
    return return_data
