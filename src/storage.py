# storage.py

import os
import sys
import zipfile
from datetime import datetime
from logger import thread_safe_logging
import pyautogui
from PIL import Image, ImageDraw, ImageFont
import math
import platform
import string  # 引入 string 模块用于字符过滤
from frozen_dir import app_path
from PIL import Image as PILImage
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from modelscope.hub.api import HubApi
import json

def resource_path(relative_path):
    if getattr(sys, 'frozen', False):      # 是否Bundle Resource
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def compress_image(input_path, output_path, target_size_kb=500):
    """
    压缩图片到指定大小（KB），确保压缩后的图片小于 target_size_kb。
    使用逐步降低质量的方法进行压缩。
    """
    try:
        img = Image.open(input_path)
        img = img.convert('RGB')  # 确保图像为RGB模式以保存为JPEG
        quality = 95

        while True:
            img.save(output_path, 'JPEG', quality=quality)
            size_kb = os.path.getsize(output_path) / 1024
            if size_kb <= target_size_kb or quality < 10:
                break
            quality -= 5
        thread_safe_logging('info', f"压缩图片: {output_path}，大小: {size_kb:.2f}KB，质量: {quality}")
    except Exception as e:
        thread_safe_logging('error', f"压缩图片失败: {input_path}, 错误: {e}")

