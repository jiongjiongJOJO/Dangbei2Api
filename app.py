import re
import os
import uuid
import time
import json
import httpx
import uvicorn
import hashlib
import secrets
import logging
from version import VERSION
from pydantic import BaseModel
from dotenv import load_dotenv
from fake_useragent import UserAgent
from fastapi.security import APIKeyHeader
from typing import List, Literal, Optional
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Depends

# 加载 .env 文件
load_dotenv()

# 获取环境变量
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise ValueError("未在 .env 文件中找到 API_KEY")

ENABLE_CORS = os.getenv("ENABLE_CORS", "True").lower() in ("true", "1", "yes")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
MAX_CHARS = int(os.getenv("MAX_CHARS", "80000"))  # 从 .env 获取 MAX_CHARS，默认 80000
RANDOM_UA = os.getenv("RANDOM_UA", "False").lower() in ("true", "1", "yes")  # 是否随机UA，默认 False

# 设置日志（单行输出，中文）
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",  # noqa
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 设置 httpx 和 httpcore 的日志级别为 INFO，屏蔽 DEBUG 输出
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)

# 初始化 FastAPI 应用
app = FastAPI()

# 根据配置启用跨域
if ENABLE_CORS:
    app.add_middleware(
        CORSMiddleware,  # noqa
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("跨域支持已启用")
else:
    logger.info("跨域支持已禁用")

# 定义常量
api_domain = "https://ai-api.dangbei.net"
default_user_agent = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)
ua = UserAgent()  # 初始化 fake-useragent 的 UserAgent 对象

# 支持的模型和对应的 userAction 映射
supported_models = [
    "deepseek-r1", "deepseek-r1-search",  # deepseek-r1-671b
    "deepseek-v3", "deepseek-v3-search",  # deepseek-v3
    "doubao", "doubao-search",  # doubao-1.5-pro-32k # noqa
    "doubao-thinking", "doubao-thinking-search",  # doubao-1.5-thinking-pro
    "qwen-plus", "qwen-plus-search",  # qwen-plus-32k
    "qwq-plus", "qwq-plus-search",  # qwen-qwq-32k
    "qwen-long", "qwen-long-search",  # qwen-long
    "moonshot-v1-32k", "moonshot-v1-32k-search",  # kimi
    "ernie-4.5-turbo-32k", "ernie-4.5-turbo-32k-search"  # ernie-4.5-turbo-32k
]

model_to_user_action = {
    # deepseek-r1-671b
    "deepseek-r1": {'model': 'deepseek', 'user_action': ["deep"]},
    "deepseek-r1-search": {'model': 'deepseek', 'user_action': ["deep", "online"]},
    # deepseek-v3
    "deepseek-v3": {'model': 'deepseek', 'user_action': []},
    "deepseek-v3-search": {'model': 'deepseek', 'user_action': ["online"]},
    # doubao-1.5-pro-32k
    'doubao': {'model': 'doubao', 'user_action': []},  # noqa
    'doubao-search': {'model': 'doubao', 'user_action': ["online"]},  # noqa
    # doubao-1.5-thinking-pro
    'doubao-thinking': {'model': 'doubao-thinking', 'user_action': ['deep']},
    'doubao-thinking-search': {'model': 'doubao-thinking', 'user_action': ['deep', "online"]},
    # qwen
    'qwen': {'model': 'qwen', 'user_action': []},
    'qwen-search': {'model': 'qwen', 'user_action': ["online"]},
    # qwen-plus-32k
    'qwen-plus': {'model': 'qwen-plus', 'user_action': []},
    'qwen-plus-search': {'model': 'qwen-plus', 'user_action': ["online"]},
    # qwen-qwq-32k
    'qwq-plus': {'model': 'qwq-plus', 'user_action': ['deep']},
    'qwq-plus-search': {'model': 'qwq-plus', 'user_action': ['deep', 'search']},
    # qwen-long
    'qwen-long': {'model': 'qwen-long', 'user_action': []},
    'qwen-long-search': {'model': 'qwen-long', 'user_action': ["online"]},
    # kimi
    'moonshot-v1-32k': {'model': 'moonshot', 'user_action': []},
    'moonshot-v1-32k-search': {'model': 'moonshot', 'user_action': ["online"]},
    # ernie-4.5-turbo-32k
    'ernie-4.5-turbo-32k': {'model': 'ernie-4.5-turbo', 'user_action': []},
    'ernie-4.5-turbo-32k-search': {'model': 'ernie-4.5-turbo', 'user_action': ["online"]},
}

