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

        self.unicode_key_map = {
            "\x01": "Cmd+A",  # Cmd+A 替代 Ctrl+A
            "\x02": "Cmd+B",  # Cmd+B 替代 Ctrl+B
            "\x03": "Cmd+C",  # Cmd+C 替代 Ctrl+C
            "\x04": "Cmd+D",  # Cmd+D 替代 Ctrl+D
            "\x05": "Cmd+E",  # Cmd+E 替代 Ctrl+E
            "\x06": "Cmd+F",  # Cmd+F 替代 Ctrl+F
            "\x07": "Cmd+G",  # Cmd+G 替代 Ctrl+G
            "\x08": "Cmd+H",  # Cmd+H 替代 Ctrl+H
            "\x09": "Cmd+I",  # Cmd+I 替代 Ctrl+I
            "\x0A": "Cmd+J",  # Cmd+J 替代 Ctrl+J
            "\x0B": "Cmd+K",  # Cmd+K 替代 Ctrl+K
            "\x0C": "Cmd+L",  # Cmd+L 替代 Ctrl+L
            "\x0D": "Cmd+M",  # Cmd+M 替代 Ctrl+M
            "\x0E": "Cmd+N",  # Cmd+N 替代 Ctrl+N
            "\x0F": "Cmd+O",  # Cmd+O 替代 Ctrl+O
            "\x10": "Cmd+P",  # Cmd+P 替代 Ctrl+P
            "\x11": "Cmd+Q",  # Cmd+Q 替代 Ctrl+Q
            "\x12": "Cmd+R",  # Cmd+R 替代 Ctrl+R
            "\x13": "Cmd+S",  # Cmd+S 替代 Ctrl+S
            "\x14": "Cmd+T",  # Cmd+T 替代 Ctrl+T
            "\x15": "Cmd+U",  # Cmd+U 替代 Ctrl+U
            "\x16": "Cmd+V",  # Cmd+V 替代 Ctrl+V
            "\x17": "Cmd+W",  # Cmd+W 替代 Ctrl+W
            "\x18": "Cmd+X",  # Cmd+X 替代 Ctrl+X
            "\x19": "Cmd+Y",  # Cmd+Y 替代 Ctrl+Y
            "\x1A": "Cmd+Z",  # Cmd+Z 替代 Ctrl+Z
            "\x1B": "Esc",  # 保持一致
            "\x1C": "Cmd+\\",  # Cmd+\ 替代 Ctrl+\
            "\x1D": "Cmd+]",  # Cmd+] 替代 Ctrl+]
            "\x1E": "Cmd+^",  # Cmd+^ 替代 Ctrl+^
            "\x1F": "Cmd+_",  # Cmd+_ 替代 Ctrl+_
            "\x7F": "Delete",  # macOS 使用 Delete 而非 Del
            # 可以继续根据需要添加更多 Unicode 键
        }

        self.special_key_map = {
            "shift": "Shift",
            "shift_l": "Shift",
            "shift_r": "Shift",
            "ctrl_l": "Cmd",  # Ctrl 左侧变为 Cmd
            "ctrl_r": "Cmd",  # Ctrl 右侧变为 Cmd
            "ctrl": "Cmd",  # Ctrl 键改为 Cmd
            "alt": "Option",  # alt 键变为 Option
            "alt_l": "Option",  # 左侧 alt 键变为 Option
            "alt_gr": "Option",  # alt_gr 可以视作 Option
            "cmd": "Cmd",  # cmd 键保持为 Cmd
            "esc": "Esc",  # esc 键保持为 Esc
            "delete": "Delete",  # delete 键
            "enter": "Return",  # macOS 中通常使用 Return
            "space": "Space",  # 空格键
            "tab": "Tab",  # Tab 键
            "backspace": "Backspace",  # 回退键
            "caps_lock": "CapsLock",  # 大小写锁定键
            "f1": "F1",  # F1 功能键
            "f2": "F2",  # F2 功能键
            "f3": "F3",  # F3 功能键
            "f4": "F4",  # F4 功能键
            "f5": "F5",  # F5 功能键
            "f6": "F6",  # F6 功能键
            "f7": "F7",  # F7 功能键
            "f8": "F8",  # F8 功能键
            "f9": "F9",  # F9 功能键
            "f10": "F10",  # F10 功能键
            "f11": "F11",  # F11 功能键
            "f12": "F12",  # F12 功能键
            "volume_up": "Volume Up",  # 音量增大
            "volume_down": "Volume Down",  # 音量减小
            "mute": "Mute",  # 静音
            "brightness_up": "Brightness Up",  # 增加亮度
            "brightness_down": "Brightness Down",  # 降低亮度
            "home": "Home",  # Home 键
            "end": "End",  # End 键
            "page_up": "Page Up",  # 上一页
            "page_down": "Page Down",  # 下一页
            "insert": "Insert",  # 插入键
            "print_screen": "Print Screen",  # 打印屏幕（通常 macOS 使用截图功能）
            "scroll_lock": "Scroll Lock",  # 滚动锁定键
            "pause": "Pause",  # 暂停键
            "num_lock": "Num Lock",  # 数字锁定键
            "left_arrow": "Left Arrow",  # 左箭头
            "right_arrow": "Right Arrow",  # 右箭头
            "up_arrow": "Up Arrow",  # 上箭头
            "down_arrow": "Down Arrow",  # 下箭头
            "fn": "Fn",  # 功能键 (macOS 上通常与其他功能键组合)
            "command": "Cmd",  # 作为命令键映射
            "option": "Option",  # 作为 option 键映射
            "capslock": "Caps Lock",  # 大小写锁定
            "enter": "Return",  # 回车
            "shift_l": "Shift Left",  # 左 shift
            "shift_r": "Shift Right",  # 右 shift
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


            self.click_press_start_screenshot = pyautogui.screenshot()
            event_data = {
                "timestamp": time.time(),
                "event": "mouse_click",
                "button": f"{button}.press" if pressed else f"{button}.release",
                "position": {"x": x, "y": y},
                "active_app": active_app
            }

            thread_safe_logging('debug', f"捕获到鼠标按下事件: {event_data}")
            self.handle_event(event_data, screenshot=self.click_press_start_screenshot)

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
        """
        将不可打印字符转换为其对应的组合键名称（如 Ctrl+A）。
        如果字符在 string.printable 中，则转为大写；否则，
        若在 unicode_key_map 中，就用该映射，否则用 U+XXXX 表示。
        这里 key_name 可能是整段连续输入，每个字符都需要转换。
        """
        from pynput.keyboard import Key, KeyCode
        converted = []

        print("key_name: ", end="")
        print(key_name)

        # 如果 key_name 是 Key 对象（例如 Key.ctrl_l），我们需要将它转为字符串
        if isinstance(key_name, Key):
            # 先检查是否包含 "Key." 前缀，再进行替换
            if "Key." in str(key_name):
                key_name = str(key_name).replace("Key.", "").lower()
            else:
                key_name = str(key_name).lower()  # 如果没有 "Key." 前缀，则直接转为小写

        # 如果 key_name 是 KeyCode 对象（例如按下的字符）
        elif isinstance(key_name, KeyCode):
            key_name = key_name.char  # 获取按键字符

        # 如果 key_name 是字符串（例如多个连续按键），按空格拆分
        if isinstance(key_name, str):
            keys = key_name.split(' ')  # 处理多个按键字符
        else:
            keys = [key_name]  # 单个按键的情况

        for key in keys:
            if key in self.special_key_map:
                converted_key = self.special_key_map.get(key, key.capitalize())
                converted.append(converted_key)
            elif key in string.printable and not key.isspace():
                converted.append(key)
            elif key in self.unicode_key_map:
                converted.append(self.unicode_key_map[key])
            else:
                converted.append(f"U+{ord(key):04X}")
        return ' '.join(converted)

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