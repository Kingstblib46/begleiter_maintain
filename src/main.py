import sys
from PyQt5 import QtWidgets
from ui import MainWindow
from logger import setup_logging, thread_safe_logging
from config import Config

def main():
    # 设置日志
    setup_logging()
    thread_safe_logging('info', "日志系统已初始化。")

    # 加载配置
    config = Config.load_config()

    # 初始化并启动主窗口
    app = QtWidgets.QApplication(sys.argv)

    # 安装全局异常钩子
    def my_exception_hook(exctype, value, traceback_obj):
        thread_safe_logging('error', f"未经处理的异常: {value}")
        sys.__excepthook__(exctype, value, traceback_obj)
    
    sys.excepthook = my_exception_hook

    window = MainWindow(config)
    window.show()
    try:
        sys.exit(app.exec_())
    except SystemExit:
        thread_safe_logging('info', "应用程序已正常退出。")
    except Exception as e:
        thread_safe_logging('error', f"应用程序异常退出: {e}")

if __name__ == "__main__":
    main()