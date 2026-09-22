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
import socket
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Union
from urllib.parse import parse_qs, unquote, urlparse

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

# ---- 阿里云 WAF 挑战页(acw_sc__v2)----
# 网站前置了阿里云 WAF。家庭/住宅 IP 通常直接放行，但机房出口 IP（如 netcup）会被
# 判为风控，首页返回一个 JS 挑战页：正文只有一段混淆脚本，里面带
#   var arg1='<40 位十六进制>'
# 脚本把 arg1 按固定置换表重排、再与固定密钥按**字节**（每 2 个十六进制字符）XOR，
# 得到 acw_sc__v2 写进 cookie 后重新请求。
# 这个值是 arg1 的纯函数，不需要浏览器执行 JS，纯 Python 就能算出来（实测可稳定通过）。
ACW_KEY = '3000176000856006061501533003690027800375'
ACW_ORDER = [0xf, 0x23, 0x1d, 0x18, 0x21, 0x10, 0x1, 0x26, 0xa, 0x9, 0x13, 0x1f,
             0x28, 0x1b, 0x16, 0x17, 0x19, 0xd, 0x6, 0xb, 0x27, 0x12, 0x14, 0x8,
             0xe, 0x15, 0x20, 0x1a, 0x2, 0x1e, 0x7, 0x4, 0x11, 0x5, 0x3, 0x1c,
             0x22, 0x25, 0xc, 0x24]
WAF_ARG1_REG = re.compile(r"var\s+arg1\s*=\s*'([0-9A-Fa-f]+)'")

# 解析接口 action 的复用时长（秒）。站点不校验路径里的订单号，实测可长期复用；
# 取 30 分钟是为了万一将来站点改成校验时也能自愈。
POST_URI_TTL = 1800

# 解析结果缓存时长：跟着直链的实际有效期走，并限制在下面区间内。
# 站点直链有效期 2 小时，而缓存在链接还活着时就过期会导致重复解析、白扣次数。
# 读不出有效期时用 CACHE_TTL_DEFAULT（此前的固定值）。
CACHE_TTL_MIN = 600
CACHE_TTL_MAX = 7200
CACHE_TTL_DEFAULT = 3600


def waf_arg1(html: str) -> str:
    """命中 WAF 挑战页时返回其中的 arg1，否则返回空串"""
    m = WAF_ARG1_REG.search(html or '')
    return m.group(1) if m else ''


