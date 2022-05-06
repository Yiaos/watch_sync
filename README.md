# watch & sync
### 监控本地路径并同步改文件下的修改到指定位置（本地、远程）
note: 不适用于单个文件较大场景

### 使用
```
server:
python3 server_sync.py

client:
python3 client_watch.py 
python3 client_watch.py -d /sync_dir1 /path/to/sync_dir2

setting:
1. 指定服务端口，简单的认证

2. 设置同步配置：
sync_conf:
key: 本地路径

switch: 监控开关
match: 监控文件的匹配正则
ignore: 忽略文件的匹配正则，优先级高于match
hiddle: 是否监控隐藏文件
```

#### client
watchdog监控本地文件修改，通过http同步至服务端
> https://github.com/gorakhargosh/watchdog

#### server
基于SimpleHTTPRequestHandler实现
带有基础download upload的http server IP:port 可以在网页浏览下载当前目录下的文件、上传文件
通过post请求上传并同步文件
> 参考见server.py中__author__