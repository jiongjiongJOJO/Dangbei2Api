# DB DeepSeek转API脚本

这是一个将dangbei(下简称为DB)网页deepseek转为兼容OpenAI API的python脚本。

基于linux.do论坛 **@云胡不喜** 佬的脚本魔改。
原贴点击[传送门](https://linux.do/t/topic/444507) 。

感谢linux.do论坛 **@yxmiler** 佬提供的保持上下文的思路。
原贴点击[传送门](https://linux.do/t/topic/457926/15?u=jiongjiong_jojo) 。

## 支持模型

注：所有模型名称后方增加 `-search` 的模型均为同模型的支持联网搜索的版本。

| 模型名                        | 支持深度思考 | 支持联网搜索 | 描述                                     |
|----------------------------|--------|--------|----------------------------------------|
| deepseek-r1                | ✅      | ❌      | 671b满血版r1模型                            |
| deepseek-r1-search         | ✅      | ✅      | 包含联网搜索功能的671b满血r1模型                    |
| deepseek-v3                | ❌      | ❌      |                                        |
| deepseek-v3-search         | ❌      | ✅      |                                        |
| doubao                     | ❌      | ❌      | 该模型被DB增加了系统提示词，doubao-1.5-pro-32k      |
| doubao-search              | ❌      | ✅      |                                        |
| doubao-thinking            | ✅      | ❌      | 该模型被DB增加了系统提示词，doubao-1.5-thinking-pro |
| doubao-thinking-search     | ✅      | ✅      |                                        |
| qwen-plus                  | ❌      | ❌      | 该模型被DB增加了系统提示词，qwen-plus-32k           |
| qwen-plus-search           | ❌      | ✅      |                                        |
| qwen-long                  | ❌      | ❌      | 该模型被DB增加了系统提示词，qwen-long               |
| qwen-long-search           | ❌      | ✅      |                                        |
| qwq-plus                   | ✅      | ❌      | 该模型被DB增加了系统提示词，暂不清楚具体什么模型              |
| qwq-plus-search            | ✅      | ✅      |                                        |
| moonshot-v1-32k            | ❌      | ❌      | 该模型被DB增加了系统提示词，kimi moonshot-v1-32k    |
| moonshot-v1-32k-search     | ❌      | ✅      |                                        |
| ernie-4.5-turbo-32k        | ❌      | ❌      | 该模型被DB增加了系统提示词，文心 ernie-4.5-turbo-32k  |
| ernie-4.5-turbo-32k-search | ❌      | ✅      |                                        |

## 部署说明

**1.本地部署前修改 .env 文件，配置环境变量**

```plaintext
# API密钥配置（替换为自己的密钥）
API_KEY=sk-your-api-key

# 上下文最大字符数（可选，默认80000，我个人测下来，最高的一次98988字符，没有空响应）
MAX_CHARS=99999

# 是否启用跨域
ENABLE_CORS=True

# 日志级别（可选：DEBUG/INFO/WARNING/ERROR/CRITICAL）
LOG_LEVEL=DEBUG
```

**2.支持Docker部署，可直接使用 Docker 命令**

```bash
docker run -d -p 8000:8000 -e API_KEY=sk-DangBei666 -e MAX_CHARS=99999  -eENABLE_CORS=True -e LOG_LEVEL=INFO --name dangbei2api jiongjiong/dangbei2api:latest
```
