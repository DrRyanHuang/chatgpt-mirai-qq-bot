from revChatGPT.revChatGPT import AsyncChatbot, generate_uuid
from charset_normalizer import from_bytes
from typing import Awaitable, Any, Dict, Tuple
from config import Config
from loguru import logger
import json
import os, sys
import asyncio

with open("config.json", "rb") as f:
    guessed_json = from_bytes(f.read()).best()
    if not guessed_json:
        raise ValueError("无法识别 JSON 格式!")
    
    config = Config.parse_obj(json.loads(str(guessed_json)))
# Refer to https://github.com/acheong08/ChatGPT
try:
    logger.info("登录 OpenAI 中……")
    logger.info("请在新打开的浏览器窗口中完成验证")
    if 'XPRA_PASSWORD' in os.environ:
        logger.info("如果您使用 xpra，请使用自己的浏览器访问 xpra 程序的端口，以访问到本程序启动的浏览器。")
    
    bot = AsyncChatbot(config=config.openai.dict(exclude_none=True, by_alias=False), conversation_id=None, base_url=config.openai.base_url)
    if not "cf_clearance" in bot.config:
        asyncio.run(bot.refresh_session())
    logger.info("登录成功，保存登录信息中……")

    if config.system.auto_save_cf_clearance:
        config.openai.cf_clearance = bot.config["cf_clearance"]
        config.openai.user_agent = bot.config["user_agent"]

    if config.system.auto_save_session_token:
        config.openai.session_token = bot.config["session_token"]
    
    logger.debug(f"获取到 cf_clearance {bot.config['cf_clearance']}")
    logger.debug(f"获取到 session_token {bot.config['session_token']}")
except Exception as e:
    logger.exception(e)
    logger.error("OpenAI 登录失败，可能是 session_token 过期或无法通过 CloudFlare 验证，建议歇息一下再重试。")
    exit(-1)

if config.system.auto_save_cf_clearance or config.system.auto_save_session_token:
    with open("config.json", "wb") as f:
        try:
            logger.debug(f"配置文件编码 {guessed_json.encoding} {config.response.timeout_format}")
            parsed_json = json.dumps(config.dict(), ensure_ascii=False, indent=4).encode(sys.getdefaultencoding())
            f.write(parsed_json)
        except Exception as e:
            logger.exception(e)
            logger.warning("配置保存失败")

class ChatSession:
    def __init__(self):
        self.reset_conversation()
    def reset_conversation(self):
        self.conversation_id = None
        self.parent_id = generate_uuid()
        self.prev_conversation_id = []
        self.prev_parent_id = []
    def rollback_conversation(self) -> bool:
        if len(self.prev_parent_id) <= 0:
            return False
        self.conversation_id = self.prev_conversation_id.pop()
        self.parent_id = self.prev_parent_id.pop()
        return True
    async def get_chat_response(self, message) -> Tuple[Dict[str, Any], Exception]:
        self.prev_conversation_id.append(self.conversation_id)
        self.prev_parent_id.append(self.parent_id)
        bot.conversation_id = self.conversation_id
        bot.parent_id = self.parent_id
        final_resp = None
        exception = None
        try:
            async for resp in await bot.get_chat_response(message, output="stream"):
                if final_resp is None:
                    logger.debug("已收到回应，正在接收中……")
                self.conversation_id = resp["conversation_id"]
                self.parent_id = resp["parent_id"]
                final_resp = resp
        except Exception as e:
            exception = e
        return final_resp, exception
sessions = {}


def get_chat_session(id: str) -> ChatSession:
    if id not in sessions:
        sessions[id] = ChatSession()
    return sessions[id]