# 用于存储 device_id 对应的 User-Agent
device_ua_map = {}


# 工具函数
def nanoid(size=21):
    url_alphabet = "abcdefgh0ijkl1mno2pqrs3tuv4wxyz5ABCDEFGH6IJKL7MNO8PQRS9TUV-WXYZ_"
    return "".join(secrets.choice(url_alphabet) for _ in range(size))


def generate_device_id():
    return f"{uuid.uuid4().hex}_{nanoid(20)}"


def get_user_agent(device_id: str) -> str:
    """根据 device_id 返回 User-Agent，保证同一会话使用相同 UA"""
    if not RANDOM_UA:
        return default_user_agent
    if device_id not in device_ua_map:
        device_ua_map[device_id] = ua.random  # 为新 device_id 生成随机 UA
    return device_ua_map[device_id]


def generate_sign(timestamp: str, payload: dict, nonce: str) -> str:
    payload_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    sign_str = f"{timestamp}{payload_str}{nonce}"
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()


# 创建会话
async def create_conversation(device_id: str, model_name) -> str:
    payload = {
        "metaData": {
            "writeCode": "",
            "chatModelConfig": {
                "model": model_to_user_action[model_name]['model'],
                "options": model_to_user_action[model_name]['user_action'],
            }
        },
        "isAnonymous": False
    }
    timestamp = str(int(time.time()) - 20)
    nonce = nanoid(21)
    sign = generate_sign(timestamp, payload, nonce)
    headers = {
        "appType": "6",
        "client-ver": "1.0.1",
        "lang": "zh",
        "token": "",
        "Origin": "https://ai.dangbei.com",
        "Referer": "https://ai.dangbei.com/",
        "User-Agent": get_user_agent(device_id),
        "deviceId": device_id,
        "nonce": nonce,
        "sign": sign,
        "timestamp": timestamp,
        "content-type": "application/json",
    }
    api = f"{api_domain}/ai-search/conversationApi/v1/create"
    async with httpx.AsyncClient(http2=True) as client:
        response = await client.post(api, json=payload, headers=headers)
        if response.status_code != 200:
            logger.error(f"创建会话失败：HTTP {response.status_code}")
            raise HTTPException(status_code=500, detail="创建会话失败")
        data = response.json()
        if data.get("success"):
            conversation_id = data["data"]["conversationId"]
            logger.info(f"[创建新会话] conversation_id: {conversation_id}, UA: {headers['User-Agent']}")
            return conversation_id
        else:
            logger.error(f"创建会话失败：{data}")
            raise HTTPException(status_code=500, detail="创建会话失败")


# 定义授权校验依赖
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def check_authorization(authorization: str = Depends(api_key_header)):
    if not authorization:
        logger.error("缺少 Authorization 头部")
        raise HTTPException(status_code=401, detail="缺少 Authorization 头部")
    api_key = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    if api_key != API_KEY:
        logger.error(f"无效的 API 密钥：{api_key}")
        raise HTTPException(status_code=401, detail="无效的 API 密钥")
    return True


# 定义请求模型
class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    stream: Optional[bool] = False
    frequency_penalty: Optional[float] = 0
    presence_penalty: Optional[float] = 0
    temperature: Optional[float] = 1
    top_p: Optional[float] = 1


# 生成流式响应块
def generate_chunk(_id: str, created: int, model: str, delta: dict, finish_reason: Optional[str] = None):
    chunk = {
        "id": _id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]
    }
    return f"data: {json.dumps(chunk)}\n\n"


# 拼接 messages 数组为字符串
def concatenate_messages(messages: List[Message]) -> str:
    concatenated = []
    for msg in messages:
        content = re.sub(r"<think>.*?</think>", "", msg.content, flags=re.DOTALL).strip()
        if content:
            concatenated.append(f"{msg.role.capitalize()}: {content}")
    return "\n".join(concatenated)


# 处理 card 类型的内容（优化为表格展示）
def parse_card_content(content: str) -> str:
    try:
        card_data = json.loads(content)
        if card_data.get("cardType") == "DB-CARD-2":
            card_info = card_data.get("cardInfo", {})
            references = []
            for item in card_info.get("cardItems", []):
                if item.get("type") == "2002":  # 搜索来源
                    sources = json.loads(item.get("content", "[]"))
                    for source in sources:
                        id_index = source.get("idIndex", "")
                        name = source.get("name", "")
                        url = source.get("url", "")
                        site_name = source.get("siteName", "")
                        row = f"| {id_index} | [{name}]({url}) | {site_name} |"
                        references.append(row)
            if references:
                header = "\n\n| 序号 | 网站URL | 来源 |\n| ---- | ---- | ---- |"
                return header + "\n" + "\n".join(references)
            return "无法解析的新闻内容"
        return "不支持的 card 类型"
    except json.JSONDecodeError:
        logger.warning(f"无法解析 card 内容：{content}")
        return "无法解析的新闻内容"


