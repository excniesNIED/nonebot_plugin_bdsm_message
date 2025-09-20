import asyncio
import configparser
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict

from nonebot import get_driver, on_message, require
from nonebot.adapters.onebot.v11 import (
    Bot,

    Event,
    Message,
    MessageEvent,
    GroupMessageEvent,
    MessageSegment,
)
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule, to_me
from nonebot.typing import T_State

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

__plugin_meta__ = PluginMetadata(
    name="BDSM Message Manager",
    description="A powerful message management plugin for NoneBot2.",
    usage="""
    [命令类型][时间戳][消息内容][目标群号]
    """,
    type="application",
    homepage="https://github.com/example/nonebot-plugin-bdsm-message",
    config=None,
    supported_adapters={"onebot.v11"},
)

# --- Path Configuration ---
# Using Path() for cross-platform compatibility.
# "data" is a common directory for plugins to store their data.
CONFIG_PATH = Path("data") / "bdsmm"
CONFIG_FILE = CONFIG_PATH / "bdsmm_config.ini"
QUEUE_FILE = CONFIG_PATH / "bdsmm_queue.json"
LOG_FILE = CONFIG_PATH / "bdsmm.log"

# --- Initial Setup ---
# Ensure the plugin's data directory exists.
CONFIG_PATH.mkdir(parents=True, exist_ok=True)
if not QUEUE_FILE.is_file():
    with open(QUEUE_FILE, "w") as file:
        json.dump({}, file)

