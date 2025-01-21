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
        self.current_action = ""
        self.key_buffer = []  # 新增：用于存储按键的缓冲区
        self.key_process_interval = 0.1  # 每100ms处理一次按键
        self.last_process_time = time.time()
        self.key_lock = threading.Lock()  # 专门用于保护按键缓冲区的锁
        self.max_action_length = 100    # 单次动作最大长度，可自行调整

        self.mouse_listener = mouse.Listener(on_click=self.on_click, on_scroll=self.on_scroll)
        self.keyboard_listener = keyboard.Listener(on_press=self.on_press)

        # 启动一个线程来监控滚动超时
        self.scroll_thread = threading.Thread(target=self.monitor_scroll_timeout, daemon=True)
        self.scroll_thread.start()

        # 启动按键处理线程
        self.key_process_thread = threading.Thread(target=self._process_key_buffer, daemon=True)
        self.key_process_thread.start()

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
            self.finalize_scroll_accumulation()

            # 处理剩余的按键缓冲区
            with self.key_lock:
                if self.key_buffer:
                    keys_to_process = self.key_buffer.copy()
                    self.key_buffer.clear()
                    
                    if keys_to_process:
                        # 合并剩余的按键
                        key_sequence = " ".join(k[0] for k in keys_to_process)
                        mouse_x, mouse_y = pyautogui.position()
                        active_app = self.get_active_app()
                        event_data = {
                            "timestamp": keys_to_process[-1][1],
                            "event": "key_press",
                            "key": key_sequence,
                            "position": {"x": mouse_x, "y": mouse_y},
                            "active_app": active_app
                        }
                        self.handle_event(event_data)

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
        if self.running:
            # 若有未完成的滚动事件，先结算
            self.finalize_scroll_accumulation()

            active_app = self.get_active_app()

            # 根据pressed状态创建相应的事件
            event_data = {
                "timestamp": time.time(),
                "event": "mouse_click",
                "button": f"{button}.press" if pressed else f"{button}.release",
                "position": {"x": x, "y": y},
                "active_app": active_app
            }
            
            thread_safe_logging('debug', f"捕获到鼠标{'按下' if pressed else '松开'}事件: {event_data}")
            self.handle_event(event_data)

    def on_scroll(self, x, y, dx, dy):
        if self.running:
            self.handle_vertical_scroll(x, y, dy)

    def on_press(self, key):
        """键盘按下时，将按键加入缓冲区"""
        if not self.running:
            return

        try:
            # 若有未完成的滚动事件，先结算
            self.finalize_scroll_accumulation()

            key_pressed = self._get_key_name(key)
            
            # 将按键添加到缓冲区
            with self.key_lock:
                self.key_buffer.append((key_pressed, time.time()))

        except Exception as e:
            thread_safe_logging('error', f"处理键盘事件时出错: {e}")

    def _get_key_name(self, key):
        """将 pynput 的 key 转成可读字符串。"""
        try:
            if hasattr(key, 'char') and key.char is not None:
                # 普通字符
                return key.char
            else:
                # 特殊键
                return f"Key.{key.name}"
        except AttributeError:
            return str(key)

    def _process_key_buffer(self):
        """持续处理按键缓冲区的线程"""
        while True:
            try:
                if not self.running:
                    time.sleep(0.1)
                    continue

                current_time = time.time()
                
                # 如果距离上次处理时间不足间隔时间，等待
                if current_time - self.last_process_time < self.key_process_interval:
                    time.sleep(0.01)  # 短暂休眠以避免CPU过度使用
                    continue

                with self.key_lock:
                    # 没有按键需要处理
                    if not self.key_buffer:
                        time.sleep(0.01)
                        continue

                    # 获取所有待处理的按键
                    keys_to_process = self.key_buffer.copy()
                    self.key_buffer.clear()

                # 处理按键
                if keys_to_process:
                    # 按时间顺序排序按键
                    keys_to_process.sort(key=lambda x: x[1])
                    
                    # 合并按键
                    key_sequence = " ".join(k[0] for k in keys_to_process)
                    
                    # 创建事件
                    mouse_x, mouse_y = pyautogui.position()
                    active_app = self.get_active_app()
                    event_data = {
                        "timestamp": keys_to_process[-1][1],  # 使用最后一个按键的时间
                        "event": "key_press",
                        "key": key_sequence,
                        "position": {"x": mouse_x, "y": mouse_y},
                        "active_app": active_app
                    }
                    
                    # 处理事件
                    self.handle_event(event_data)

                self.last_process_time = current_time

            except Exception as e:
                thread_safe_logging('error', f"处理按键缓冲区时出错: {e}")
                time.sleep(0.1)  # 发生错误时短暂暂停

    def handle_vertical_scroll(self, x, y, dy):
        """累加垂直滚动事件。若方向改变或超时则生成一次 mouse_scroll 事件并截图。"""
        now = time.time()
        old_dir = self.scroll_accumulator["direction"]
        old_time = self.scroll_accumulator["last_time"]

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
            time_diff = now - old_time
            if new_dir != old_dir or time_diff > self.scroll_timeout:
                self.finalize_scroll_accumulation()
                self.scroll_accumulator["direction"] = new_dir
                self.scroll_accumulator["acc_dy"] = dy
                self.scroll_accumulator["x"] = x
                self.scroll_accumulator["y"] = y
                self.scroll_accumulator["last_time"] = now
            else:
                self.scroll_accumulator["acc_dy"] += dy
                self.scroll_accumulator["x"] = x
                self.scroll_accumulator["y"] = y
                self.scroll_accumulator["last_time"] = now

    def finalize_scroll_accumulation(self):
        """结算滚动累积，生成一次 mouse_scroll 事件并截图。"""
        direction = self.scroll_accumulator["direction"]
        if direction is None:
            return

        acc_dy = self.scroll_accumulator["acc_dy"]
        x = self.scroll_accumulator["x"]
        y = self.scroll_accumulator["y"]

        active_app = self.get_active_app()
        event_data = {
            "timestamp": time.time(),
            "event": "mouse_scroll",
            "delta_x": 0,
            "delta_y": acc_dy,
            "position": {"x": x, "y": y},
            "active_app": active_app
        }
        self.handle_event(event_data)
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

    def handle_event(self, event):
        """对录制的事件进行截图并保存，再写入数据队列。"""
        try:
            action_type = event.get('event')  # 获取事件类型

            if action_type in ['mouse_click', 'mouse_scroll', 'key_press']:
                # 创建 action_content 字典，用于存储详细事件内容
                action_content = {}

                if action_type in ['mouse_click', 'mouse_scroll']:
                    screen_size = pyautogui.size()
                    screen_x, screen_y = screen_size
                    x = int(event['position']['x'])
                    y = screen_y - int(event['position']['y'])
                    button = event.get('button')

                    if action_type == 'mouse_scroll':
                        # 获取水平和垂直滚动量
                        dx = event.get('delta_x', 0)  # 水平方向的滚动量
                        dy = event.get('delta_y', 0)  # 垂直方向的滚动量
                        screenshot_path = self.storage_manager.save_screenshot(x=x, y=y, dx=dx, dy=dy)
                        action_content = {
                            "position": {
                                "x": x,
                                "y": y,
                                "screen_width": pyautogui.size().width,
                                "screen_height": pyautogui.size().height
                            },
                            "button": None,
                            "delta": {
                                "dx": dx,
                                "dy": dy
                            },
                            "key": None  # 对于鼠标事件，key 设置为 None
                        }
                    else:  # mouse_click
                        screenshot_path = self.storage_manager.save_screenshot(x=x, y=y, button=button)
                        action_content = {
                            "position": {
                                "x": x,
                                "y": y,
                                "screen_width": pyautogui.size().width,
                                "screen_height": pyautogui.size().height
                            },
                            "button": button,
                            "delta": None,  # 对于非滚动事件，delta 设置为 None
                            "key": None  # 对于鼠标事件，key 设置为 None
                        }

                elif action_type == 'key_press':
                    key_name = event['key']
                    screenshot_path = self.storage_manager.save_screenshot(key_name=key_name)

                    # 获取鼠标位置
                    mouse_x, mouse_y = pyautogui.position()

                    action_content = {
                        "position": {
                            "x": int(mouse_x),
                            "y": int(mouse_y),
                            "screen_width": pyautogui.size().width,
                            "screen_height": pyautogui.size().height
                        },  # 记录鼠标位置
                        "button": None,
                        "delta": None,  # 对于键盘事件，delta 设置为 None
                        "key": key_name  # 键盘按键
                    }

                # 获取鼠标位置
                mouse_x, mouse_y = pyautogui.position()

                # 将 position 字段处理并移除
                if 'position' in event and event['position'] is not None:
                    screen_size = pyautogui.size()
                    screen_x, screen_y = screen_size
                    x = event['position']['x']
                    y = screen_y - event['position']['y']

                    # 设置 mouse_position 字段
                    mouse_position = {
                        "x": int(x),
                        "y": int(y),
                        "screen_width": pyautogui.size().width,
                        "screen_height": pyautogui.size().height
                    }

                    del event['position']  # 移除原有的 position 字段
                else:
                    mouse_position = {
                        "x": None,
                        "y": None,
                        "screen_width": pyautogui.size().width,
                        "screen_height": pyautogui.size().height
                    }

                # 组装最终的事件结构
                new_event = {
                    "timestamp": event.get("timestamp", time.time()),  # 保存时间戳
                    "action_type": action_type,  # 保存事件类型
                    "action_content": action_content,  # 保存事件内容
                    "active_app": event.get("active_app", "未知应用"),  # 活动应用
                    "screenshots_path": self.get_relative_screenshot_path(screenshot_path),  # 独立保存截图路径
                    "mouse_position": mouse_position  # 独立保存鼠标位置
                }

                # 先将事件添加到数据列表中
                with self.lock:
                    self.data.append(new_event)

                # 实时保存事件到 JSONL 文件
                filename = self.storage_manager.getLogPath()
                filename = os.path.join(filename, self.log_filename)
                with open(filename, 'a', encoding='utf-8') as f:
                    json.dump(new_event, f, ensure_ascii=False)
                    f.write('\n')  # 每条事件一行

                # Emit the event
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