# 按字符数截断 messages，保留上下文连贯性
def truncate_messages(messages: List[Message], max_chars: int = MAX_CHARS) -> List[Message]:
    total_chars = sum(len(msg.content) for msg in messages)
    if total_chars <= max_chars:
        return messages

    other_messages = [msg for msg in messages if msg.role not in ["user", "assistant"]]
    other_chars = sum(len(msg.content) for msg in other_messages)

    available_chars = max_chars - other_chars
    if available_chars <= 0:
        logger.warning("非 user/assistant 消息已超过字符限制，仅保留这些消息")
        return other_messages

    ua_messages = [msg for msg in messages if msg.role in ["user", "assistant"]]
    truncated_ua = []
    current_chars = 0

    for msg in reversed(ua_messages):
        msg_chars = len(msg.content)
        if current_chars + msg_chars <= available_chars:
            truncated_ua.insert(0, msg)
            current_chars += msg_chars
        else:
            break

    truncated_messages = other_messages + truncated_ua
    logger.info(
        f"截断上下文：原始字符数 {total_chars}，"
        f"截断后字符数 {sum(len(msg.content) for msg in truncated_messages)}，"
        f"消息数 {len(truncated_messages)}"
    )
    return truncated_messages


def prepare_request_payload(request: ChatCompletionRequest, device_id: str, conversation_id: str):
    truncated_messages = truncate_messages(request.messages)
    concatenated_message = concatenate_messages(truncated_messages)
    user_action = model_to_user_action.get(request.model, {}).get('user_action', [])
    model = model_to_user_action.get(request.model, {}).get("model", "deepseek")
    payload = {
        "role": "user",
        "stream": True,
        "botCode": "AI_SEARCH",
        "userAction": ",".join(user_action),
        "model": model,
        "conversationId": conversation_id,
        "question": concatenated_message,
        "anonymousKey": "",
        "chatOption": {
            "writeCode": None, "searchKnowledge": False
        },
        "files": [],
        "status": "local",
        "agentId": "",
    }
    timestamp = str(int(time.time()))
    nonce = nanoid(21)
    sign = generate_sign(timestamp, payload, nonce)
    headers = {
        "Origin": "https://ai.dangbei.com",
        "Referer": "https://ai.dangbei.com/",
        "User-Agent": get_user_agent(device_id),
        "deviceId": device_id,
        "nonce": nonce,
        "sign": sign,
        "timestamp": timestamp,
    }
    return payload, headers


# 流式响应函数
async def stream_response(request: ChatCompletionRequest, device_id: str, conversation_id: str):
    payload, headers = prepare_request_payload(request, device_id, conversation_id)
    api = f"{api_domain}/ai-search/chatApi/v1/chat"
    _id = f"chatcmpl-{uuid.uuid4().hex}"  # noqa
    created = int(time.time())
    logger.info(
        f"开始流式响应，会话ID: {conversation_id}，"
        f"UA：{headers['User-Agent']}，"
        f"请求: {json.dumps(payload, ensure_ascii=False)}"
    )
    yield generate_chunk(_id, created, request.model, {"role": "assistant"})
    thinking = False
    content_parts = []
    card_content = None
    is_r1_model = request.model in ["deepseek-r1", "deepseek-r1-search"]

    async with httpx.AsyncClient(http2=True) as client:
        async with client.stream("POST", api, json=payload, headers=headers, timeout=1200) as response:
            if response.status_code != 200:
                error_msg = f"错误：无法获取响应，状态码: {response.status_code}"
                logger.error(error_msg)
                yield generate_chunk(_id, created, request.model, {"content": error_msg}, "stop")
                return
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    json_str = line[5:]
                    try:
                        data = json.loads(json_str)
                        content = data.get("content") or ""
                        if content:
                            content = re.sub(r"<details>.*?</details>", "", content, flags=re.DOTALL)
                            if data.get("content_type") == "thinking":
                                if not thinking:
                                    thinking = True
                                    content_parts.append("<think>")
                                    yield generate_chunk(_id, created, request.model, {"content": "<think>"})
                                content_parts.append(content)
                                yield generate_chunk(_id, created, request.model, {"content": content})
                            elif data.get("content_type") == "text":
                                if thinking:
                                    thinking = False
                                    content_parts.append("</think>")
                                    yield generate_chunk(_id, created, request.model, {"content": "</think>"})
                                content_parts.append(content)
                                yield generate_chunk(_id, created, request.model, {"content": content})
                            elif data.get("content_type") == "card":
                                parsed_content = parse_card_content(content)
                                if is_r1_model:
                                    card_content = parsed_content
                                else:
                                    content_parts.append(parsed_content + "\n\n")
                                    yield generate_chunk(_id, created, request.model,
                                                         {"content": parsed_content + "\n\n"})
                    except json.JSONDecodeError:
                        logger.warning(f"无法解析 JSON 数据：{json_str}")
                        continue
            if thinking:
                content_parts.append("</think>")
                yield generate_chunk(_id, created, request.model, {"content": "</think>"})
            if is_r1_model and card_content:
                content_parts.append(card_content + "\n\n")
                yield generate_chunk(_id, created, request.model, {"content": card_content + "\n\n"})
            yield generate_chunk(_id, created, request.model, {}, "stop")
            content = "".join(content_parts)
            logger.info(f"流式响应完成，会话ID: {conversation_id}，内容: {json.dumps(content, ensure_ascii=False)}")


