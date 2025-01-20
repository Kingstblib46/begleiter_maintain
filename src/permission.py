from PyQt5.QtWidgets import QMessageBox
from logger import thread_safe_logging
import pyautogui

def check_permission():
    """
    检查应用是否具有屏幕录制权限。
    """
    try:
        from AppKit import NSWorkspace
        options = NSWorkspace.sharedWorkspace().runningApplications()
        for app in options:
            if app.localizedName() == 'Python':
                # 检查权限
                # 这里需要更复杂的权限检查，简化处理返回 False
                return False
        return False
    except ImportError:
        thread_safe_logging('error', "AppKit 库不可用。")
        return False

def request_permission(parent=None):
    """
    在 macOS 上，权限通常在尝试执行操作时请求。
    这里尝试截屏，如果失败，则提示用户授权。
    """
    try:
        screenshot = pyautogui.screenshot()
        screenshot.close()
        thread_safe_logging('info', "截屏权限已授予。")
        return True
    except Exception as e:
        thread_safe_logging('error', f"截屏权限未授予: {e}")
        if parent:
            QMessageBox.warning(parent, '权限不足', '无法获取截屏权限，请手动授权。')
        return False