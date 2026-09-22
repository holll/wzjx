#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证码识别回归测试。

用法：python tests/test_captcha_ocr.py

依赖 ddddocr（可选依赖，`pip install ddddocr`）；没装则直接跳过。
判定标准：
  - **错误提交数为 0** —— ocr_captcha 识别不出时必须返回空串（弃权），
    绝不能给出错误答案，否则会白白浪费一次验证码提交；
  - 识别率不低于 70%（实测约 80%，且弃权的样本会被换图重试）。
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from tools.tool import ocr_captcha          # noqa: E402

SAMPLES = os.path.join(HERE, 'captcha_samples')
MIN_ACCURACY = 0.70


def main() -> int:
    try:
        import ddddocr                        # noqa: F401
    except ImportError:
        print('未安装 ddddocr，跳过验证码识别测试（pip install ddddocr）')
        return 0

    with open(os.path.join(SAMPLES, 'labels.json'), encoding='utf-8') as f:
        labels = json.load(f)['samples']

    right = wrong = abstain = 0
    for name, item in sorted(labels.items()):
        path = os.path.join(SAMPLES, name)
        if not os.path.exists(path):
            print(f'  样本缺失: {name}')
            continue
        with open(path, 'rb') as f:
            got = ocr_captcha(f.read())
        want = item['answer']
        if not got:
            abstain += 1
            mark = '○ 弃权（换图重试）'
        elif got == want:
            right += 1
            mark = '✔'
        else:
            wrong += 1
            mark = '✘ 答案错'
        print(f'  {name:<20}{item["expr"]:<6}期望 {want:<5}得到 {got or "(空)":<6}{mark}')

    total = right + wrong + abstain
    print(f'\n识别正确 {right}/{total}  错误 {wrong}  弃权 {abstain}')
    print(f'有效识别率 {right / total * 100:.1f}%（阈值 {MIN_ACCURACY * 100:.0f}%）')

    if wrong:
        print('✘ 存在错误答案提交 —— ocr_captcha 必须在拿不准时返回空串')
        return 1
    if right / total < MIN_ACCURACY:
        print('✘ 识别率低于阈值')
        return 1
    print('✔ 通过')
    return 0


if __name__ == '__main__':
    sys.exit(main())
