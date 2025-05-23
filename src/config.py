import os
import json
from logger import thread_safe_logging

DEFAULT_CONFIG = {
    "screenshot_interval": 20,  # 截屏间隔（秒）修改为20秒
    "save_path": "screenshots",  # 使用相对路径
    "record_user_actions": True,  # 是否记录用户操作
    "user_actions_log": os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log', 'user_actions.log'),  # 用户操作日志文件路径
        # 新增配置项开始
    "encryption": {
        "key": "16byteslongkey!!",  # AES加密密钥（16字节）
        "iv": "16byteslongiv!!!"    # AES初始化向量（16字节）
    },
    "modelscope": {
        "access_token": "45e3bad7-e2bc-45b6-b7be-44dda62adca6",
        "owner_name": "lllijuih",
        "dataset_name": "AGENTC",
        "commit_message": "upload dataset folder to repo",
        "repo_type": "dataset",
        "path_in_repo": "test"
    }
    # 新增配置项结束
}

class Config:
    @staticmethod
    def load_config(config_file='config.json'):
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config_file)
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                thread_safe_logging('info', "配置文件已加载。")
                return config
            except Exception as e:
                thread_safe_logging('error', f"加载配置文件失败: {e}")
                return DEFAULT_CONFIG
        else:
            Config.save_config(DEFAULT_CONFIG, config_path)
            thread_safe_logging('info', "默认配置已创建。")
            return DEFAULT_CONFIG

    @staticmethod
    def save_config(config, config_file='config.json'):
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config_file)
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
            thread_safe_logging('info', "配置文件已保存。")
        except Exception as e:
            thread_safe_logging('error', f"保存配置文件失败: {e}")