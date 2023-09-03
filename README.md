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
  "auto_name": "false或者true #开启此功能有助于获取正确的文件名，但是会降低解析速度",
  "aria2_token": "如果使用idm下载，此项为空",
  "download_path": "下载目录",
  "proxies": "填写代理地址(http://127.0.0.1:7890)或者置空"
}
```

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