# --- Logger Configuration ---
# Sets up a dedicated logger for this plugin to separate its logs
# from NoneBot's main log, making debugging easier.
log_formatter = logging.Formatter(
    "[%(asctime)s] [%(name)s] [%(levelname)s] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setFormatter(log_formatter)
bdsm_logger = logging.getLogger("bdsmm")
bdsm_logger.addHandler(file_handler)
bdsm_logger.setLevel(logging.INFO)

# --- Configuration Class ---
class Config:
    """
    Handles loading and parsing of the plugin's configuration from bdsmm_config.ini.
    """
    def __init__(self):
        self.admin_groups: List[int] = []
        self.receiver_groups: List[int] = []
        self.admins: List[int] = []
        self._load_config()

    def _load_config(self):
        if not CONFIG_FILE.exists():
            # Create default config file
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(
                    "[bdsmm_Groups]\n"
                    "admin_groups=\n"
                    "receiver_groups=\n\n"
                    "[bdsmm_Admins]\n"
                    "admin=\n"
                )
            logger.info(f"Created default config file at {CONFIG_FILE}")
            return

        config = configparser.ConfigParser()
        config.read(CONFIG_FILE, encoding="utf-8")

        # Safely parse comma-separated lists of group and admin IDs.
        if "bdsmm_Groups" in config:
            admin_groups_str = config["bdsmm_Groups"].get("admin_groups", "")
            self.admin_groups = (
                [int(g.strip()) for g in admin_groups_str.split(",") if g.strip()]
                if admin_groups_str
                else []
            )
            receiver_groups_str = config["bdsmm_Groups"].get("receiver_groups", "")
            self.receiver_groups = (
                [int(g.strip()) for g in receiver_groups_str.split(",") if g.strip()]
                if receiver_groups_str
                else []
            )

        if "bdsmm_Admins" in config:
            admins_str = config["bdsmm_Admins"].get("admin", "")
            self.admins = (
                [int(a.strip()) for a in admins_str.split(",") if a.strip()]
                if admins_str
                else []
            )

        # Log the loaded configuration for verification.
        bdsm_logger.info(
            f"Config loaded. Admin groups: {self.admin_groups}, Receiver groups: {self.receiver_groups}, Admins: {self.admins}"
        )


# Instantiate the configuration.
config = Config()

driver = get_driver()

# --- Startup and Shutdown ---
@driver.on_startup
async def on_startup():
    """
    Loads any tasks from the queue that were scheduled before a bot restart.
    """
    if QUEUE_FILE.exists():
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            try:
                queue = json.load(f)
                if not isinstance(queue, dict):
                    bdsm_logger.warning(
                        f"{QUEUE_FILE} does not contain a valid dictionary. Re-initializing."
                    )
                    queue = {}

                for job_id, job_info in queue.items():
                    timestamp = datetime.fromisoformat(job_info["timestamp"])
                    if timestamp > datetime.now():
                        scheduler.add_job(
                            execute_scheduled_task,
                            "date",
                            run_date=timestamp,
                            id=job_id,
                            args=[
                                job_info["type"],
                                job_info["content"],
                                job_info["target_group"],
                                job_id,
                            ],
                        )
                        bdsm_logger.info(f"Loaded scheduled job {job_id}")
            except json.JSONDecodeError:
                bdsm_logger.error(f"Failed to decode {QUEUE_FILE}. Starting with an empty queue.")

# --- Scheduled Task Execution ---
async def execute_scheduled_task(
    command_type: str, content: str, target_group: int, job_id: str
):
    """
    This function is the entry point for all tasks executed by the scheduler.
    It retrieves a bot instance and executes the corresponding command.
    """
    bots = get_driver().bots
    if not bots:
        bdsm_logger.error("No bot instance available to execute scheduled task.")
        return

    bot = list(bots.values())[0]  # Get the first available bot instance.

    try:
        message_to_send = None
        if command_type == "sendmessage":
            message_to_send = parse_content_to_message(content)
        elif command_type == "forwardmessage":
            message_to_send = Message(content)

        if message_to_send:
            msg_info = await bot.send_group_msg(
                group_id=target_group, message=message_to_send
            )
            message_id = msg_info["message_id"]

            bdsm_logger.info(
                f"Executed scheduled job {job_id}: Sent message to group {target_group}. MessageID: {message_id}"
            )

            # Send confirmation to admin groups
            confirmation_message = f"Scheduled message sent to group {target_group}.\nMessageID: {message_id}"
            for admin_group in config.admin_groups:
                try:
                    await bot.send_group_msg(
                        group_id=admin_group, message=confirmation_message
                    )
                except Exception as e:
                    bdsm_logger.error(
                        f"Failed to send confirmation to admin group {admin_group}: {e}"
                    )

        # Once the task is done, remove it from the persistent queue.
        remove_from_queue(job_id)
    except Exception as e:
        bdsm_logger.error(f"Failed to execute scheduled job {job_id}: {e}")

# --- Queue Management ---
def save_to_queue(job_id: str, task_info: Dict):
    """
    Adds or updates a task in the bdsmm_queue.json file.
    This ensures that scheduled tasks persist across bot restarts.
    """
    queue = {}
    if QUEUE_FILE.exists():
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            try:
                queue = json.load(f)
                if not isinstance(queue, dict):
                    queue = {}
            except json.JSONDecodeError:
                pass  # Start with an empty queue if file is corrupt
    queue[job_id] = task_info
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=4, ensure_ascii=False)


def remove_from_queue(job_id: str):
    """
    Removes a task from the bdsmm_queue.json file, typically after it has been
    executed or canceled.
    """
    if not QUEUE_FILE.exists():
        return
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        try:
            queue = json.load(f)
            if not isinstance(queue, dict):
                return # Can't remove from a non-dictionary
        except json.JSONDecodeError:
            return  # Nothing to remove
    if job_id in queue:
        del queue[job_id]
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=4, ensure_ascii=False)


def parse_content_to_message(content: str) -> Message:
    """
    Parses a string with custom syntax into a NoneBot Message object.
    - Handles {at_all} for "at all" segment.
    - Handles \\n for newlines.
    - Parses {:Image(url="...")} into image segments.
    """
    content = content.replace("\\n", "\n")

    # Regex to split the string by our custom tags, but keep the tags
    tag_regex = r"(\{at_all\}|\{\:Image\(url=\".*?\"\)\})"
    parts = re.split(tag_regex, content)

    message = Message()
    image_url_regex = r"\{\:Image\(url=\"(.*?)\"\)\}"

    for part in parts:
        if not part:  # re.split can produce empty strings
            continue
        
        if part == "{at_all}":
            message += MessageSegment.at("all")
        elif re.match(image_url_regex, part):
            match = re.search(image_url_regex, part)
            if match:
                url = match.group(1)
                message += MessageSegment.image(file=url)
        else:
            message += MessageSegment.text(part)
            
    return message

