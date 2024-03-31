import os
import re

import requests
from bs4 import BeautifulSoup

from tools import const
from tools import tool
from tools.tool import myRequests


def iycdn(url) -> str:
    s = requests.session()
    domain = 'https://' + url.split('/')[-2]
    rep = s.get(url)
    soup = BeautifulSoup(rep.text, 'html.parser')
    renji_js_url = domain + soup.find('script').attrs['src']
    renji_js = s.get(renji_js_url).text
    import re

    # 使用正则表达式提取key值
    pattern_k = r'key\s*=\s*"([^"]+)"'
    pattern_v = r'value\s*=\s*"([^"]+)"'
    pattern_t = r'yanzheng_ip.php\?type=([^&]+)'
    pattern_yz = r'"(\/.+_yanzheng_ip\.php)'
    match_k = re.search(pattern_k, renji_js)
    match_v = re.search(pattern_v, renji_js)
    match_t = re.search(pattern_t, renji_js)
    match_yz = re.search(pattern_yz, renji_js)

    if match_k and match_v and match_t:
        params = {
            'type': match_t.group(1),
            'key': match_k.group(1),
            'value': tool.md5_encode(tool.string_to_hex(match_v.group(1))),
        }
        s.get(domain + match_yz.group(1), params=params)
        rep = s.get(url)
        soup = BeautifulSoup(rep.text, 'html.parser')
        name = re.findall(r'>(.*?)<', soup.find('input', {'id': 'f_html'}).attrs['value'])[0]
        return name
    else:
        return ''


def rosefile(url: str):
    # eg.https://rosefile.net/pm98zjeu2b/xa754.rar.html
    return url.split('/')[-1][:-5]


def urlMod1(url: str):
    # eg.https://koalaclouds.com/971f6c37836c82fb/xm1901.part1.rar
    return url.split('/')[-1]


def row_fluid(rep_text: str):
    # eg.https://www.567file.com/file-1387363.html
    # eg.https://ownfile.net/files/T09mMzQ5ODUx.html
    # eg.http://www.feiyupan.com/file-1400.html
    # eg.http://www.xunniupan.com/file-2475170.html
    soup = BeautifulSoup(rep_text, 'html.parser')
    return soup.find('div', {'class': 'row-fluid'}).div.h1.text


def feimaoyun(url: str):
    # eg.https://www.feimaoyun.com/s/398y7f0l
    key = url.split('/')
    s = myRequests()
    rep = s.post('https://www.feimaoyun.com/index.php/down/new_detailv2', data={'code': key})
    if rep.status_code == 200:
        return rep.json()['data']['file_name']
    else:
        return input(f'解析失败，请手动填写文件名')


def dufile(rep_text: str):
    # eg.https://dufile.com/file/0c7184f05ecdce0f.html
    soup = BeautifulSoup(rep_text, 'html.parser')
    return soup.find('h2', {'class': 'title'}).text.split('  ')[-1]


def align_absbottom(rep_text: str):
    # eg.http://www.xingyaopan.com/fs/tuqlqxxnyzggaag
    # eg.http://www.kufile.net/file/QUExNTM5NDg1.html
    # eg.http://www.rarclouds.com/file/QUExNTE5Mjgz.html
    soup = BeautifulSoup(rep_text, 'html.parser')
    name = soup.find('title').text.split(' - ')[0]
    file_type = soup.find('img', {'align': 'absbottom'})['src'].split('/')[-1].split('.')[0]
    return f'{name}.{file_type}'


def dudujb(rep_text: str):
    # eg.https://www.dudujb.com/file-1105754.html
    soup = BeautifulSoup(rep_text, 'html.parser')
    soup = soup.findAll('input', {'class': 'txtgray'})[-1]['value']
    return BeautifulSoup(soup, 'html.parser').text


def new_title(url: str):
    # eg.http://www.xfpan.cc/file/QUExMzE4MDUx.html
    # eg.https://www.skyfileos.com/90ea219698c62ea5
    s = myRequests()
    rep = s.get(url.replace(r'/file/', r'/down/'), headers={'Referer': url})
    if rep.status_code == 200:
        soup = BeautifulSoup(rep.text, 'html.parser')
        return soup.find('title').text.split(' - ')[0]
    else:
        return input(f'解析失败，请手动填写文件名')


def expfile(url: str):
    # eg.http://www.expfile.com/file-1464062.html
    s = myRequests()
    rep = s.get(url.replace('file-', 'down2-'))
    if rep.status_code == 200:
        soup = BeautifulSoup(rep.text, 'html.parser')
        return soup.find('title').text.split(' - ')[0]
    else:
        return input(f'解析失败，请手动填写文件名({url})')


def titleMod1(rep_text: str):
    # eg.https://www.baigepan.com/s/iU36ven9Wu
    # eg.https://www.jisuyp.com/s/a6fm2yePRo
    # eg.http://www.qqupload.com/3uj4i
    soup = BeautifulSoup(rep_text, 'html.parser')
    return soup.find('title').text.split(' - ')[0]


async def get_name(url):
    s = myRequests()
    if os.environ['auto_name'] == 'false':
        return input('文件名：'), url

    rep = requests.models.Response
    # 从链接中就可以获取文件名的网站、链接需要进行转换的网站
    if not tool.is_in_list(const.white_domain, url):
        rep = s.get(url)
        if rep.status_code != 200 and rep.status_code != 301 and rep.status_code != 302:
            return input('解析失败，请手动输入文件名：'), url
        url = rep.url
        # 针对200状态码的跳转
        soup = BeautifulSoup(rep.text, 'html.parser')
        if soup.find('meta').get('http-equiv') == 'refresh':
            # META http-equiv="refresh" 实现网页自动跳转
            url = re.search(r'[a-zA-z]+://\S*', soup.find('meta').get('content')).group()
            rep = s.get(url)

    try:
        if 'rosefile' in url:
            name = rosefile(url)
        elif tool.is_in_list(['koalaclouds', 'koolaayun'], url):
            name = urlMod1(url)
        elif 'feimaoyun' in url:
            name = feimaoyun(url)
        elif tool.is_in_list(['567', 'ownfile', 'feiyupan', 'xunniu'], url.rsplit('/', maxsplit=1)[0]):
            name = row_fluid(rep.text)
        elif 'dufile' in url:
            name = dufile(rep.text)
        elif tool.is_in_list(['xingyao', 'xywpan', 'kufile', 'rarclouds'], url):
            name = align_absbottom(rep.text)
        elif 'dudujb' in url:
            name = dudujb(rep.text)
        elif tool.is_in_list(['xfpan', 'skyfileos'], url):
            name = new_title(url)
        elif 'expfile' in url:
            name = expfile(url)
        elif tool.is_in_list(['baigepan', 'jisuyp', 'qqupload'], url):
            name = titleMod1(rep.text)
        elif 'iycdn' in url:
            name = iycdn(url)
        else:
            name = input(f'暂不支持该网盘自动解析文件名，请手动填写({url}')
        print(f'获取文件名{name}成功', flush=True)
    except:
        return None, url
    return name, url
