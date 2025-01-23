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

        self.known_key_map = {
            "": "",
            "Key.f1": "f1",
            "u": "u",
            "m": "m",
            "g": "g",
            "r": "r",
            "Key.insert": "insert",
            "Key.cmd_l": "cmd_l",  # cmd代替ctrl_l
            "Key.left": "left",
            "Key.f8": "f8",
            "Key.f11": "f11",
            "z": "z",
            "e": "e",
            "Key.up": "up",
            "3": "3",
            "=": "=",
            "w": "w",
            ".": ".",
            "Key.space": "space",
            "n": "n",
            "Key.alt_l": "alt_l",
            "h": "h",
            "Key.scroll_lock": "scroll_lock",
            "Key.f10": "f10",
            "k": "k",
            "Key.home": "home",
            "o": "o",
            "Key.right": "right",
            "`": "`",
            "9": "9",
            "Key.f6": "f6",
            "Key.esc": "esc",
            "Key.cmd_r": "cmd_r",  # cmd代替ctrl_r
            "y": "y",
            "Key.cmd": "cmd",  # cmd
            "Key.delete": "delete",
            "Key.shift": "shift",
            "j": "j",
            "*": "*",
            "Key.f7": "f7",
            "Key.print_screen": "print_screen",
            "/": "/",
            "Key.backspace": "backspace",
            "-": "-",
            "t": "t",
            "f": "f",
            "Key.enter": "enter",
            "Key.f3": "f3",
            "0": "0",
            "4": "4",
            "d": "d",
            "Key.caps_lock": "caps_lock",
            "l": "l",
            "8": "8",
            "Key.f12": "f12",
            "Key.tab": "tab",
            "i": "i",
            "Key.f4": "f4",
            "Key.page_up": "page_up",
            ",": ",",
            "x": "x",
            "Key.shift_r": "shift_r",
            "Key.page_down": "page_down",
            "None": "None",
            "Key.f5": "f5",
            "p": "p",
            "6": "6",
            "1": "1",
            "a": "a",
            "2": "2",
            ";": ";",
            "'": "'",
            "]": "]",
            "c": "c",
            "Key.menu": "menu",
            "q": "q",
            "Key.pause": "pause",
            "v": "v",
            "Key.num_lock": "num_lock",
            "s": "s",
            "b": "b",
            "5": "5",
            "Key.f9": "f9",
            "Key.alt_gr": "alt_gr",
            "Key.f2": "f2",
            "Key.end": "end",
            "Key.down": "down",
            "7": "7",
            "\\": "\\",
            "[": "[",
            "+": "+",

            # 数字键盘部分
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

            # Function keys mapped as usual on macOS
            "<97>": "1",
            "<98>": "2",
            "<99>": "3",
            "<100>": "4",
            "<101>": "5",
            "<102>": "6",
            "<103>": "7",
            "<104>": "8",
            "<105>": "9",
            "<96>": "0",
            "<255>": "Fn",

            # MacOS Ctrl key mappings
            "'\\x01'": "Ctrl+A",  # Ctrl+A
            "'\\x02'": "Ctrl+B",  # Ctrl+B
            "'\\x03'": "Ctrl+C",  # Ctrl+C
            "'\\x04'": "Ctrl+D",  # Ctrl+D
            "'\\x05'": "Ctrl+E",  # Ctrl+E
            "'\\x06'": "Ctrl+F",  # Ctrl+F
            "'\\x07'": "Ctrl+G",  # Ctrl+G
            "'\\x08'": "Ctrl+H",  # Ctrl+H
            "'\\x09'": "Ctrl+I",  # Ctrl+I
            "'\\x0a'": "Ctrl+J",  # Ctrl+J
            "'\\x0b'": "Ctrl+K",  # Ctrl+K
            "'\\x0c'": "Ctrl+L",  # Ctrl+L
            "'\\x0d'": "Ctrl+M",  # Ctrl+M
            "'\\x0e'": "Ctrl+N",  # Ctrl+N
            "'\\x0f'": "Ctrl+O",  # Ctrl+O
            "'\\x10'": "Ctrl+P",  # Ctrl+P
            "'\\x11'": "Ctrl+Q",  # Ctrl+Q
            "'\\x12'": "Ctrl+R",  # Ctrl+R
            "'\\x13'": "Ctrl+S",  # Ctrl+S
            "'\\x14'": "Ctrl+T",  # Ctrl+T
            "'\\x15'": "Ctrl+U",  # Ctrl+U
            "'\\x16'": "Ctrl+V",  # Ctrl+V
            "'\\x17'": "Ctrl+W",  # Ctrl+W
            "'\\x18'": "Ctrl+X",  # Ctrl+X
            "'\\x19'": "Ctrl+Y",  # Ctrl+Y
            "'\\x1a'": "Ctrl+Z"  # Ctrl+Z
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

    def start_recording(self):
        if not self.running:
            self.running = True
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
                print("press")
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
                print("release")
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
            print("[*] press_start_screenshot")
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
        print("key_name: ",end="")
        print(key_name)
        # print(type(key_name))
        try:
            key_name_str = str(key_name).strip()
            print("key_name_str: ", key_name_str)
        # print("known_key_map[key_name_str]", self.known_key_map[key_name_str])
        except:
            return ""
        try:
            if(key_name_str in self.known_key_map):
                print("key_name_str in self.known_key_map:      ", self.known_key_map[key_name_str])
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
            print("[*] scroll_press_start_screenshot")
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
        self.handle_event(event_data, screenshot)

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