# --- Permission Check ---
def is_admin(user_id: int) -> bool:
    """
    Checks if a user is authorized to issue commands. If the admin list in the
    config is empty, all users in admin groups are considered admins.
    """
    if not config.admins:
        return True
    return user_id in config.admins


def is_bdsm_command() -> Rule:
    async def _is_bdsm_command(event: MessageEvent, state: T_State) -> bool:
        msg = event.get_plaintext().strip()
        if re.match(r"\[(.*?)\]\[(.*?)\]\[(.*?)\]\[(.*?)\]", msg, re.DOTALL):
            return True
        if msg.lower() == 'message':
            return True
        return False
    return Rule(_is_bdsm_command)


# --- Main Message Handler ---
message_handler = on_message(rule=to_me() & is_bdsm_command(), priority=10, block=True)


@message_handler.handle()
async def handle_message(bot: Bot, event: GroupMessageEvent):
    """
    This is the primary handler for all incoming commands. It performs
    permission checks, parses the command, and delegates to the appropriate
    function for execution.
    """
    # Only process messages from configured admin groups.
    if event.group_id not in config.admin_groups:
        return

    # Check if the user has admin privileges.
    if not is_admin(event.user_id):
        await message_handler.finish("You are not authorized to use this command.")
        return

    command_text = event.get_plaintext().strip()
    
    # Provide a simple help message if the user just pings the bot with "message".
    if command_text.lower() == 'message':
        await message_handler.finish(
            "BDSM Message Manager - 可用命令:\n"
            "基本格式: [命令类型][时间戳][消息内容][目标群号]\n\n"
            "1. sendmessage: 发送消息\n"
            "   - 时间戳: 0 (立即发送) 或 YYYYMMDDHHMM(SS) (定时发送)\n"
            "   - 消息内容: 支持纯文本, {at_all}, \\n (换行), 和 `{:Image(url=\"...\")}` 图片格式.\n"
            "   - 示例: `[sendmessage][202509201200][大家好][123456]`\n\n"
            "2. forwardmessage: 转发消息 (需回复一条消息)\n"
            "   - 时间戳: 0 (立即发送) 或 YYYYMMDDHHMM(SS) (定时发送)\n"
            "   - 消息内容: 留空\n"
            "   - 示例: `[forwardmessage][0][][123456]` (回复某条消息时使用)\n\n"
            "3. recallmessage: 撤回消息\n"
            "   - 时间戳: 0\n"
            "   - 消息内容: 要撤回的消息ID (MessageID).\n"
            "   - 目标群号: 消息所在的群号 (虽然格式上需要, 但实际未使用).\n"
            "   - 也可以通过回复要撤回的消息来使用, 消息内容和群号任意.\n"
            "   - 示例: `[recallmessage][0][12345][654321]`\n\n"
            "4. cancelmessage: 取消定时任务\n"
            "   - 时间戳: -1\n"
            "   - 消息内容: 要取消的任务ID (JobID).\n"
            "   - 示例: `[cancelmessage][-1][job_...][0]`\n\n"
            "5. schedulemessage: 查看定时任务列表\n"
            "   - 时间戳/消息内容/目标群号: 可选的筛选条件.\n"
            "   - 示例: `[schedulemessage][][][123456]` (查看所有发往群123456的任务)\n"
        )
        return

    # Use regex to parse the command string.
    match = re.match(r"\[(.*?)\]\[(.*?)\]\[(.*?)\]\[(.*?)\]", command_text, re.DOTALL)
    if not match:
        # Silently ignore messages that don't match the command format.
        return

    command_type, timestamp_str, content, target_group_str = (g.strip() for g in match.groups())

    # Validate the target group ID.
    if not target_group_str.isdigit() and command_type != "schedulemessage":
        await message_handler.finish("Invalid target group number.")
        return
        
    target_group = int(target_group_str) if target_group_str.isdigit() else 0

    if target_group and target_group not in config.receiver_groups:
        await message_handler.finish(f"Group {target_group} is not in the receiver groups list.")
        return
        
    bdsm_logger.info(
        f"Received command from user {event.user_id} in group {event.group_id}: "
        f"[{command_type}][{timestamp_str}][...][{target_group_str}]"
    )

    # --- Command Delegation ---
    # Based on the command_type, the appropriate logic is executed.
    
    if command_type == "sendmessage":
        if timestamp_str == "0":  # Immediate send
            try:
                msg_info = await bot.send_group_msg(
                    group_id=target_group, message=parse_content_to_message(content)
                )
                await message_handler.send(
                    f"Message sent to group {target_group}. MessageID: {msg_info['message_id']}"
                )
                bdsm_logger.info(f"Sent message to group {target_group}.")
            except Exception as e:
                await message_handler.send(f"Failed to send message: {e}")
                bdsm_logger.error(f"Failed to send message to group {target_group}: {e}")
        elif timestamp_str.isdigit():  # Scheduled send
            try:
                if len(timestamp_str) == 14:
                    send_time = datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
                elif len(timestamp_str) == 12:
                    send_time = datetime.strptime(timestamp_str, "%Y%m%d%H%M")
                else:
                    raise ValueError("Incorrect timestamp length")

                job_id = f"job_{send_time.timestamp()}_{target_group}"
                scheduler.add_job(
                    execute_scheduled_task,
                    "date",
                    run_date=send_time,
                    id=job_id,
                    args=["sendmessage", content, target_group, job_id],
                )
                save_to_queue(
                    job_id,
                    {
                        "timestamp": send_time.isoformat(),
                        "type": "sendmessage",
                        "content": content,
                        "target_group": target_group,
                    },
                )
                await message_handler.send(
                    f"Message scheduled for {send_time.strftime('%Y-%m-%d %H:%M:%S')} to group {target_group}."
                    f" JobID: {job_id}"
                )
                bdsm_logger.info(f"Scheduled message for group {target_group} at {send_time}.")
            except ValueError:
                await message_handler.send("Invalid timestamp format. Please use YYYYMMDDHHMMSS or YYYYMMDDHHMM.")
            except Exception as e:
                await message_handler.send(f"Failed to schedule message: {e}")
                bdsm_logger.error(f"Failed to schedule message for group {target_group}: {e}")
                
    elif command_type == "forwardmessage":
        if not event.reply:
            await message_handler.finish("The `forwardmessage` command must be used by replying to a message.")
            return

        forward_message = event.reply.message
        if timestamp_str == "0":
            try:
                msg_info = await bot.send_group_msg(group_id=target_group, message=forward_message)
                await message_handler.send(
                    f"Message forwarded to group {target_group}. MessageID: {msg_info['message_id']}"
                )
                bdsm_logger.info(f"Forwarded message to group {target_group}.")
            except Exception as e:
                await message_handler.send(f"Failed to forward message: {e}")
                bdsm_logger.error(f"Failed to forward message to group {target_group}: {e}")
        elif timestamp_str.isdigit():
            try:
                if len(timestamp_str) == 14:
                    send_time = datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
                elif len(timestamp_str) == 12:
                    send_time = datetime.strptime(timestamp_str, "%Y%m%d%H%M")
                else:
                    raise ValueError("Incorrect timestamp length")

                job_id = f"job_forward_{send_time.timestamp()}_{target_group}"
                scheduler.add_job(
                    execute_scheduled_task,
                    "date",
                    run_date=send_time,
                    id=job_id,
                    args=["forwardmessage", str(forward_message), target_group, job_id],
                )
                save_to_queue(
                    job_id,
                    {
                        "timestamp": send_time.isoformat(),
                        "type": "forwardmessage",
                        "content": str(forward_message),
                        "target_group": target_group,
                    },
                )
                await message_handler.send(
                    f"Forward message scheduled for {send_time.strftime('%Y-%m-%d %H:%M:%S')} to group {target_group}."
                    f" JobID: {job_id}"
                )
                bdsm_logger.info(f"Scheduled forward for group {target_group} at {send_time}.")
            except ValueError:
                await message_handler.send("Invalid timestamp format. Please use YYYYMMDDHHMMSS or YYYYMMDDHHMM.")
            except Exception as e:
                await message_handler.send(f"Failed to schedule forward: {e}")
                bdsm_logger.error(f"Failed to schedule forward for group {target_group}: {e}")
                
    elif command_type == "recallmessage":
        # Prioritize recalling the message from the reply.
        if event.reply:
            try:
                recalled_msg_id = event.reply.message_id
                await bot.delete_msg(message_id=recalled_msg_id)
                await message_handler.send(f"Message {recalled_msg_id} has been recalled.")
                bdsm_logger.info(f"Recalled message {recalled_msg_id}.")
                return
            except Exception as e:
                # Log the error but continue to allow fallback.
                bdsm_logger.error(f"Could not recall from reply: {e}")
        
        # Fallback to using message_id from the content field.
        if not content.isdigit():
             await message_handler.finish("Invalid MessageID. Provide a numeric MessageID or reply to the message to recall.")
             return
        message_id = int(content)

        try:
            await bot.delete_msg(message_id=message_id)
            await message_handler.send(f"Message {message_id} has been recalled.")
            bdsm_logger.info(f"Recalled message {message_id} from group {target_group}.")
        except Exception as e:
            await message_handler.send(f"Failed to recall message: {e}")
            bdsm_logger.error(f"Failed to recall message {message_id}: {e}")

    elif command_type == "schedulemessage":
        if not QUEUE_FILE.exists():
            await message_handler.send("The schedule queue is empty.")
            return

        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            try:
                queue = json.load(f)
            except json.JSONDecodeError:
                await message_handler.send("Could not read the schedule queue.")
                return

        if not queue:
            await message_handler.send("The schedule queue is empty.")
            return

        # Filtering logic for viewing the schedule.
        filtered_tasks = queue.copy()
        
        # Filter by timestamp.
        if timestamp_str:
            try:
                filter_time = None
                if len(timestamp_str) == 14:
                    filter_time = datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
                elif len(timestamp_str) == 12:
                    filter_time = datetime.strptime(timestamp_str, "%Y%m%d%H%M")

                if filter_time:
                    filtered_tasks = {
                        job_id: info
                        for job_id, info in filtered_tasks.items()
                        if datetime.fromisoformat(info["timestamp"]) == filter_time
                    }
            except ValueError:
                pass # Ignore invalid time formats during filtering.

        # Filter by content using regular expressions.
        if content:
            try:
                regex = re.compile(content)
                filtered_tasks = {
                    job_id: info
                    for job_id, info in filtered_tasks.items()
                    if regex.search(info["content"])
                }
            except re.error:
                await message_handler.send("Invalid regular expression for content filtering.")
                return
        
        # Filter by target group.
        if target_group_str and target_group_str.isdigit():
            filter_group = int(target_group_str)
            filtered_tasks = {
                job_id: info
                for job_id, info in filtered_tasks.items()
                if info["target_group"] == filter_group
            }

        if not filtered_tasks:
            await message_handler.send("No scheduled tasks match your criteria.")
            return

        # Format and send the list of scheduled tasks.
        response = "Scheduled Tasks:\n"
        for job_id, job_info in filtered_tasks.items():
            response += (
                f"  - JobID: {job_id}\n"
                f"    Time: {datetime.fromisoformat(job_info['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"    Group: {job_info['target_group']}\n"
                f"    Content: `{job_info['content'][:30].replace('`', '')}...`\n"
            )
        await message_handler.send(response)
    
    elif command_type == "cancelmessage":
        if timestamp_str != "-1":
             await message_handler.finish("To cancel a task, the timestamp must be -1.")
             return
             
        job_id_to_cancel = content
        try:
            scheduler.remove_job(job_id_to_cancel)
            remove_from_queue(job_id_to_cancel)
            await message_handler.send(f"Scheduled job {job_id_to_cancel} has been canceled.")
            bdsm_logger.info(f"Canceled scheduled job {job_id_to_cancel}.")
        except Exception as e:
            await message_handler.send(f"Failed to cancel job {job_id_to_cancel}: {e}")
            bdsm_logger.error(f"Failed to cancel job {job_id_to_cancel}: {e}")