def acw_sc_v2(arg1: str) -> str:
    """由 arg1 算出 acw_sc__v2。

    注意第二步是**按字节** XOR（每 2 个十六进制字符一组转成整数），
    不是逐字符 XOR——写成逐字符也能跑出结果，但值完全不同、WAF 不认。
    """
    buf = [''] * len(ACW_ORDER)
    for i, ch in enumerate(arg1):
        for j, pos in enumerate(ACW_ORDER):
            if pos == i + 1:
                buf[j] = ch
    un = ''.join(buf)
    return ''.join(f'{int(un[i:i + 2], 16) ^ int(ACW_KEY[i:i + 2], 16):02x}'
                   for i in range(0, min(len(un), len(ACW_KEY)), 2))


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
        self._post_uri_at = 0.0
        self._post_uri_lock = threading.Lock()

    def _fetch_post_uri(self) -> str:
        """从首页解析出接口 action；失败时把首页落盘并打出诊断，然后抛错"""
        rep = None
        soup = None
        try:
            rep = self.get(const.pan_domain)
            soup = BeautifulSoup(rep.text, 'html.parser')
            action = find_post_uri(soup, rep.text)
            if not action:
                raise RuntimeError('首页未找到解析接口 form/action')
            return action
        except Exception as e:
            print(f'获取解析接口地址失败: {e.__class__.__name__}: {e}', flush=True)
            if rep is not None:
                # 首页这一层此前只打异常名，看不到服务器实际拿到的是什么页
                print(f'  首页诊断: {_dump_page(rep, soup, "home_page.html")}', flush=True)
                hint = waf_hint(rep.text)
                if hint:
                    print(f'  {hint}', flush=True)
            raise

    def _ensure_post_uri(self, force: bool = False) -> str:
        """取解析接口 action（带锁，server 模式多请求共用同一实例）。

        实测同一个 action 可以反复 POST：连续两次成功解析都能拿到下载按钮，
        甚至把 order id 换成伪造值也照样出结果 —— 路径里的订单号并不参与校验，
        根本不是「一次性的」。所以按 TTL 缓存复用，省掉每次解析前多打一次首页
        （机房出口 IP 上这一步还会额外撞一次 WAF 挑战）。

        缓存过期或 force 时重新获取；刷新失败但手里有旧值时降级沿用旧值，
        避免首页被 WAF 挡住时整个解析直接失败。
        """
        with self._post_uri_lock:
            if (not force and self._post_uri
                    and time.time() - self._post_uri_at < POST_URI_TTL):
                return self._post_uri
            try:
                action = self._fetch_post_uri()
            except Exception:
                if self._post_uri:
                    print(f'首页获取失败，降级沿用上次的接口地址 {self._post_uri}', flush=True)
                    return self._post_uri
                raise
            if action != self._post_uri:
                print(f'已刷新解析接口地址: {action}', flush=True)
            self._post_uri = action
            self._post_uri_at = time.time()
            return action

    @property
    def post_uri(self) -> str:
        return self._ensure_post_uri()

    def refresh_post_uri(self) -> str:
        """强制重新获取接口地址（提交失败时兜底重试用）"""
        return self._ensure_post_uri(force=True)

    def post_parse(self, data: dict) -> requests.models.Response:
        """提交解析表单；用缓存里的接口地址，请求异常时刷新地址再试一次"""
        headers = {'Referer': const.pan_domain + '/', 'Origin': const.pan_domain}
        try:
            return self.post(f'{const.pan_domain}{self.post_uri}', data=data, headers=headers)
        except Exception as e:
            print(f'提交解析请求失败({e.__class__.__name__})，刷新接口地址后重试一次', flush=True)
            return self.post(f'{const.pan_domain}{self.refresh_post_uri()}',
                             data=data, headers=headers)

    def _merge_headers(self, extra_headers):
        """合并 session headers 和额外 headers，使用副本避免引用污染"""
        merged = dict(self.session.headers)
        if isinstance(extra_headers, dict):
            merged.update(extra_headers)
        else:
            # 修复原 `for k, v in extra_headers` 把 dict 迭代成 key 再解包报错的问题
            merged.update(dict(extra_headers))
        return merged

    def _send(self, method: str, url: str, headers=None, params=None, data=None,
              timeout: int = 30, allow_redirects: bool = True) -> requests.models.Response:
        """统一入口：撞上阿里云 WAF 挑战页时自动解出 cookie 并重放"""
        kwargs = {'timeout': timeout, 'allow_redirects': allow_redirects}
        if headers is not None:
            kwargs['headers'] = self._merge_headers(headers)
        if params is not None:
            kwargs['params'] = params
        if data is not None:
            kwargs['data'] = data
        rep = self.session.request(method, url, **kwargs)
        for _ in range(2):
            arg1 = waf_arg1(rep.text)
            if not arg1:
                break
            self.session.cookies.set('acw_sc__v2', acw_sc_v2(arg1), domain=PAN_HOST)
            print('命中解析站 WAF 挑战页，已本地算出 acw_sc__v2 并重试', flush=True)
            rep = self.session.request(method, url, **kwargs)
        return rep

    def get(self, url: str, headers: Union[None, dict] = None, params=None) -> requests.models.Response:
        return self._send('GET', url, headers=headers, params=params, timeout=30)

    def post(self, url: str, headers: Union[None, dict] = None, data=None,
             allow_redirects: bool = True) -> requests.models.Response:
        return self._send('POST', url, headers=headers, data=data, timeout=60,
                          allow_redirects=allow_redirects)


