#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单链接调试脚本：解析一条网盘分享链接并打印全部下载线路。

用法:
    python 1.py <网盘分享链接>
    python 1.py https://windfiles.com/share/39eFm5ff4dab71

安全约定：卡密等凭据一律从 config.json 读取，不要写进代码。
（原文件曾硬编码卡密与固定 cookie/订单 ID，那些都是会失效且会泄露凭据的写法。）
"""

import asyncio
import json
import os
import sys

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')


def load_config() -> dict:
    with open(CONFIG_PATH, encoding='utf-8') as f:
        config = json.load(f)
    for key, value in config.items():
        os.environ[key] = value
    return config


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    config = load_config()
    if not config.get('card'):
        print('请先在 config.json 中填写 card（卡密）')
        return 1

    from tools import tool

    result = asyncio.run(tool.jiexi(tool.MyRequests(), sys.argv[1]))

    print(f"\n状态   : {result['code']} {result.get('msg', '')}")
    print(f"缓存   : {result.get('cache')}")
    if result.get('end_time'):
        print(f"会员到期: {result['end_time']}")

    lines = result.get('lines', [])
    if lines:
        print(f"\n线路明细 ({len(lines)} 条):")
        for line in lines:
            print(f"  {line['label']:<12} {line['route']:<20} {line['btn']}")

    links = result.get('links', [])
    if links:
        print(f"\n去重直链 ({len(links)} 条, S3 预签名, 约 2 小时有效):")
        for i, url in enumerate(links):
            print(f"  [{i}] {url}")

    return 0 if result['code'] == 200 else 2


if __name__ == '__main__':
    sys.exit(main())
