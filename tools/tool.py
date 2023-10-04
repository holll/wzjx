import hashlib
from typing import Union

import requests
import urllib3
from requests.adapters import HTTPAdapter

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
