import sys
import os

def app_path():
    """
    返回应用程序的基础路径。
    如果是打包后的应用程序（如使用 PyInstaller），则返回可执行文件的目录。
    否则，返回脚本所在的目录。
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))