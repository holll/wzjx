white_domain = [
    'rosefile',
    'koalaclouds',
    'koolaayun',
    'feimaoyun',
    'expfile',
    'xfpan',
    'skyfileos'
]
pan_domain = 'https://haoduopan.com'
domain_reg = r'(https?://[^/]+)'

# ---- 结果页选择器（2026-09 站点改版后实测）----
# 下载按钮精确 class，站点改版后 aria2-link 属性已移除，
# 直链改为放在 href="/master/download?l=<base64url>&en=<sig>" 里
download_btn_class = 'btn btn-info btn-sm'
end_time_class = 'badge badge-pill badge-secondary'  # 会员到期时间

# 错误/提示页文案容器，按优先级取第一个命中的：
#   1. alert-white my_container  —— 完整提示块，含标题（如"文件正在为您准备中"）
#   2. alert-secondary           —— 提示块正文
#   3. col-12 / col text-center  —— 兜底（注意 col-12 text-center 在提示页命中的是
#      "返回首页"页脚，本身没有文案，必须排在提示块之后，否则会取到空字符串）
error_msg_class_list = [
    'alert alert-white my_container',
    'alert alert-secondary',
    'col-12',
    'col-12 text-center',
    'col text-center',            # 旧版容器，保留兼容
]

# 中转路由 -> 线路展示名。
# 站点共 7 个线路 tab，但底层只有 2 个真实存储直链（阿里云 S3 + Cloudflare R2 备份），
# 各 tab 只是转发同一批预签名直链，因此按直链去重后可显著减少冗余。
route_label = {
    '/master/download': '专用线路',
    '/s3/download': '高速线路(S3)',
    '/download': '高速线路',
    '/direct/download': '迅雷',
    '/toAria2': 'Motrix',
    'ef2://': 'IDM',
    'ct://': '迅雷[新]',
}
