# action_recorder_thread.py

from PyQt5 import QtCore
from action_recorder import ActionRecorder
from logger import thread_safe_logging

class ActionRecorderThread(QtCore.QThread):
    action_recorded = QtCore.pyqtSignal(str)

    def __init__(self, log_file='log/user_actions.log', save_path='screenshots'):
        super().__init__()
        self.recorder = ActionRecorder(log_file, save_path)
        self.recorder.action_recorded.connect(self.action_recorded.emit)

    def run(self):
        self.recorder.start_recording()
        self.exec_()

    def stop(self):
        self.recorder.stop_recording()
        self.quit()
        self.wait()
        thread_safe_logging('info', "ActionRecorderThread 已成功停止。")
        print("ActionRecorderThread 已成功停止。")