# ---- 机器验证（算术图片验证码）----
# 站点在被风控时会把解析请求跳到 /toCaptcha/<card>，页面是一个算术图片验证码
#   <img src="/toCaptchaImg/<card>"> + POST /doCaptcha {card, answer}
# 实测要点（2026-09）：
#   1. 验证是**卡密级**的，不是 session 级 —— 答对一次后，另起一个全新 session
#      也能直接解析，所以不需要在同一次请求里做识别；
#   2. 答错**没有惩罚**：返回 200 并重新渲染验证页，可以无限重试；
#   3. 成功信号是 302 跳转 /，失败信号是 200 + captchaForm；
#   4. 图片是 easy-captcha 风格的彩色算术题（130x48），ddddocr 直接识别约 80%，
#      主要失败模式是 "+" 被吞掉（"5+1" 读成 "51"），所以额外做结构校验。
# 站点自带的 mathcode.onnx 那类模型对本站无效（160x60 标准字体，域不匹配）。
CAPTCHA_MAX_TRY = 4
_captcha_ocr = None


def ocr_captcha(img_bytes: bytes) -> str:
    """识别算术验证码，返回答案；识别不出返回 ''。

    没装 ddddocr 就返回 ''（此时调用方退回人工验证的提示，不影响原有行为）。
    """
    global _captcha_ocr
    try:
        if _captcha_ocr is None:
            from ddddocr import DdddOcr      # 可选依赖，懒加载
            _captcha_ocr = DdddOcr(show_ad=False)
        raw = _captcha_ocr.classification(img_bytes) or ''
    except ImportError:
        return ''
    except Exception as e:
        print(f'验证码识别异常: {e.__class__.__name__}: {e}', flush=True)
        return ''

    # 结构校验：本站固定是"单个数字 + 单个运算符 + 单个数字"，
    # 用单字符正则，避免把尾部 "=?" 误读出的数字并进操作数
    m = re.search(r'(\d)\s*([+\-*/×÷xX])\s*(\d)', raw)
    if not m:
        return ''
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    try:
        if op == '+':
            return str(a + b)
        if op == '-':
            return str(a - b)
        if op in 'xX*×':
            return str(a * b)
        return str(a // b)
    except ZeroDivisionError:
        return ''


def solve_captcha(s: 'MyRequests', card: str) -> bool:
    """自动过机器验证：取图 -> 识别 -> 提交，失败就换一张重试。

    答错无惩罚（实测只重新出题），所以直接重试到成功为止。
    返回 True 表示验证已通过，调用方可以重新发起解析。
    """
    for attempt in range(1, CAPTCHA_MAX_TRY + 1):
        try:
            img = s.get(f'{const.pan_domain}/toCaptchaImg/{card}')
        except Exception as e:
            print(f'  [{attempt}/{CAPTCHA_MAX_TRY}] 取验证码失败: {e.__class__.__name__}', flush=True)
            continue
        answer = ocr_captcha(img.content)
        if not answer:
            print(f'  [{attempt}/{CAPTCHA_MAX_TRY}] 验证码识别失败，换一张重试', flush=True)
            continue
        try:
            rep = s.post(f'{const.pan_domain}/doCaptcha',
                         data={'card': card, 'answer': answer},
                         headers={'Referer': f'{const.pan_domain}/toCaptcha/{card}'},
                         allow_redirects=False)
        except Exception as e:
            print(f'  [{attempt}/{CAPTCHA_MAX_TRY}] 提交验证码失败: {e.__class__.__name__}', flush=True)
            continue
        # 成功是 302 跳转 /；失败是 200 并重新渲染验证页
        if rep.status_code in (301, 302, 303, 307, 308):
            print(f'机器验证已通过（第 {attempt} 次识别，答案 {answer}）', flush=True)
            return True
        print(f'  [{attempt}/{CAPTCHA_MAX_TRY}] 答案 {answer} 未被接受，换一张重试', flush=True)
    return False


def link_expire_at(url: str) -> Optional[int]:
    """从直链里读出失效时间（UNIX 秒）；读不出返回 None。

    站点目前有 4 种直链形态，只有 S3/R2 预签名带标准化签名参数：
        X-Amz-Date=20260922T062320Z & X-Amz-Expires=7200
        → 失效时间 = X-Amz-Date + X-Amz-Expires
    （实测 X-Amz-Date 就是签发时刻：与解析完成的时刻只差 1 秒）

    其余形态读不出，不要假装能读：
      - 站点代理 walker: 附加串是 strrev(base64(json))，明文里只有 timestamp，
        语义未确认，不当作失效时间用
      - 站点代理 s20: 只有 link 参数是明文，disk/s/u 是服务端签名与加密
      - 源站裸链: 无任何签名参数
    """
    q = parse_qs(urlparse(url).query)
    raw_date = q.get('X-Amz-Date', [''])[0]
    raw_exp = q.get('X-Amz-Expires', [''])[0]
    if not raw_date or not raw_exp.isdigit():
        return None
    try:
        made = datetime.strptime(raw_date, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return int(made.timestamp()) + int(raw_exp)


def _is_dns_error(exc: BaseException) -> bool:
    """异常链里是否出现域名解析失败（gaierror）"""
    for _ in range(8):
        if isinstance(exc, socket.gaierror):
            return True
        exc = exc.__cause__ or exc.__context__
        if exc is None:
            break
    return False


def probe_link(url: str, timeout: int = 12) -> Optional[bool]:
    """探测直链可用性：True=能取数据，False=明确不可用，None=结论不明（保留）。

    只取 1 字节（range: bytes=0-0）避免整包下载；站点对直链校验 Referer。

    之所以要三态：SSL 校验失败是**本地信任库**的问题，不是死链 —— 实测同一链接
    requests 报 "unable to get local issuer certificate"（站点未下发完整证书链，
    certifi 补不上），而 curl 走系统证书库能正常 200。把它当成死链会把可用链接
    误删，所以只对明确信号下结论：
      - 域名解析不了 → False
      - HTTP 4xx/5xx（服务端明确拒绝，如 walker 的 530）→ False
      - 其它（SSL / 超时 / 连接重置）→ None
    """
    headers = {
        'user-agent': MyRequests.user_agent,
        'referer': f'{const.pan_domain}/',
        'range': 'bytes=0-0',
    }
    try:
        rep = requests.get(url, headers=headers, timeout=timeout, stream=True)
        ok = rep.status_code in (200, 206)
        rep.close()
        return True if ok else False
    except requests.exceptions.SSLError:
        return None
    except requests.exceptions.ConnectionError as e:
        return False if _is_dns_error(e) else None
    except Exception:
        return None


def usable_links(links: List[str], lines: Optional[List[dict]] = None,
                 probe: bool = True) -> List[str]:
    """筛掉已过期 / 明确不可用的直链。

    先用 expire_at 做零成本过滤，再对剩下的做一次轻量探活。
    探活后一条不剩时退回探活前的列表 —— 宁可让调用方自己试，
    也不要把候选全清空（超时/SSL 都可能只是本地或瞬时问题）。
    """
    expire = {l['url']: l.get('expire_at') for l in (lines or []) if l.get('url')}
    now = int(time.time())
    fresh = [u for u in links if not (expire.get(u) and expire[u] < now)]
    if not fresh:
        print(f'提示：{len(links)} 条直链的签名均已过期', flush=True)
        return links
    dropped = len(links) - len(fresh)

    if not probe or len(fresh) == 1:
        if dropped:
            print(f'已跳过 {dropped} 条过期直链，剩余 {len(fresh)} 条', flush=True)
        return fresh

    verdict = {u: probe_link(u) for u in fresh}
    alive = [u for u in fresh if verdict[u] is not False]
    dead = [u for u in fresh if verdict[u] is False]

    if not alive:
        print(f'提示：{len(fresh)} 条直链探活均失败，按原样交回（可能只是瞬时故障）', flush=True)
        return fresh

    if dropped or dead:
        detail = '、'.join(_host_of(u) for u in dead)
        print(f'已跳过 {dropped} 条过期 + {len(dead)} 条不可用直链'
              + (f'（不可用：{detail}）' if detail else ''), flush=True)
    unknown = [u for u in fresh if verdict[u] is None]
    if unknown:
        print('以下直链探活结论不明（多为本机证书/网络问题，仍保留）：'
              + '、'.join(_host_of(u) for u in unknown), flush=True)
    return alive


def tab_label_map(soup: BeautifulSoup) -> dict:
    """tab-pane id -> 标签名。

    站点用 Bootstrap tab 组织线路（尊享/专用/Gopeed/高速/Motrix/IDM/迅雷/迅雷新），
    同一个转发路由会在多个 tab 里复用（如 /direct/download 同时出现在
    主力线路与迅雷 tab），所以线路名只能按所在 tab 取，不能按路由判断。
    """
    labels = {}
    for link in soup.find_all('a', {'class': 'nav-link'}):
        href = (link.get('href') or '').strip()
        if href.startswith('#'):
            labels[href[1:]] = link.get_text(' ', strip=True)
    return labels


def _label_of(a, tab_labels: dict, route: str) -> str:
    """下载按钮的线路名：优先取所在 tab 的标签，取不到再退回路由映射"""
    pane = a.find_parent('div', class_='tab-pane')
    if pane is not None and pane.get('id') in tab_labels:
        return tab_labels[pane['id']]
    return const.route_label.get(route, route)


def parse_download_lines(soup: BeautifulSoup, buttons=None) -> Tuple[List[dict], List[str]]:
    """解析结果页的全部下载线路。

    返回 (lines, links)：
      lines 每项 {label, route, url, en, btn[, idm_cmd|thunder]}
      links 为**去重后的真实直链**，可直接交给 aria2 / IDM 使用。

    站点有 8 个线路 tab，但底层只有少数几个真实存储地址（预签名直链），
    各 tab 转发的是同一批直链，因此按直链去重。
    """
    lines: List[dict] = []
    links: List[str] = []
    seen = set()

    def _add(line: dict, direct: str):
        line['expire_at'] = link_expire_at(direct)   # 读不出有效期的形态为 None
        lines.append(line)
        if direct and direct not in seen:
            seen.add(direct)
            links.append(direct)

    if buttons is None:
        buttons = soup.find_all('a', {'class': const.download_btn_class})
    tab_labels = tab_label_map(soup)
    for a in buttons:
        href = (a.get('href') or '').strip()
        btn = a.get_text(strip=True)

        # 1) 站点中转: /master/download?l=<b64>&en=<sig>  (含 /s3 /download /direct /toAria2)
        if href.startswith('/') or href.startswith('http'):
            m = re.search(r'[?&](?:l|link)=([^&]+)', href)
            if not m:
                continue
            try:
                direct = b64url_decode(unquote(m.group(1)))
            except Exception:
                continue
            route = href.split('?')[0]
            en_m = re.search(r'[?&]en=([^&]+)', href)
            _add({'label': _label_of(a, tab_labels, route), 'route': route,
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
            _add({'label': _label_of(a, tab_labels, 'ef2://'), 'route': 'ef2://',
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
            _add({'label': _label_of(a, tab_labels, 'ct://'), 'route': 'ct://',
                  'url': direct, 'en': '', 'btn': btn, 'thunder': obj}, direct)

    return lines, links


def _dump_page(rep, soup, filename: str) -> str:
    """把响应页落盘并返回诊断摘要（站点改版/异地访问排查用）。

    日志里只有 HTTP 访问行、看不到失败原因，是因为失败信息此前只放进了响应体。
    这里统一把 HTTP 状态/落点/标题/正文摘要打出来，页面存盘便于直接比对结构。
    """
    title = soup.title.get_text(strip=True) if (soup is not None and soup.title) else ''
    body = ' '.join((soup.get_text(' ', strip=True) or '').split())[:200] if soup is not None else ''
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(rep.text)
        path = filename
    except Exception as e:
        path = f'(保存失败 {e.__class__.__name__}: {e})'
    return (f'HTTP={rep.status_code} 落点={rep.url} 已保存至 {path}\n'
            f'  标题: {title!r}\n  正文摘要: {body!r}')


def find_post_uri(soup: BeautifulSoup, html: str) -> str:
    """定位解析接口 action（首页 form#diskForm 的 action 每次渲染都不同）。

    不同网络环境/渲染版本下首页结构会变，因此多路兜底：
      1. form#diskForm 的 action（正常路径）
      2. 任意带 action 的 form（站点改 form id 时仍可用）
      3. 正文中直接出现的 /doOrder4Card/<数字>（action 被塞进 JS 变量时）
    """
    form = soup.find('form', {'id': 'diskForm'})
    if form is not None and (form.get('action') or '').strip():
        return form['action'].strip()
    for form in soup.find_all('form'):
        action = (form.get('action') or '').strip()
        if action:
            return action
    m = re.search(r'/doOrder4Card/\d+', html)
    return m.group() if m else ''


def waf_hint(html: str) -> str:
    """首页仍是 WAF 挑战页时给出兜底建议（正常情况 _send 已自动解过）"""
    if waf_arg1(html):
        return ('首页仍是阿里云 WAF 挑战页：自动解 acw_sc__v2 未通过，可在浏览器打开解析站，'
                '把 acw_sc__v2 填进 config.json 的 cookies 后重试')
    return ''


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
    """解析失败时落盘结果页并打印诊断信息（站点改版/异地访问排查用）"""
    print(f'解析失败: code={return_data["code"]} msg={return_data["msg"]!r} '
          f'{_dump_page(rep, soup, "result_page.html")}', flush=True)


def select_link(links: list, lines: Optional[list] = None, auto_select: Optional[bool] = None) -> str:
    """选择一条直链。

    多线路时交互式选择，auto_select 开启时自动挑一条。
    两种情况都先筛掉已过期 / 取不到数据的直链 —— 站点返回的直链里
    确实混着死链（实测有域名已无法解析的源站裸链），按顺序无脑取第一条会踩坑。
    """
    if auto_select is None:
        # 配置值是字符串，不能直接 bool()：bool('false') 结果也是 True
        auto_select = str(os.getenv('auto_select', '')).strip().lower() in ('1', 'true', 'yes', 'on')

    lines = lines or []
    expire = {l['url']: l.get('expire_at') for l in lines if l.get('url')}
    candidates = usable_links(links, lines)

    if auto_select:
        picked = candidates[0]
        print(f'已自动选择直链：{_host_of(picked)}', flush=True)
        return picked

    if len(candidates) == 1:
        return candidates[0]

    label_map = {}
    for line in lines:
        label_map.setdefault(line['url'], line['label'])
    now = int(time.time())

    print('可选的下载服务器：')
    for i, link in enumerate(candidates):
        label = label_map.get(link, '')
        exp = expire.get(link)
        # 已过期的在 usable_links 里就被滤掉了，这里显示的是剩余有效期
        left = f'  剩余 {int((exp - now) / 60)} 分钟' if exp else ''
        print(f'[{i}]: {_host_of(link)}' + (f'  ({label})' if label else '') + left)
    while True:
        choice = input('请输入序号选择下载服务器：')
        if not choice.isdecimal():
            print(f'请输入数字序号！0-{len(candidates) - 1}')
            continue
        choice = int(choice)
        if 0 <= choice < len(candidates):
            return candidates[choice]
        print(f'请输入正确的序号！0-{len(candidates) - 1}')


def cache_ttl_for(expire_at: Optional[int]) -> int:
    """按直链有效期决定解析结果缓存多久。

    站点直链有效期 2 小时，而缓存此前固定 1 小时 —— 链接还活着就重新解析，
    白扣一次次数。这里跟有效期对齐，并夹在 [CACHE_TTL_MIN, CACHE_TTL_MAX] 内；
    读不出有效期时退回默认值。
    """
    if not expire_at:
        return CACHE_TTL_DEFAULT
    return max(CACHE_TTL_MIN, min(CACHE_TTL_MAX, expire_at - int(time.time())))


async def jiexi(s: MyRequests, url: str) -> dict:
    """解析网赚盘链接，获取真实下载地址。

    return_data 主要字段：
      code/msg/cache/raw_url/links/lines/end_time
      expire_at: 本批已知直链里**最晚**的失效时间（UNIX 秒）。
                 只有 S3/R2 预签名形态读得出（见 link_expire_at）；
                 全部读不出时为 None。各条线路的精确值另见 lines[i]['expire_at']。
    """
    return_data = {'code': 200, 'raw_url': url, 'links': [], 'lines': [],
                   'msg': '', 'cache': 'miss'}
    if not url.endswith('#re') and hasRedis:
        link_cache = r_l.lrange(url, 0, -1)
        link_cache = [link.decode('utf-8') for link in link_cache]
        if link_cache:
            return_data['cache'] = 'hit'
            return_data['links'] = link_cache
            # 缓存命中时补回会员到期时间与线路明细（原逻辑只缓存直链，
            # end_time 和 lines 会丢失，导致缓存命中的解析在选线路时没有线路名）
            meta = r_l.get(f'{url}#meta')
            if meta:
                meta = json.loads(meta)
                return_data['end_time'] = meta.get('end_time', '')
                return_data['lines'] = meta.get('lines', [])
                return_data['expire_at'] = meta.get('expire_at')
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
        rep = s.post_parse(data)
    except Exception as e:
        print('下载链接解析失败', e.__class__.__name__)
        return_data['code'] = 500
        return_data['msg'] = '下载链接解析失败'
        return return_data

    if 'toCaptcha' in rep.url:
        print('遭遇到机器验证', flush=True)
        captcha_url = f'{const.pan_domain}/toCaptcha/{os.environ["card"]}'
        if solve_captcha(s, os.environ['card']):
            # 验证通过后重新发起一次解析（验证是卡密级的，重发即可）
            try:
                rep = s.post_parse(data)
            except Exception as e:
                print('验证通过后重新解析失败', e.__class__.__name__)
                return_data['code'] = 500
                return_data['msg'] = '下载链接解析失败'
                return return_data
        if 'toCaptcha' in rep.url:
            # 没装 ddddocr 或连续识别失败：保留原有的人工处理入口
            return_data['code'] = 403
            return_data['msg'] = '遭遇到机器验证'
            if platform.system() == 'Windows':
                import pyperclip
                pyperclip.copy(captcha_url)
                print('已将验证网址复制到剪贴板')
            print(f'自动验证未通过，请手动打开完成验证：{captcha_url}', flush=True)
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
    # 本批直链里最晚的已知失效时间：过了它整批就都不可用了（读不出的形态不计入）
    known = [l['expire_at'] for l in lines if l.get('expire_at')]
    return_data['expire_at'] = max(known) if known else None

    if not links:
        return_data['code'] = 400
        return_data['msg'] = '未获取到下载地址'
        dump_fail_page(rep, soup, return_data)
    elif hasRedis:
        # 同步 redis 库，不使用 await（原代码的 await 会导致 TypeError）
        ttl = cache_ttl_for(return_data['expire_at'])
        # 先删旧值再写：否则残留的旧直链会和新值混在一个 list 里
        r_l.delete(url)
        r_l.rpush(url, *links)
        r_l.expire(url, ttl)
        r_l.set(f'{url}#meta',
                json.dumps({'end_time': return_data.get('end_time', ''),
                            'lines': lines,
                            'expire_at': return_data['expire_at']}), ex=ttl)
        print(f'解析结果已缓存 {ttl} 秒（对齐直链有效期）', flush=True)
    return return_data