class StorageManager:
    _instance = None
    _initialized = False
    _session_started = False  # 新增标志，表示是否已经开始会话

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(StorageManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, save_path='screenshots'):
        # 确保只初始化一次
        if StorageManager._initialized:
            return
            
        # 获取基础路径
        base_path = app_path()
        thread_safe_logging('info', f"StorageManager初始化 - 基础路径: {base_path}")
        self.config = self.load_config()

        # 初始化变量，但不立即创建文件夹
        self.base_path = base_path
        self.session_folder = None
        self.save_path = None
        self.original_path = None
        self.annotated_path = None
        self.log_path = None

        # 定义不可打印字符到组合键的映射（针对macOS的Command键）
        self.unicode_key_map = {
            "\x01": "Cmd+A",
            "\x02": "Cmd+B",
            "\x03": "Cmd+C",
            "\x04": "Cmd+D",
            "\x05": "Cmd+E",
            "\x06": "Cmd+F",
            "\x07": "Cmd+G",
            "\x08": "Cmd+H",
            "\x09": "Cmd+I",
            "\x0A": "Cmd+J",
            "\x0B": "Cmd+K",
            "\x0C": "Cmd+L",
            "\x0D": "Cmd+M",
            "\x0E": "Cmd+N",
            "\x0F": "Cmd+O",
            "\x10": "Cmd+P",
            "\x11": "Cmd+Q",
            "\x12": "Cmd+R",
            "\x13": "Cmd+S",
            "\x14": "Cmd+T",
            "\x15": "Cmd+U",
            "\x16": "Cmd+V",
            "\x17": "Cmd+W",
            "\x18": "Cmd+X",
            "\x19": "Cmd+Y",
            "\x1A": "Cmd+Z",
            "\x1B": "Esc",
            "\x7F": "Del",
            # 根据需要添加更多映射
        }

        # 定义可能的字体路径
        common_fonts = {
            "Darwin": [
                "/Library/Fonts/Arial.ttf",
                "/Library/Fonts/Helvetica.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/System/Library/Fonts/Supplemental/Helvetica.ttf"
            ],
            "Windows": "C:\\Windows\\Fonts\\arial.ttf",
            "Linux": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        }

        system = platform.system()
        font_paths = common_fonts.get(system)
        self.font = None

        if system == "Darwin" and isinstance(font_paths, list):
            for path in font_paths:
                if os.path.exists(path):
                    try:
                        self.font = ImageFont.truetype(path, 100)  # 设置字体大小为100
                        thread_safe_logging('info', f"已加载字体: {path}，字体大小: 100")
                        break
                    except IOError as e:
                        thread_safe_logging('warning', f"加载字体失败: {path}, 错误: {e}")
            if self.font is None:
                thread_safe_logging('warning', "未找到指定字体，使用默认字体。")
                self.font = ImageFont.load_default()
                thread_safe_logging('debug', "当前使用的字体是默认字体，无法调整大小。")
        else:
            if isinstance(font_paths, list):
                # 其他系统，多个字体路径
                for path in font_paths:
                    if os.path.exists(path):
                        try:
                            self.font = ImageFont.truetype(path, 100)
                            thread_safe_logging('info', f"已加载字体: {path}，字体大小: 100")
                            break
                        except IOError as e:
                            thread_safe_logging('warning', f"加载字体失败: {path}, 错误: {e}")
                if self.font is None:
                    thread_safe_logging('warning', "未找到指定字体，使用默认字体。")
                    self.font = ImageFont.load_default()
                    thread_safe_logging('debug', "当前使用的字体是默认字体，无法调整大小。")
            else:
                # 单一字体路径
                font_path = font_paths
                if font_path and os.path.exists(font_path):
                    try:
                        self.font = ImageFont.truetype(font_path, 100)
                        thread_safe_logging('info', f"已加载字体: {font_path}，字体大小: 100")
                    except IOError as e:
                        thread_safe_logging('warning', f"加载字体失败: {font_path}, 错误: {e}")
                        self.font = ImageFont.load_default()
                        thread_safe_logging('debug', "当前使用的字体是默认字体，无法调整大小。")
                else:
                    thread_safe_logging('warning', "未找到指定字体，使用默认字体。")
                    self.font = ImageFont.load_default()
                    thread_safe_logging('debug', "当前使用的字体是默认字体，无法调整大小。")

        # 定义特殊键映射
        self.special_key_map = {
            "shift": "Shift",
            "ctrl": "Ctrl",
            "alt": "Alt",
            "cmd": "Cmd",
            "esc": "Esc",
            "delete": "Del",
            # 可以根据需要添加更多特殊键
        }

        StorageManager._initialized = True

    def load_config(self):
        """
        加载配置文件。
        """
        try:
            with open(resource_path('config.json'), 'r', encoding='utf-8') as f:
                config = json.load(f)
            thread_safe_logging('info', "存储管理器配置已加载。")
            return config
        except Exception as e:
            thread_safe_logging('error', f"加载存储管理器配置失败: {e}")
            return {}

    def getLogPath(self):
        return self.log_path

    def draw_star(self, draw, x, y, radius_outer, radius_inner, color_star):
        """在截图上绘制一个五角星，用于标记鼠标位置。"""
        num_points = 5
        points = []
        for i in range(num_points):
            angle = math.radians(i * 144)
            x_outer = x + radius_outer * math.cos(angle)
            y_outer = y - radius_outer * math.sin(angle)
            points.append((x_outer, y_outer))

            angle = math.radians(i * 144 + 72)
            x_inner = x + radius_inner * math.cos(angle)
            y_inner = y - radius_inner * math.sin(angle)
            points.append((x_inner, y_inner))

        draw.polygon(points, fill=color_star)

    def convert_key_name(self, key_name):
        """
        将不可打印字符转换为其对应的组合键名称（如 Cmd+A）。
        只有不可打印字符才转换为 Unicode 编码，可读字符保持不变。
        """
        converted = []
        # Split the key_name by space to handle continuous input
        keys = key_name.split(' ')
        for key in keys:
            if key.startswith('Key.'):
                special_key = key.split('.')[1]
                converted_key = self.special_key_map.get(special_key, special_key.capitalize())
                converted.append(converted_key)
            elif key in string.printable and not key.isspace():
                converted.append(key)
            else:
                converted.append(f"U+{ord(key):04X}")
        return ' '.join(converted)

    def save_screenshot(self, x=None, y=None, dx=None, dy=None, button=None, key_name=None, screenshot=None, filename=None):
        """保存截图"""
        if not self._session_started:
            thread_safe_logging('warning', "尝试保存截图但会话尚未开始")
            return False
            
        try:
            base_path = app_path()
            screen_size = pyautogui.size()
            screen_width, screen_height = screen_size

            # 捕获截图如果没有提供
            if screenshot and filename:
                img = screenshot
                # 从文件名中提取时间戳（假设文件名格式为 screenshot_TIMESTAMP.png）
                timestamp = os.path.splitext(filename)[0].split('_')[-1]
            else:
                img = pyautogui.screenshot()
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")

            # 定义文件名
            unannotated_filename = f"screenshot_{timestamp}_no_info.jpg"
            annotated_filename = f"screenshot_{timestamp}_with_info.jpg"

            unannotated_filepath = os.path.join(self.original_path, unannotated_filename)
            annotated_filepath = os.path.join(self.annotated_path, annotated_filename)
            #print(unannotated_filepath, annotated_filepath)

            # 保存不带信息的截图（仅绘制鼠标位置）
            img_unannotated = img.copy()
            draw_unannotated = ImageDraw.Draw(img_unannotated)

            if x is not None and y is not None:
                percent_x = (x / screen_width) * 100
                percent_y = (y / screen_height) * 100

                star_x = percent_x * img_unannotated.width / 100
                star_y = (100 - percent_y) * img_unannotated.height / 100

            # 转换为RGB并保存为JPEG
            img_unannotated_rgb = img_unannotated.convert('RGB')
            img_unannotated_rgb.save(unannotated_filepath, 'JPEG', quality=95)
            compress_image(unannotated_filepath, unannotated_filepath, target_size_kb=500)

            # 保存带信息的截图（绘制鼠标位置和附加信息）
            img_annotated = img.copy()
            draw_annotated = ImageDraw.Draw(img_annotated)

            has_info = False  # 标记是否有附加信息
            text = ""

            if x is not None and y is not None:
                # 绘制鼠标位置
                self.draw_star(draw_annotated, star_x, star_y, radius_outer=60, radius_inner=20, color_star=(255, 0, 0))

                # 准备文本信息
                text = f"Mouse: ({x}, {y}) | X: {percent_x:.2f}% | Y: {percent_y:.2f}%"
                if button is not None:
                    text += f" | Button: {button}"
                if dx is not None or dy is not None:
                    text += f" | Scroll delta: ({dx}, {dy})"

                has_info = True

            if key_name is not None:
                key_name_processed = self.convert_key_name(key_name)
                if has_info and text:
                    text += " | "
                elif not has_info:
                    text = ""
                text += f"Key: {key_name_processed}"
                thread_safe_logging('debug', f"Key name processed: {key_name_processed}")

                has_info = True

            if has_info and text:
                # 获取文本大小
                bbox = draw_annotated.textbbox((0, 0), text, font=self.font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]

                # 文本位置：顶部居中
                y_offset = 50  # 根据需要调整
                position = ((img_annotated.width - text_width) / 2, y_offset)

                # 绘制半透明背景
                background = (0, 0, 0, 128)  # 半透明黑色
                # 创建一个透明层
                overlay = Image.new('RGBA', img_annotated.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                overlay_draw.rectangle(
                    [position[0] - 10, position[1] - 10, position[0] + text_width + 10, position[1] + text_height + 10],
                    fill=background
                )
                # 合并图层
                img_with_overlay = Image.alpha_composite(img_annotated.convert('RGBA'), overlay)

                # 绘制文本
                draw_final = ImageDraw.Draw(img_with_overlay)
                draw_final.text(position, text, font=self.font, fill=(255, 255, 255))
                thread_safe_logging('debug', f"绘制信息文本的位置: {position}")

                # 转换为RGB并保存为JPEG
                img_with_overlay_rgb = img_with_overlay.convert('RGB')
                img_with_overlay_rgb.save(annotated_filepath, 'JPEG', quality=95)
                compress_image(annotated_filepath, annotated_filepath, target_size_kb=500)
            else:
                # 如果没有附加信息，仅保存带有鼠标位置的截图
                img_annotated_rgb = img_annotated.convert('RGB')
                img_annotated_rgb.save(annotated_filepath, 'JPEG', quality=95)
                compress_image(annotated_filepath, annotated_filepath, target_size_kb=500)

            # 获取相对路径
            relative_unannotated_path = os.path.relpath(unannotated_filepath, base_path)
            relative_annotated_path = os.path.relpath(annotated_filepath, base_path)

            # 记录日志
            thread_safe_logging('info', f"已保存无信息截图: {relative_unannotated_path}")
            thread_safe_logging('info', f"已保存有信息截图: {relative_annotated_path}")

            # 返回不带信息的截图相对路径
            return relative_unannotated_path

        except Exception as e:
            thread_safe_logging('error', f"截屏失败: {e}")
            return "截屏失败"

    def zip_folder(self, folder_path, zip_path):
        """
        将指定文件夹打包成 ZIP 文件，排除之前生成的压缩包和加密文件。
        """
        try:
            thread_safe_logging('info', f"开始压缩文件夹 - 源文件夹: {folder_path}")
            thread_safe_logging('info', f"ZIP文件将保存至: {zip_path}")
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                file_count = 0
                for root, dirs, files in os.walk(folder_path):
                    thread_safe_logging('info', f"正在处理子目录: {root}")
                    # 过滤掉不需要的文件
                    files = [f for f in files if not (f.endswith('.zip') or f.endswith('.enc'))]
                    thread_safe_logging('info', f"发现文件数量: {len(files)}")
                    
                    for file in files:
                        abs_file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(abs_file_path, os.path.dirname(folder_path))
                        zipf.write(abs_file_path, relative_path)
                        file_count += 1
                        thread_safe_logging('info', f"已添加文件: {relative_path}")
            
            zip_size = os.path.getsize(zip_path) / (1024 * 1024)  # Convert to MB
            thread_safe_logging('info', f"压缩完成 - 文件数: {file_count}, ZIP大小: {zip_size:.2f}MB")
            
        except Exception as e:
            thread_safe_logging('error', f"压缩失败 - 文件夹: {folder_path}, 错误: {str(e)}")
            raise

    def encrypt_file(self, input_file, output_file, key, iv):
        """
        使用 AES 加密文件。
        """
        try:
            thread_safe_logging('info', f"开始加密文件 - 源文件: {input_file}")
            thread_safe_logging('info', f"加密文件将保存至: {output_file}")
            
            input_size = os.path.getsize(input_file) / (1024 * 1024)  # Convert to MB
            thread_safe_logging('info', f"源文件大小: {input_size:.2f}MB")

            cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
            with open(input_file, 'rb') as f:
                plaintext = f.read()
                thread_safe_logging('info', f"已读取源文件，准备加密")

            # 使用 PKCS7 填充数据
            padded_data = pad(plaintext, AES.block_size)
            ciphertext = cipher.encrypt(padded_data)

            # 保存 IV + 加密后的数据
            with open(output_file, 'wb') as f:
                f.write(iv.encode('utf-8') + ciphertext)

            output_size = os.path.getsize(output_file) / (1024 * 1024)  # Convert to MB
            thread_safe_logging('info', f"加密完成 - 加密后文件大小: {output_size:.2f}MB")
            
        except Exception as e:
            thread_safe_logging('error', f"加密失败 - 文件: {input_file}, 错误: {str(e)}")
            raise

    def upload_file(self, file_path):
        """
        使用 ModelScope API 上传打包后的 ZIP 文件。
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        config = self.config.get('modelscope', {})
        access_token = config.get('access_token')
        owner_name = config.get('owner_name')
        dataset_name = config.get('dataset_name')
        commit_message = config.get('commit_message', 'upload dataset folder to repo')
        repo_type = config.get('repo_type', 'dataset')
        print('\n' + access_token, owner_name, dataset_name, commit_message, repo_type)
        
        # 读取用户名并构建上传路径（用户名作为文件夹，时间戳作为文件名）
        try:
            with open(os.path.join(app_path(), 'username.txt'), 'r', encoding='utf-8') as f:
                username = f.read().strip()
                path_in_repo = f"{username}/{timestamp}.zip.enc"
                print(f"上传路径: {path_in_repo}")
        except:
            print("未找到用户名文件")
            path_in_repo = f"{timestamp}.zip.enc"

        if not os.path.exists(file_path):
            thread_safe_logging('error', f"错误: 文件 {file_path} 不存在。上传失败。")
            return

        api = HubApi()
        api.login(access_token)

        try:
            repo_id = f"{owner_name}/{dataset_name}"
            print(f"正在上传到仓库: {repo_id}")
            print(f"文件路径: {file_path}")
            print(f"仓库内路径: {path_in_repo}")
            
            api.upload_file(
                repo_id=repo_id,
                path_or_fileobj=file_path,
                path_in_repo=path_in_repo,
                commit_message=commit_message,
                repo_type=repo_type
            )
            thread_safe_logging('info', f"成功: 文件已上传到 {repo_id}/{path_in_repo}")
            print(f"文件已上传到: {repo_id}/{path_in_repo}")
        except Exception as e:
            thread_safe_logging('error', f"错误: 上传文件时出错: {e}")
            print(f"上传错误: {str(e)}")

    def process_session(self):
        """
        压缩、加密并上传当前会话的文件夹。
        """
        try:
            thread_safe_logging('info', f"开始处理会话文件夹: {self.session_folder}")
            
            zip_path = os.path.join(self.session_folder, f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
            encrypted_zip_path = zip_path + ".enc"
            
            thread_safe_logging('info', f"计划生成的ZIP文件路径: {zip_path}")
            thread_safe_logging('info', f"计划生成的加密文件路径: {encrypted_zip_path}")

            self.zip_folder(self.session_folder, zip_path)

            encryption_config = self.config.get('encryption', {})
            key = encryption_config.get('key')
            iv = encryption_config.get('iv')
            
            if not key or not iv:
                thread_safe_logging('error', "加密失败 - 配置缺失: key 或 iv 未配置")
                return

            thread_safe_logging('info', "开始加密ZIP文件")
            self.encrypt_file(zip_path, encrypted_zip_path, key, iv)

            thread_safe_logging('info', "开始上传加密文件")
            self.upload_file(encrypted_zip_path)

            thread_safe_logging('info', f"会话处理完成 - 文件夹: {self.session_folder}")

            # 在所有处理完成后，删除会话文件夹
            #try:
                #import shutil
                #shutil.rmtree(self.session_folder)
                #print(f"\n会话文件夹已删除: {self.session_folder}")
                #thread_safe_logging('info', f"会话文件夹已删除: {self.session_folder}")
            #except Exception as e:
                #thread_safe_logging('error', f"删除文件夹失败: {str(e)}")
                #print(f"\n删除文件夹失败: {str(e)}")

        except Exception as e:
            thread_safe_logging('error', f"会话处理失败 - 文件夹: {self.session_folder}, 错误: {str(e)}")
            raise

    def start_session(self):
        """在用户同意后启动会话"""
        if not self._session_started:
            # 创建以当前时间戳为名称的文件夹
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.session_folder = os.path.join(os.path.join(self.base_path, "records"), timestamp)
            thread_safe_logging('info', f"StorageManager - 创建会话文件夹: {self.session_folder}")
            
            # 创建所需的文件夹
            os.makedirs(self.session_folder, exist_ok=True)
            self.save_path = os.path.join(self.session_folder, 'screenshots')
            os.makedirs(self.save_path, exist_ok=True)
            
            self.original_path = os.path.join(self.save_path, 'original')
            self.annotated_path = os.path.join(self.save_path, 'annotated')
            os.makedirs(self.original_path, exist_ok=True)
            os.makedirs(self.annotated_path, exist_ok=True)
            
            self.log_path = os.path.join(self.session_folder, 'log')
            os.makedirs(self.log_path, exist_ok=True)
            
            StorageManager._session_started = True
            return True
        return False