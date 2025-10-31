import os
import sys
import json
import time
import torch
import gc
from loguru import logger

# 添加项目根目录到 Python 路径
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.append(PROJECT_ROOT)

from sqlalchemy.orm import Session
from app.database import get_db_context
from app.utils.redis_client import redis_client
from app.models.file import File as FileModel
from app.models.enums import FileStatus
from app.services.parser import ParserService



def clean_memory():
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()
    gc.collect()

# 批处理文件数
WORK_BATCH = os.getenv("WORK_BATCH", 1)

# Redis Stream 配置
PARSER_STREAM = "file_parser_stream"
CONSUMER_GROUP = "parser_workers"
CONSUMER_NAME = f"worker_{os.getpid()}"

def process_task(task_data: dict, db: Session):
    """
    处理单个解析任务
    Args:
        task_data (dict): 任务数据，包含 file_id, user_id, parse_method
        db (Session): 数据库会话
    """
    try:
        file_id = task_data.get("file_id")
        user_id = task_data.get("user_id")
        parse_method = task_data.get("parse_method", "auto")

        if not file_id or not user_id:
            logger.error(f"Invalid task data: {task_data}")
            return

        # 获取文件记录
        file = db.query(FileModel).filter(FileModel.id == file_id).first()
        if not file:
            logger.error(f"File not found: {file_id}")
            return

        # 创建解析服务实例
        parser_service = ParserService(db)

        # 执行文件解析
        logger.info(f"Processing file {file_id} for user {user_id}")
        result = parser_service.parse_file(file, user_id, parse_method)
        logger.info(f"File {file_id} processed successfully: {result}")

    except Exception as e:
        logger.error(f"Error processing task {task_data}: {str(e)}")
        # 如果解析失败，更新文件状态
        if file:
            file.status = FileStatus.PARSE_FAILED
            db.commit()

def run_worker():
    """
    运行文件解析工作者
    """
    logger.info("Starting file parser worker...")

    try:
        # 确保消费者组存在
        redis_client.create_consumer_group(PARSER_STREAM, CONSUMER_GROUP)
    except Exception as e:
        logger.error(f"Failed to create consumer group: {e}")
        return

    try:
        while True:
            try:
                # 从 Stream 中读取新消息
                messages = redis_client.read_stream(
                    PARSER_STREAM,
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    count=WORK_BATCH,
                    block=1000  # 阻塞1秒等待新消息
                )
                if messages:
                    logger.info(f"Received {len(messages)} messages")
                    for stream_id, message in messages:
                        try:
                            # 解析任务数据
                            task_data = json.loads(message[b'data'].decode('utf-8'))
                            logger.info(f"Processing task: {task_data}")

                            # 使用上下文管理器处理数据库会话
                            with get_db_context() as db:
                                # 处理任务
                                process_task(task_data, db)

                            # 确认消息已处理
                            redis_client.ack_message(PARSER_STREAM, CONSUMER_GROUP, stream_id)
                            logger.info(f"Task {stream_id} processed and acknowledged")

                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to decode task data: {e}")
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")

            except Exception as e:
                logger.error(f"Error reading from stream: {e}")
                time.sleep(1)  # 发生错误时等待1秒再重试

    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker error: {e}")
    finally:
        # 清理资源
        logger.info("清理资源。。。")
        clean_memory()

if __name__ == "__main__":
    run_worker() 