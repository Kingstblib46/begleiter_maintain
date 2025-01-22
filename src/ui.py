from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from permission import request_permission
from storage import StorageManager
from logger import thread_safe_logging
from action_recorder_thread import ActionRecorderThread
import pyautogui
import os
import sys
from datetime import datetime


class ProcessSessionThread(QThread):
    error_occurred = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, storage_manager):
        super().__init__()
        self.storage_manager = storage_manager

    def run(self):
        try:
            self.storage_manager.process_session()
            thread_safe_logging('info', "会话处理完成，准备退出。")
            self.finished_signal.emit()
        except Exception as e:
            thread_safe_logging('error', f"会话处理过程中出错: {e}")
            self.error_occurred.emit(f"会话处理出错: {e}")


class MainWindow(QtWidgets.QWidget):
    error_signal = pyqtSignal(str)
    quit_signal = pyqtSignal()

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.storage_manager = StorageManager(config.get('save_path', 'screenshots'))
        self.action_recorder_thread = None
        self.process_thread = None
        self.is_processing = False
        self.should_quit = False
        
        # 设置窗口属性
        self.setWindowTitle('熊猫实习生')
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources',
                                 'icon.icns' if sys.platform == 'darwin' else 'icon.ico')
        self.setWindowIcon(QtGui.QIcon(icon_path))
        self.setFixedSize(400, 300)
        
        # 初始化UI和动作记录器
        self.init_ui()
        self.init_action_recorder()
        
        # 连接信号
        self.error_signal.connect(self.show_error)
        self.quit_signal.connect(QtWidgets.QApplication.quit)
        
        # 初始化定时器
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.capture_screenshot)
        self.storage_manager.app_timer = self.timer

    def init_action_recorder(self):
        if self.config.get('record_user_actions', True):
            self.action_recorder_thread = ActionRecorderThread(
                log_file=self.config.get('user_actions_log', 'log/user_actions.log')
            )
            self.action_recorder_thread.action_recorded.connect(self.handle_action_recorded)
            self.action_recorder_thread.start()

    def handle_action_recorded(self, action):
        thread_safe_logging('debug', f"接收到用户操作: {action}")

    def init_ui(self):
        self.layout = QtWidgets.QVBoxLayout()

        # 提示标签
        self.label = QtWidgets.QLabel('是否允许程序自动截取屏幕截图并保存？')
        self.label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.label)

        # 按钮布局
        self.button_layout = QtWidgets.QHBoxLayout()

        # "允许"按钮
        self.accept_btn = QtWidgets.QPushButton('允许')
        self.accept_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px;")
        self.accept_btn.clicked.connect(self.on_accept)
        self.button_layout.addWidget(self.accept_btn)

        # "拒绝"按钮
        self.decline_btn = QtWidgets.QPushButton('拒绝')
        self.decline_btn.setStyleSheet("background-color: #f44336; color: white; padding: 10px;")
        self.decline_btn.clicked.connect(self.on_decline)
        self.button_layout.addWidget(self.decline_btn)

        self.layout.addLayout(self.button_layout)

        # 创建"停止记录并关闭"按钮，但初始时隐藏
        self.stop_close_btn = QtWidgets.QPushButton('停止记录并关闭')
        self.stop_close_btn.setStyleSheet("background-color: #555555; color: white; padding: 10px;")
        self.stop_close_btn.clicked.connect(self.on_stop_and_close)
        self.layout.addWidget(self.stop_close_btn)
        self.stop_close_btn.hide()  # 初始隐藏

        self.setLayout(self.layout)
       
    def on_accept(self):
        thread_safe_logging('info', "用户选择允许截屏")
        if request_permission(parent=self):
            # 启动会话并创建文件夹
            if self.storage_manager.start_session():
                QtWidgets.QMessageBox.information(
                    self, '启动',
                    f"程序已启动，将自动截取屏幕，并记录用户操作。"
                )
                interval = self.config.get('screenshot_interval', 20)
                self.timer.start(interval * 1000)  # 毫秒
                thread_safe_logging('info', f"启动截屏定时器，每{interval}秒进行一次截屏。")
                self.show_stop_close_button()
        else:
            self.on_decline()

    def on_decline(self):
        thread_safe_logging('info', "用户选择拒绝截屏")
        QtWidgets.QMessageBox.information(self, '退出', '程序已退出。')
        QtWidgets.QApplication.quit()

    def show_stop_close_button(self):
        # 隐藏提示标签和接受、拒绝按钮
        self.label.hide()
        self.accept_btn.hide()
        self.decline_btn.hide()
        # 显示停止记录并关闭按钮
        self.stop_close_btn.show()

    def on_stop_and_close(self):
        if self.is_processing:
            return
        
        self.is_processing = True
        self.should_quit = True
        thread_safe_logging('info', "用户点击'停止记录并关闭'按钮")
        
        # 停止定时器
        if self.timer.isActive():
            self.timer.stop()
            thread_safe_logging('info', "定时器已停止")

        # 禁用按钮防止重复点击
        self.stop_close_btn.setEnabled(False)
        
        # 停止动作记录线程
        if self.action_recorder_thread:
            thread_safe_logging('info', "准备停止动作记录线程")
            self.action_recorder_thread.stop()
            thread_safe_logging('info', "动作记录线程已停止")

        # 处理会话并退出
        thread_safe_logging('info', "准备启动处理会话线程")
        self.process_thread = ProcessSessionThread(self.storage_manager)
        self.process_thread.error_occurred.connect(self.show_error)
        self.process_thread.finished_signal.connect(self.final_quit)
        self.process_thread.start()

    def capture_screenshot(self):
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            screenshot = pyautogui.screenshot()
            filename = f"screenshot_{timestamp}.png"
            self.storage_manager.save_screenshot(screenshot=screenshot, filename=filename)
            thread_safe_logging('info', f"已保存截图: {filename}")
        except Exception as e:
            thread_safe_logging('error', f"截屏失败: {e}")

    def closeEvent(self, event):
        thread_safe_logging('info', "触发窗口关闭事件")
        if hasattr(self, 'stop_close_btn') and self.stop_close_btn.isVisible():
            # 如果正在记录，则调用停止记录并关闭
            self.on_stop_and_close()
            event.ignore()  # 忽略关闭事件，等待处理完成后自动退出
        else:
            # 如果还没开始记录，直接退出
            QtWidgets.QApplication.quit()

    def show_error(self, message):
        QtWidgets.QMessageBox.critical(self, '错误', message)
        # Re-enable stop and close button in case of error
        self.stop_close_btn.setEnabled(True)

    def final_quit(self):
        thread_safe_logging('info', "会话处理完成，准备退出。")
        QtWidgets.QApplication.quit()