# 主端点
@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, _: None = Depends(check_authorization)):
    logger.info(f"接收到请求: {json.dumps(request.model_dump(), ensure_ascii=False)}")

    if request.model not in supported_models:
        request.model = "deepseek-v3"

    device_id = generate_device_id()
    print(f"device_id: {device_id}")
    conversation_id = await create_conversation(device_id, request.model)

    if request.stream:
        return StreamingResponse(stream_response(request, device_id, conversation_id), media_type="text/event-stream")

    payload, headers = prepare_request_payload(request, device_id, conversation_id)
    api = f"{api_domain}/ai-search/chatApi/v1/chat"
    content_parts = []
    card_content = None
    thinking = False
    is_r1_model = request.model in ["deepseek-r1", "deepseek-r1-search"]
    logger.info(
        f"开始非流式响应，会话ID: {conversation_id}，"
        f"UA: {headers['User-Agent']}，"
        f"请求: {json.dumps(payload, ensure_ascii=False)}"
    )
    async with httpx.AsyncClient(http2=True) as client:
        async with client.stream("POST", api, json=payload, headers=headers, timeout=1200) as response:
            if response.status_code != 200:
                error_msg = f"无法从 API 获取响应，状态码: {response.status_code}"
                logger.error(error_msg)
                raise HTTPException(status_code=500, detail=error_msg)
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    json_str = line[5:]
                    try:
                        data = json.loads(json_str)
                        content = data.get("content") or ""
                        if content:
                            content = re.sub(r"<details>.*?</details>", "", content, flags=re.DOTALL)
                            if data.get("content_type") == "thinking":
                                if not thinking:
                                    thinking = True
                                    content_parts.append("<think>")
                                content_parts.append(content)
                            elif data.get("content_type") == "text":
                                if thinking:
                                    thinking = False
                                    content_parts.append("</think>")
                                content_parts.append(content)
                            elif data.get("content_type") == "card":
                                parsed_content = parse_card_content(content)
                                if is_r1_model:
                                    card_content = parsed_content
                                else:
                                    content_parts.append(parsed_content + "\n\n")
                    except json.JSONDecodeError:
                        logger.warning(f"无法解析 JSON 数据：{json_str}")
                        continue
    if thinking:
        content_parts.append("</think>")
    if is_r1_model and card_content:
        content_parts.append(card_content + "\n\n")
    content = "".join(content_parts)

    response_data = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",  # noqa
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    logger.info(f"响应: {json.dumps(response_data, ensure_ascii=False)}")
    return response_data


# /models 端点
@app.get("/v1/models")
async def list_models(_: None = Depends(check_authorization)):
    logger.info("接收到 /models 请求")
    models = [
        {
            "id": model,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "dangbei"  # noqa
        } for model in supported_models
    ]
    response_data = {"object": "list", "data": models}
    logger.info(f"模型响应: {json.dumps(response_data, ensure_ascii=False)}")
    return response_data


if __name__ == "__main__":
    logger.info('当前程序版本为：{}'.format(VERSION))
    uvicorn.run(app, host="0.0.0.0", port=8000)
