# wzjx
利用解析网站获取网赚盘下载地址并推送到aria2或IDM

解析网站：<http://disk.codest.me/>

卡密购买地址：<https://h5.m.taobao.com/awp/core/detail.htm?id=641655392460>

感谢@Eric Brown提供的调用IDM代码 [教程](https://stackoverflow.com/questions/22587681/use-idminternet-download-manager-api-with-python)

## 使用教程

1. 下载本项目
2. 将config.example.json重命名为config.json
3. 填写配置文件

## 配置文件解释

```json
{
  "card": "卡密",
  "aria2_rpc": "如果使用idm下载，此项为空",
  "aria2_token": "如果使用idm下载，此项为空",
  "download_path": "下载目录",
  "proxies": "填写代理地址(http://127.0.0.1:7890)或者置空"
}
```