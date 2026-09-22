# 网赚盘解析真实下载地址

利用解析网站获取网赚盘下载地址并推送到aria2或IDM

| 支持网盘  |        |         |
|-------|--------|---------|
| 飞猫云√  | 567√   | 库云√     |
| EXP√  | 茉香     | 火箭云     |
| 雪球云盘√ | 先锋云√   | DUFILE√ |
| 星耀云盘√ | 贵族√    | Rose√   |
| 520   | 46     | 77      |
| RAR√  | OWN√   | 蜜蜂      |
| 飞鱼盘√  | YIFILE | 台湾云     |
| SKY√  |        |         |

**网站名称后面有√的表示支持自动解析文件名**

_想要添加自动解析功能，请提交issue，标题写网盘名称，内容附上网盘文件的分享链接_

解析网站：<http://disk.codest.me/>

卡密购买地址：<https://h5.m.taobao.com/awp/core/detail.htm?id=641655392460>

感谢@Eric
Brown提供的调用IDM代码 [教程](https://stackoverflow.com/questions/22587681/use-idminternet-download-manager-api-with-python)

## 使用教程

1. 下载本项目
2. 将config.example.json重命名为config.json
3. 填写配置文件 [教程](#jump1)
4. 安装依赖 [教程](#jump2)

## 配置文件解释<a id="jump1"></a>

```json
{
  "card": "卡密",
  "aria2_rpc": "如果使用idm下载，此项为空",
  "aria2_token": "如果使用idm下载，此项为空",
  "auto_name": "false或者true #开启此功能有助于获取正确的文件名，但是会降低解析速度",
  "auto_select": "false或者true #开启后自动选第一条线路(专用线路)，不再交互式询问",
  "download_path": "下载目录",
  "xc": "置为 true 时只输出续传码 XC://xxx，不推送下载器",
  "cookies": "可选。解析站前置阿里云WAF，被拦截时可粘贴浏览器的 acw_sc__v2=xxx; fingerprint=xxx"
}
```

## API 返回结构（server 模式）<a id="jump3"></a>

启动：`python index.py -server`，`POST /api/parse`，请求体 `{"url": "网盘分享链接"}`。

```json
{
  "code": 200,
  "msg": "",
  "cache": "miss",
  "raw_url": "分享链接",
  "end_time": "27/03/02 到期",
  "expire_at": 1790066911,
  "links": ["https://... 去重后的真实直链"],
  "lines": [
    {
      "label": "👑 专用线路",
      "route": "/direct/download",
      "url": "https://... 与 links 中的元素对应",
      "en": "",
      "btn": "主力线路1",
      "expire_at": 1790066911
    }
  ]
}
```

- `code`：`200` 成功；`400` 站点提示（次数用尽、文件准备中等，原因见 `msg`）；`403` 需要人机验证；`500` 解析异常
- `cache`：`hit` 表示命中解析缓存（缓存时长与直链有效期对齐，最长 2 小时）
- `expire_at`：直链失效时间（UNIX 秒），读不出时为 `null`

关于 `expire_at`：站点直链有 4 种形态，**只有 S3/R2 预签名形态能读出精确失效时间**
（URL 里带 `X-Amz-Date` + `X-Amz-Expires`，实测有效期 2 小时）；站点代理链接
（walker / s20）的参数是服务端签名或加密、源站裸链无签名，都读不出。顶层的
`expire_at` 取本批已知值里**最晚**的一个，各线路的精确值看 `lines[].expire_at`。

选线路时会自动跳过**已过期**与**明确不可用**（域名解析失败 / 服务端 4xx-5xx）的直链；
探活结论不明的（如本机证书缺失导致的 SSL 失败）会保留而不是删掉。

注意：这个过滤只发生在**选用线路**时（交互选择 / `auto_select`）。API 返回的 `links`
保持原样不做探活（避免给每次请求增加额外网络往返），调用方可以按 `expire_at` 自行判断。

## 依赖安装教程<a id="jump2"></a>

执行`pip3 install -r requirements.txt`

或者依次执行

```commandline
pip3 install packages/beautifulsoup4-4.11.1-py3-none-any.whl
pip3 install packages/comtypes-1.1.11-py2.py3-none-any.whl
pip3 install packages/requests-2.28.1-py3-none-any.whl
```

## 注意事项

* 不保证代码长期有效
* 解析网站和淘宝店铺与本人无关，不保证长期有效
* 综上，卡密购买时长请慎重考虑


## 贡献者们

> 感谢所有让这个项目变得更好的贡献者们！

[![Star History Chart](https://contrib.rocks/image?repo=holll/wzjx)](https://github.com/holll/wzjx/graphs/contributors)

## Star历史

<a href="https://github.com/holll/wzjx/stargazers">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=holll/wzjx&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=holll/wzjx&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=holll/wzjx&type=Date" />
  </picture>
</a>
