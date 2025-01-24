# action_recorder.py

import os
import json
import threading
import time
from datetime import datetime
from pynput import mouse, keyboard
from logger import thread_safe_logging, global_log_dir
from PyQt5 import QtCore
import psutil
import ctypes
from ctypes import wintypes
import pyautogui
from storage import StorageManager
from frozen_dir import app_path
import platform
import string

from threading import Timer

class ActionRecorder(QtCore.QObject):
    action_recorded = QtCore.pyqtSignal(str)

    def __init__(self, log_file='log/user_actions.log', save_path='screenshots'):
        super().__init__()
        base_path = app_path()
        self.log_file = os.path.join(base_path, log_file)
        self.save_path = os.path.join(base_path, save_path)
        # os.makedirs(self.save_path, exist_ok=True)
        self.storage_manager = StorageManager(self.save_path)
        self.running = False
        self.data = []
        self.lock = threading.Lock()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"user_actions_real_time_{timestamp}.jsonl"
        self.log_filename = filename

        # 获取屏幕宽度和高度（用于计算相对位置）
        self.screen_width, self.screen_height = pyautogui.size()

        # ---------- 拖拽相关 ----------
        self.dragging = False
        self.drag_start_x = None
        self.drag_start_y = None

        # ---------- 滚动累积相关 ----------
        self.scroll_accumulator = {
            "direction": None,
            "acc_dy": 0,
            "x": None,
            "y": None,
            "last_time": 0.0
        }
        self.scroll_timeout = 2.0

        # ---------- 键盘连续输入相关 ----------
        self.current_action = ""       # 用于累计用户连续输入的字符串
        self.action_timer = None       # 定时器，用来判断用户是否停止输入
        self.last_key_time = time.time()
        self.max_action_length = 50    # 单次动作最大长度，可自行调整

        self.mouse_listener = mouse.Listener(on_click=self.on_click, on_scroll=self.on_scroll)
        self.keyboard_listener = keyboard.Listener(on_press=self.on_press)

        # 启动一个线程来监控滚动超时
        self.scroll_thread = threading.Thread(target=self.monitor_scroll_timeout, daemon=True)
        self.scroll_thread.start()

        # 启动按键处理线程
        #self.key_process_thread = threading.Thread(target=self._process_key_buffer, daemon=True)
        #self.key_process_thread.start()

        # ---------- action 数量相关 ----------
        self.prev_action_count = 0
        self.cur_action_count = 0
        self.max_action_threshold = 300
        self.batch_count = 1

        self.known_key_map = {
            # Alphanumeric keys
            "a": "a",
            "b": "b",
            "c": "c",
            "d": "d",
            "e": "e",
            "f": "f",
            "g": "g",
            "h": "h",
            "i": "i",
            "j": "j",
            "k": "k",
            "l": "l",
            "m": "m",
            "n": "n",
            "o": "o",
            "p": "p",
            "q": "q",
            "r": "r",
            "s": "s",
            "t": "t",
            "u": "u",
            "v": "v",
            "w": "w",
            "x": "x",
            "y": "y",
            "z": "z",

            # Numbers and symbols
            "0": "0",
            "1": "1",
            "2": "2",
            "3": "3",
            "4": "4",
            "5": "5",
            "6": "6",
            "7": "7",
            "8": "8",
            "9": "9",
            "=": "=",
            "-": "-",
            ";": ";",
            "'": "'",
            ",": ",",
            ".": ".",
            "/": "/",
            "\\": "\\",
            "[": "[",
            "]": "]",
            "`": "`",

            # Special keys
            "Key.space": "space",
            "Key.enter": "enter",
            "Key.backspace": "backspace",
            "Key.tab": "tab",
            "Key.delete": "delete",
            "Key.shift": "shift",
            "Key.caps_lock": "caps_lock",
            "Key.ctrl_l": "ctrl_l",  # Ctrl key remains as ctrl
            "Key.ctrl_r": "ctrl_r",  # Ctrl key remains as ctrl
            "Key.alt_l": "alt_l",
            "Key.alt_gr": "alt_gr",
            "Key.cmd": "cmd",  # macOS cmd key
            "Key.cmd_l": "cmd_l",  # Left cmd key
            "Key.cmd_r": "cmd_r",  # Right cmd key
            "Key.fn": "fn",  # Fn key (for Mac-specific functions)
            "Key.shift_l": "shift_l",  # Left shift
            "Key.shift_r": "shift_r",  # Right shift
            "Key.ctrl": "ctrl",  # Standard ctrl key (no change)
            "Key.esc": "esc",

            # Function keys (F1-F12)
            "Key.f1": "f1",
            "Key.f2": "f2",
            "Key.f3": "f3",
            "Key.f4": "f4",
            "Key.f5": "f5",
            "Key.f6": "f6",
            "Key.f7": "f7",
            "Key.f8": "f8",
            "Key.f9": "f9",
            "Key.f10": "f10",
            "Key.f11": "f11",
            "Key.f12": "f12",

            # Arrow keys
            "Key.up": "up",
            "Key.down": "down",
            "Key.left": "left",
            "Key.right": "right",

            # Page and navigation keys
            "Key.page_up": "page_up",
            "Key.page_down": "page_down",
            "Key.home": "home",
            "Key.end": "end",
            "Key.insert": "insert",
            "Key.scroll_lock": "scroll_lock",
            "Key.num_lock": "num_lock",

            # Numeric keypad keys (for macOS keyboards with numpad)
            "Key.num_1": "1",
            "Key.num_2": "2",
            "Key.num_3": "3",
            "Key.num_4": "4",
            "Key.num_5": "5",
            "Key.num_6": "6",
            "Key.num_7": "7",
            "Key.num_8": "8",
            "Key.num_9": "9",
            "Key.num_0": "0",
            "Key.num_decimal": ".",
            "Key.num_enter": "enter",
            "Key.num_add": "+",
            "Key.num_subtract": "-",
            "Key.num_multiply": "*",
            "Key.num_divide": "/",
            "Key.num_equals": "equals",

            # MacOS-specific key mappings (for Cmd+A, Cmd+C, etc.)
            "'\\x01'": "Cmd+A",  # Cmd+A
            "'\\x02'": "Cmd+B",  # Cmd+B
            "'\\x03'": "Cmd+C",  # Cmd+C
            "'\\x04'": "Cmd+D",  # Cmd+D
            "'\\x05'": "Cmd+E",  # Cmd+E
            "'\\x06'": "Cmd+F",  # Cmd+F
            "'\\x07'": "Cmd+G",  # Cmd+G
            "'\\x08'": "Cmd+H",  # Cmd+H
            "'\\x09'": "Cmd+I",  # Cmd+I
            "'\\x0a'": "Cmd+J",  # Cmd+J
            "'\\x0b'": "Cmd+K",  # Cmd+K
            "'\\x0c'": "Cmd+L",  # Cmd+L
            "'\\x0d'": "Cmd+M",  # Cmd+M
            "'\\x0e'": "Cmd+N",  # Cmd+N
            "'\\x0f'": "Cmd+O",  # Cmd+O
            "'\\x10'": "Cmd+P",  # Cmd+P
            "'\\x11'": "Cmd+Q",  # Cmd+Q
            "'\\x12'": "Cmd+R",  # Cmd+R
            "'\\x13'": "Cmd+S",  # Cmd+S
            "'\\x14'": "Cmd+T",  # Cmd+T
            "'\\x15'": "Cmd+U",  # Cmd+U
            "'\\x16'": "Cmd+V",  # Cmd+V
            "'\\x17'": "Cmd+W",  # Cmd+W
            "'\\x18'": "Cmd+X",  # Cmd+X
            "'\\x19'": "Cmd+Y",  # Cmd+Y
            "'\\x1a'": "Cmd+Z"  # Cmd+Z
        }

        # ---------- 键盘press前截图 ----------
        self.is_press_start = True
        self.press_start_screenshot = None

        # ---------- 鼠标press前截图 ----------
        self.is_click_press_start = True
        self.click_press_start_screenshot = None

        # ---------- 鼠标scroll前截图 ----------
        self.is_scroll_press_start = True
        self.scroll_press_start_screenshot = None

    def resource_path(relative_path):
        import sys
        if getattr(sys, 'frozen', False):  # 是否Bundle Resource
            base_path = sys._MEIPASS
        else:
            base_path = os.path.abspath(".")
        if base_path.endswith('_internal'):
            base_path = base_path[:-9]
        return os.path.join(base_path, relative_path)  # 去掉 _internal

    def count_file(self, foldername):
        """
        统计指定文件夹中的文件数量。

        :param foldername: 文件夹的路径
        :return: 文件数量（整数）
        """
        try:
            # 检查文件夹是否存在
            if not os.path.exists(foldername):
                #print(f"Folder '{foldername}' does not exist.")
                return 0

            # 使用 os.listdir 统计文件数量
            file_count = len([f for f in os.listdir(foldername) if os.path.isfile(os.path.join(foldername, f))])
            return file_count
        except Exception as e:
            print(f"Error counting files in folder '{foldername}': {e}")
            return 0

    def copy_folder(self, src_folder, dest_folder):
        """
        将 src_folder 复制到 dest_folder。

        :param src_folder: 源文件夹路径
        :param dest_folder: 目标文件夹路径
        """
        import shutil
        import os
        try:
            # 检查源文件夹是否存在
            if not os.path.exists(src_folder):
                #print(f"Source folder '{src_folder}' does not exist or is empty.")
                return False

            # 检查源文件夹是否有内容
            if len(os.listdir(src_folder)) == 0:
                print(f"Source folder '{src_folder}' is empty.")
                return False

            # 如果目标文件夹已存在，先删除
            if os.path.exists(dest_folder):
                shutil.rmtree(dest_folder)
                print(f"Existing destination folder '{dest_folder}' has been removed.")

            # 使用 shutil.copytree 复制整个文件夹
            shutil.copytree(src_folder, dest_folder)
            print(f"Folder '{src_folder}' successfully copied to '{dest_folder}'.")
            return True
        except Exception as e:
            print(f"Error copying folder '{src_folder}' to '{dest_folder}': {e}")
            return False

    def copy_file(self, src_file, dest_file):
        """
        将 src_file 复制到 dest_file。

        :param src_file: 源文件路径
        :param dest_file: 目标文件路径
        """
        import shutil
        try:
            # 检查源文件是否存在
            if not os.path.exists(src_file):
                #print(f"Source file '{src_file}' does not exist.")
                return False

            # 获取目标文件夹路径并创建（如果不存在）
            dest_folder = os.path.dirname(dest_file)
            if not os.path.exists(dest_folder):
                os.makedirs(dest_folder)
                print(f"Destination folder '{dest_folder}' created.")

            # 复制文件
            shutil.copy2(src_file, dest_file)
            print(f"File '{src_file}' successfully copied to '{dest_file}'.")
            return True
        except Exception as e:
            print(f"Error copying file '{src_file}' to '{dest_file}': {e}")
            return False

    def encrypt_file(self, input_file, output_file, key, iv):
        """
        使用 AES 加密文件
        """
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
        try:
            cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
            with open(input_file, 'rb') as f:
                plaintext = f.read()
            # 使用 PKCS7 填充数据
            ciphertext = cipher.encrypt(pad(plaintext, AES.block_size))
            # 保存 IV + 加密后的数据
            with open(output_file, 'wb') as f:
                f.write(iv.encode('utf-8') + ciphertext)  # 将 IV 和加密后的数据写入文件
            thread_safe_logging('info', f"成功: 文件 {input_file} 已加密为 {output_file}。")
        except Exception as e:
            thread_safe_logging('error', f"错误: 加密文件 {input_file} 时出错: {e}")

    def zip_xxx_count(self, session_folder, start, end):
        """
        将 current_copy_folder 中的文件压缩处理。

        1. 从 original 文件夹中取文件，按照文件名称排序后，取下标为 start~end 的文件（1-based 下标）。
        2. 从 .jsonl 文件中读取对应行的数据，取下标为 start~end 的行（1-based 下标）。
        3. 将这两部分数据打包为 zip 文件，压缩结构如下：
        screenshots/
        ├── xxx.jpg
        ├── …
        log/
        ├── xxx.jsonl

        :param session_folder: 会话文件夹路径
        :param start: 开始下标（1-based）
        :param end: 结束下标（1-based）
        """
        import zipfile
        try:
            # 1. 处理图片文件
            original_folder = os.path.join(session_folder, "screenshots", "original")
            if not os.path.exists(original_folder):
                raise FileNotFoundError(f"Original folder '{original_folder}' does not exist.")

            files = sorted(os.listdir(original_folder))  # 按文件名排序
            selected_files = files[start - 1:end]  # 下标从 1 开始，因此调整为 0-based
            selected_file_paths = [os.path.join(original_folder, f) for f in selected_files]

            # 2. 处理JSONL文件
            log_folder = os.path.join(session_folder, "log")
            if not os.path.exists(log_folder):
                raise FileNotFoundError(f"Log folder '{log_folder}' does not exist.")

            # 创建必要的目录结构
            copy_dir = os.path.join(session_folder, "copy")
            copy_screenshots_dir = os.path.join(copy_dir, "screenshots")
            copy_log_dir = os.path.join(copy_dir, "log")
            os.makedirs(copy_screenshots_dir, exist_ok=True);print("make screenshot dir success")
            os.makedirs(copy_log_dir, exist_ok=True);print("make log dir success")

            # 创建临时JSONL文件来存储选定的行
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            temp_jsonl = os.path.join(copy_log_dir, f"{timestamp}.jsonl")
            
            # 读取原始JSONL文件并提取指定行
            log_files = os.listdir(log_folder)
            jsonl_file = os.path.join(log_folder, log_files[0])  # 只有一个文件
            with open(jsonl_file, 'r', encoding='utf-8') as source, \
                 open(temp_jsonl, 'w', encoding='utf-8') as target:
                lines = source.readlines()
                selected_lines = lines[start - 1:end]  # 下标从 1 开始，因此调整为 0-based
                print(f"Selected lines: ", end - start)
                target.writelines(selected_lines)

            # 3. 创建zip文件
            zip_file_name = os.path.join(copy_dir, f"{timestamp}.zip")
            with zipfile.ZipFile(zip_file_name, "w", zipfile.ZIP_DEFLATED) as zipf:
                # 添加图片文件到 screenshots 目录
                for file_path in selected_file_paths:
                    arcname = os.path.join("screenshots", os.path.basename(file_path))
                    zipf.write(file_path, arcname)
                    print(f"Added to zip: {arcname}")
                
                # 添加JSONL文件到 log 目录
                arcname = os.path.join("log", os.path.basename(temp_jsonl))
                zipf.write(temp_jsonl, arcname)
                print(f"Added to zip: {arcname}")

            # 清理临时JSONL文件
            os.remove(temp_jsonl)
            # 清理临时目录
            os.rmdir(copy_screenshots_dir)
            os.rmdir(copy_log_dir)

            print(f"Zip file created: {zip_file_name}")
            return zip_file_name

        except Exception as e:
            print(f"Error in zip_xxx_count: {e}")
            return None

    def monitor_action_count(self):
        """
        只分批传图片，不传jsonl
        也不用copy，直接用双指针读 original文件夹就行
        """
        # return
        self.max_action_threshold = 300
        First = True
        while True:
            if (First == True):
                time.sleep(10)  # 这是为了开发测试时，让开始多点几下，使得有记录）后面直接改为监控的时间interval就行
                First = False
            # 后面记得把下面的加上try except
            # +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
            session_folder = self.storage_manager.session_folder

            if self.storage_manager.session_folder is None:
                records_dir = os.path.join(app_path(), "records")
                if os.path.exists(records_dir):
                    sessions = os.listdir(records_dir)
                    if len(sessions) == 1:
                        session_folder = os.path.join(records_dir, sessions[0])
                        print("use local!")
                        self.storage_manager.session_folder = session_folder
                    else:
                        raise ValueError(f"Expected exactly one session folder, found {len(sessions)}")
                else:
                    raise ValueError("Records directory does not exist")

            original_folder = os.path.join(session_folder, 'screenshots', 'original')
            log_folder = os.path.join(session_folder, 'log')
            log_file_path = os.path.join(log_folder, self.log_filename)
            # print("@monitor_action_count : session_folder ---",session_folder)
            # print("@monitor_action_count : original_folder ---",original_folder)
            # print("@monitor_action_count : log_file ---",log_file_path)
            # print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
            # 统计增量
            self.cur_action_count = self.count_file(original_folder)
            if self.cur_action_count - self.prev_action_count > self.max_action_threshold:
                # ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
                # 压缩, 加密，上传
                # 还需要考虑：如果没有成功上传，需要将数据先留着，下次再上传
                # 改成这种吧，如果没有成功上传，就不更新 prev_action_count 和 batch_count 就行了
                # copy文件夹都一律删除
                zip_file_name = self.zip_xxx_count(session_folder, self.prev_action_count + 1,
                                                   self.cur_action_count)  # 注意区间问题
                key = "16byteslongkey!!"
                iv = "16byteslongiv!!!"
                enc_zip_file_name = zip_file_name + ".enc"
                self.encrypt_file(zip_file_name, enc_zip_file_name, key, iv)
                upload_success = False
                if zip_file_name is not None:
                    # 上传
                    upload_success = self.storage_manager.upload_file(enc_zip_file_name,
                                                                      self.cur_action_count - self.prev_action_count,
                                                                      self.batch_count)
                # ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
                # 删除
                if upload_success:
                    self.batch_count += 1
                    self.prev_action_count = self.cur_action_count
                    from storage import resource_path
                    batch_count_file = resource_path(".batch_count!dont_delete!!!")
                    with open(batch_count_file, 'w') as f:
                        f.write(str(self.batch_count))
                    sum_file = resource_path(".sum_count!dont_delete!!!")
                    with open(sum_file, 'w') as f:
                        f.write(str(self.cur_action_count))
                    print(f"Successfully uploaded file: {enc_zip_file_name}")
                else:
                    pass

                time.sleep(60)

        pass

    def start_recording(self):
        if not self.running:
            self.running = True
            # 启动一个线程来监控产生的action数量
            self.action_thread = threading.Thread(target=self.monitor_action_count, daemon=True)
            self.action_thread.start()
            self.mouse_listener.start()
            self.keyboard_listener.start()
            thread_safe_logging('info', "用户操作记录器已启动。")
            thread_safe_logging('debug', "开启事件监听器。")

    def stop_recording(self):
        if self.running:
            self.running = False

            # 停止前，先把滚动的累积事件结算
            self.finalize_scroll_accumulation(self.scroll_press_start_screenshot)

            # 停止前，也需要把最后一次的键盘输入保存
            if self.action_timer:
                self.action_timer.cancel()
            self.finish_action()

            self.mouse_listener.stop()
            self.keyboard_listener.stop()
            thread_safe_logging('info', "用户操作记录器已停止。")
            thread_safe_logging('debug', "关闭事件监听器。")
            self.save_data()

    def get_active_app(self):
        """获取当前前台进程名称"""
        try:
            system = platform.system()
            if system == "Windows":
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                pid = wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                process = psutil.Process(pid.value)
                return process.name()
            elif system == "Darwin":
                import subprocess
                script = '''
                tell application "System Events"
                    set frontApp to name of first application process whose frontmost is true
                end tell
                return frontApp
                '''
                front_app = subprocess.check_output(['osascript', '-e', script]).decode().strip()
                return front_app
            else:
                # 对于其他系统，可以使用 psutil 或其他方法
                return "未知应用"
        except Exception as e:
            thread_safe_logging('error', f"获取活动应用程序时出错: {e}")
            return "未知应用"

    def on_click(self, x, y, button, pressed):
        # 都用press之前的截图
        if self.running:
            # 若有未完成的滚动事件，先结算
            self.finalize_scroll_accumulation(self.scroll_press_start_screenshot)

            active_app = self.get_active_app()

            # 生成字符串格式的鼠标位置
            position_x = f"{x}/{self.screen_width}"
            position_y = f"{y}/{self.screen_height}"

            if pressed:
                #print("press")
                # 截图
                self.click_press_start_screenshot = pyautogui.screenshot()
                # 鼠标按下，记录拖拽开始
                self.drag_start_x, self.drag_start_y = x, y
                # 记录按下事件
                event_data = {
                    "timestamp": time.time(),
                    "event": "mouse_click",
                    "button": f"{button}.press",
                    "position": {"x": x, "y": y},
                    "active_app": active_app
                }
                thread_safe_logging('debug', f"捕获到鼠标按下事件: {event_data}")
                self.handle_event(event_data, screenshot=self.click_press_start_screenshot)
            else:
                # 鼠标松开，记录拖拽结束
                #print("release")
                event_data = {
                        "timestamp": time.time(),
                        "event": "mouse_click",
                        "button": f"{button}.release",
                        "position": {"x": x, "y": y},
                        "active_app": active_app
                    }
                    # 记录松开事件
                thread_safe_logging('debug', f"捕获到鼠标松开事件: {event_data}")
                self.handle_event(event_data, screenshot=self.click_press_start_screenshot)
                self.click_press_start_screenshot = None

    def on_scroll(self, x, y, dx, dy):
        if self.running:
            self.handle_vertical_scroll(x, y, dy)

    def on_press(self, key):
        """键盘按下时，将当前按键加入连续输入的缓冲区。"""
        if not self.running:
            return

        # 若有未完成的滚动事件，先结算
        self.finalize_scroll_accumulation(self.scroll_press_start_screenshot)

        # 键盘序列的第一个press截图
        if self.is_press_start is True:
            self.press_start_screenshot = pyautogui.screenshot()
            #print("[*] press_start_screenshot")
        self.is_press_start = False

        key_pressed = self._get_key_name(key)

        # 如果一次动作超过预设最大长度，先保存之前的再开始新动作
        # if len(self.current_action) + len(key_pressed) > self.max_action_length:
        #     self.finish_action()

        self.current_action += key_pressed + " "

        # 重置/启动定时器：1.5 秒后若无新的按键按下，则视为一次完整输入
        if self.action_timer:
            self.action_timer.cancel()
        self.action_timer = Timer(1.5, self.finish_action)
        self.action_timer.start()

    def _get_key_name(self, key_name):
        #print("key_name: ",end="")
        #print(key_name)
        # print(type(key_name))
        try:
            key_name_str = str(key_name).strip()
            #print("key_name_str: ", key_name_str)
        # print("known_key_map[key_name_str]", self.known_key_map[key_name_str])
        except:
            return ""
        try:
            if(key_name_str in self.known_key_map):
                #print("key_name_str in self.known_key_map:      ", self.known_key_map[key_name_str])
                return self.known_key_map[key_name_str]
            else:
                return key_name_str
        except:
            return ""

    def finish_action(self):
        """当用户停止输入超过 1 秒，或长度超标时，将本段输入合并为一次事件。"""
        if not self.current_action.strip():
            return
        mouse_x, mouse_y = pyautogui.position()
        active_app = self.get_active_app()
        event_data = {
            "timestamp": time.time(),
            "event": "key_press",
            "key": self.current_action.strip(),
            "position": {"x": mouse_x, "y": mouse_y},
            "active_app": active_app
        }
        self.handle_event(event_data, self.press_start_screenshot)
        self.current_action = ""
        self.is_press_start = True
        self.press_start_screenshot = None

    def handle_vertical_scroll(self, x, y, dy):
        """累加垂直滚动事件。若方向改变或超时则生成一次 mouse_scroll 事件并截图。"""
        now = time.time()
        old_dir = self.scroll_accumulator["direction"]
        old_time = self.scroll_accumulator["last_time"]

        if self.is_scroll_press_start is True:
            self.scroll_press_start_screenshot = pyautogui.screenshot()
            #print("[*] scroll_press_start_screenshot")
            self.is_scroll_press_start = False

        if dy == 0:
            return

        new_dir = "up" if dy > 0 else "down"

        if old_dir is None:
            self.scroll_accumulator["direction"] = new_dir
            self.scroll_accumulator["acc_dy"] = dy
            self.scroll_accumulator["x"] = x
            self.scroll_accumulator["y"] = y
            self.scroll_accumulator["last_time"] = now
        else:
            # 超时，变向 检测；删掉
            # time_diff = now - old_time
            # if new_dir != old_dir or time_diff > self.scroll_timeout:
            #     self.finalize_scroll_accumulation()
            #     self.scroll_accumulator["direction"] = new_dir
            #     self.scroll_accumulator["acc_dy"] = dy
            #     self.scroll_accumulator["x"] = x
            #     self.scroll_accumulator["y"] = y
            #     self.scroll_accumulator["last_time"] = now
            # else:

            # 鼠标位置改变，结束这次连续滚动，结算
            now_x, now_y = pyautogui.position()
            if abs(now_x - self.scroll_accumulator["x"]) > 20 or abs(now_y - self.scroll_accumulator["y"] > 20):
                self.finalize_scroll_accumulation()
            else:
                self.scroll_accumulator["acc_dy"] += dy
                self.scroll_accumulator["x"] = x
                self.scroll_accumulator["y"] = y
                self.scroll_accumulator["last_time"] = now

    def finalize_scroll_accumulation(self, screenshot=None):
        """结算滚动累积，生成一次 mouse_scroll 事件并截图。"""
        direction = self.scroll_accumulator["direction"]
        if direction is None:
            return

        acc_dy = self.scroll_accumulator["acc_dy"]
        x = self.scroll_accumulator["x"]
        y = self.scroll_accumulator["y"]

        position_x = f"{x}/{self.screen_width}"
        position_y = f"{y}/{self.screen_height}"

        active_app = self.get_active_app()
        event_data = {
            "timestamp": time.time(),
            "event": "mouse_scroll",
            "delta_x": 0,
            "delta_y": acc_dy,
            "position": {"x": x, "y": y},
            "active_app": active_app
        }
        self.handle_event(event_data, screenshot = self.scroll_press_start_screenshot)

        self.is_scroll_press_start = True
        self.scroll_press_start_screenshot = None

        thread_safe_logging('debug', f"结算滚动事件: {event_data}")

        self.scroll_accumulator = {
            "direction": None,
            "acc_dy": 0,
            "x": None,
            "y": None,
            "last_time": 0.0
        }

    def monitor_scroll_timeout(self):
        """
        持续监控滚动事件的超时，如果超过 scroll_timeout 时间没有新的滚动，
        则结算当前的滚动累积。
        """
        while True:
            if not self.running:
                time.sleep(0.1)
                continue
            now = time.time()
            last_time = self.scroll_accumulator["last_time"]
            if self.scroll_accumulator["direction"] is not None and (now - last_time) > self.scroll_timeout:
                self.finalize_scroll_accumulation()
            time.sleep(0.1)

    def handle_event(self, event, screenshot=None):
        """对录制的事件进行截图并保存，再写入数据队列。"""
        try:
            action_type = event.get('event')  # 获取事件类型

            if action_type in ['mouse_click', 'mouse_scroll', 'key_press']:
                # 创建 action_content 字典，用于存储详细事件内容
                action_content = {}

                if action_type in ['mouse_click', 'mouse_scroll']:
                    x = event['position']['x']
                    y = self.screen_height - event['position']['y']
                    button = event.get('button')

                    if action_type == 'mouse_scroll':
                        # 获取水平和垂直滚动量
                        dx = event.get('delta_x', 0)  # 水平方向的滚动量
                        dy = event.get('delta_y', 0)  # 垂直方向的滚动量
                        screenshot_path = self.storage_manager.save_screenshot(x=x, y=y, dx=dx, dy=dy,
                                                                               screenshot=screenshot)
                        action_content = {
                            "position": {
                                "x": x,
                                "y": y,
                                "max_x": self.screen_width,
                                "max_y": self.screen_height
                            },
                            "button": None,
                            "delta": {
                                "dx": dx,
                                "dy": dy
                            },
                            "key": None  # 对于鼠标事件，key 设置为 None
                        }
                    else:  # mouse_click
                        screenshot_path = self.storage_manager.save_screenshot(x=x, y=y, screenshot=screenshot, button=button)
                        action_content = {
                            "position": {
                                "x": x,
                                "y": y,
                                "max_x": self.screen_width,
                                "max_y": self.screen_height
                            },
                            "button": button,
                            "delta": None,  # 对于非滚动事件，delta 设置为 None
                            "key": None  # 对于鼠标事件，key 设置为 None
                        }

                elif action_type == 'key_press':
                    key_name = event['key']
                    if screenshot is not None:
                        screenshot_path = self.storage_manager.save_screenshot(key_name=key_name, screenshot=screenshot)
                    else:
                        screenshot_path = self.storage_manager.save_screenshot(key_name=key_name)
                    x = event['position']['x']
                    y = self.screen_height - event['position']['y']

                    action_content = {
                        "position": {
                            "x": x,
                            "y": y,
                            "max_x": pyautogui.size().width,
                            "max_y": pyautogui.size().height
                        },  # 记录鼠标位置
                        "button": None,
                        "delta": None,  # 对于键盘事件，delta 设置为 None
                        "key": key_name  # 键盘按键
                    }

                # 获取鼠标位置
                mouse_x, mouse_y = pyautogui.position()

                # 将 position 字段处理并移除
                if 'position' in event:
                    x = event['position']['x']
                    y = self.screen_height - event['position']['y']

                    # 设置 mouse_position 字段
                    mouse_position = {
                        "x": x,
                        "y": y,
                        "max_x": self.screen_width,
                        "max_y": self.screen_height
                    }

                    del event['position']  # 移除原有的 position 字段

                # 组装最终的事件结构
                new_event = {
                    "timestamp": time.time(),  # 保存时间戳
                    "action_type": action_type,  # 保存事件类型
                    "action_content": action_content,  # 保存事件内容
                    "active_app": event['active_app'],  # 活动应用
                    "screenshots_path": self.get_relative_screenshot_path(screenshot_path),  # 独立保存截图路径
                    "mouse_position": mouse_position  # 独立保存鼠标位置
                }

                # 实时保存事件到 JSONL 文件
                filename = self.storage_manager.getLogPath()
                filename = os.path.join(filename, self.log_filename)
                with open(filename, 'a', encoding='utf-8') as f:
                    json.dump(new_event, f, ensure_ascii=False)
                    f.write('\n')  # 每条事件一行

                self.action_recorded.emit(json.dumps(new_event))

                with self.lock:
                    self.data.append(new_event)

                thread_safe_logging('info', f"记录事件并保存截图: {new_event}")

        except Exception as e:
            thread_safe_logging('error', f"处理事件时出错: {e}")

    def save_data(self):
        """将本次运行期间累计的所有事件保存为 JSON 文件。"""
        try:
            if not self.data:
                return
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"user_actions_{timestamp}.json"
            filepath = self.storage_manager.getLogPath()
            filepath = os.path.join(filepath, filename)
            # print(filepath)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
            thread_safe_logging('info', f"用户操作数据已保存至: {filepath}")
            self.data.clear()
        except Exception as e:
            thread_safe_logging('error', f"保存用户操作数据时出错: {e}")

    def get_relative_screenshot_path(self, absolute_path):
        """
        从绝对路径中提取相对路径，从\\records\\开始
        """

        # 查找关键词位置
        if '/records/' in absolute_path:
            # 找到 records 路径，截取并返回
            return "records/" + absolute_path.split('/records/', 1)[-1]
        elif '\\records\\' in absolute_path:
            # 兼容Windows分隔符
            return "records\\" + absolute_path.split('\\records\\', 1)[-1]
        else:
            # 如果路径不包含 'records'，返回原路径
            return absolute_path