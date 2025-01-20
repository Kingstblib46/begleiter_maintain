# logger.py

import logging
import threading
import os
from frozen_dir import app_path

logger = logging.getLogger("ScreenshotApp")
logger_lock = threading.Lock()
global_log_dir = ""

def setup_logging():
    """
    配置日志记录器，确保日志文件保存到正确路径。
    """
    global global_log_dir
    if not logger.handlers:  # 防止重复添加日志处理器
        logger.setLevel(logging.INFO)

        # 动态获取日志目录
        base_path = app_path()
        log_dir = os.path.join(base_path, "log")
        global_log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        handler = logging.FileHandler(os.path.join(log_dir, "app.log"), encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

def thread_safe_logging(level, message):
    with logger_lock:
        if level == 'debug':
            logger.debug(message)
        elif level == 'info':
            logger.info(message)
        elif level == 'warning':
            logger.warning(message)
        elif level == 'error':
            logger.error(message)
        elif level == 'critical':
            logger.critical(message)

# 初始化日志
setup_logging()
