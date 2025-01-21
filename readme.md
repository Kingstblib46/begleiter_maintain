```markdown
# 更新日志

以下是项目 **begleiter** 的更新日志，记录了所有重大更改、修复和改进。

## [1.1.0] - 2025-01-15

### 修复

- **截图保存路径**：修正截图保存目录，从 `/src/log/screenshots` 更改为 `/src/screenshots`，确保截图保存在正确的位置。
  
- **截图上显示操作信息**：确保在截图上正确显示用户操作信息（如鼠标点击、滚动和键盘按键）。使用默认字体，并在字体加载和文本绘制阶段添加了 `print` 语句以便调试。

- **错误修复**：
  - 解决了 `unsupported operand type(s) for /: 'PngImageFile' and 'int'` 错误，确保在算术运算中操作数类型正确。
  - 修复了 `name 'datetime' is not defined` 错误，确保在所有需要的地方正确导入和引用 `datetime` 模块。

### 改进

- **移除定时截屏功能**：删除了每隔20秒进行一次截屏的旧规则，仅在用户操作时进行截屏。

- **增强日志记录与调试**：在字体加载和文本绘制阶段添加了 `print` 语句，便于在终端追踪执行情况，确保截图上正确显示操作信息。

- **事件处理优化**：改进了鼠标点击、滚动和键盘按下事件的处理，确保每个事件都能被准确记录并在截图上注释相关信息。

### 新增

- **调试输出**：在关键步骤添加了 `print` 语句，用于在终端输出调试信息，帮助开发人员确认代码执行情况。

## [1.0.1] - 2025-01-14

### 初始版本

- 发布了用户操作记录器的初始版本，能够捕捉鼠标点击、滚动事件和键盘按键，并生成带有相关操作信息的截图。

## 项目结构

```
begleiter/
├── src/
│   ├── action_recorder.py
│   ├── action_recorder_thread.py
│   ├── config.py
│   ├── logger.py
│   ├── permission.py
│   ├── storage.py
│   ├── ui.py
│   └── main.py
├── screenshots/  # 截图将保存到这里
└── log/
    └── app.log
```

## 安装与配置

确保已安装所有必要的依赖库，特别是在 macOS 上：

```bash
pip install pynput PyQt5 pyautogui pillow psutil
```

### 权限设置

在 macOS 上，应用程序需要获得辅助功能权限才能监听键盘和鼠标事件，以及截屏。请按照以下步骤进行设置：

1. 打开 **系统偏好设置**。
2. 选择 **安全性与隐私**。
3. 在左侧栏选择 **隐私**。
4. 在右侧列表中，找到 **辅助功能** 和 **截屏**。
5. 点击锁定图标并输入密码进行更改。
6. 点击 **+** 按钮，添加您的 Python 解释器（例如 `/usr/bin/python3`）或您使用的 IDE（如 PyCharm）。

## 运行

确保所有文件保存并正确配置后，您可以运行主程序：

```bash
/opt/anaconda3/envs/development/bin/python3.12 /Users/hiranokaoru/PycharmProjects/begleiter/src/main.py
```

## 调试与验证

### 检查日志

在应用程序运行时，监控 `log/app.log` 以确保没有新的错误出现，尤其是：

- **截图中是否有操作信息打印**：如鼠标位置、滚动增量、按键名称等。
- **事件是否被正确记录**：包括鼠标点击、滚动和键盘按下事件。
- **错误日志**：确保没有出现之前的截屏错误或新的错误。

### 测试操作记录

1. **鼠标点击和滚动**：
   - 在不同位置点击和滚动，检查 `/src/screenshots` 目录下是否生成了带有星形标记和文本信息的截图。
   - 查看终端输出，确认 `print` 语句是否显示正确的调试信息。
   - 检查 `app.log` 文件，确认是否记录了对应的 `mouse_click` 和 `mouse_scroll` 事件。

2. **键盘按键**：
   - 按下不同的键，尤其是可打印和不可打印的按键，检查截图是否显示正确的按键信息。
   - 查看终端输出，确认 `print` 语句是否显示正确的按键信息。
   - 检查 `app.log` 文件，确认是否记录了对应的 `key_press` 事件。

3. **日志检查**：
   - 确保没有出现新的错误日志。
   - 确保所有截图都包含相关的操作信息。

### 终端输出示例

```plaintext
用户操作记录器已启动。
开启事件监听器。
捕获到鼠标点击事件: {'timestamp': 1736875732.6328452, 'event': 'mouse_click', 'button': 'Button.left', 'position': {'x': 1448.4140625, 'y': 850.96484375}, 'active_app': 'PyCharm'}
绘制文本信息到截图: /Users/hiranokaoru/PycharmProjects/begleiter/src/screenshots/screenshot_2025-01-15_01-28-53_016464.png
在 (1448.4140625, 850.96484375) 绘制星形标记。
绘制鼠标信息文本的位置: (700.0, 550.0)
已保存截图: /Users/hiranokaoru/PycharmProjects/begleiter/src/screenshots/screenshot_2025-01-15_01-28-53_016464.png
截图保存路径: /Users/hiranokaoru/PycharmProjects/begleiter/src/screenshots/screenshot_2025-01-15_01-28-53_016464.png
记录事件并保存截图: {'timestamp': 1736875732.6328452, 'event': 'mouse_click', 'button': 'Button.left', 'position': {'x': 1448.4140625, 'y': 850.96484375}, 'active_app': 'PyCharm', 'screenshot': '/Users/hiranokaoru/PycharmProjects/begleiter/src/screenshots/screenshot_2025-01-15_01-28-53_016464.png'}
...
```

### 验证截图信息显示

确保截图中显示了以下信息：

- **鼠标点击**：星形标记及鼠标位置和百分比信息。
- **鼠标滚动**：滚动增量信息。
- **键盘按键**：按键名称信息。

## 贡献

欢迎贡献您的力量！请提交 issues 或 pull requests 来反馈问题或建议。

## 许可证

本项目采用 MIT 许可证。详情请参阅 `LICENSE` 文件。
```
打包命令：pyinstaller --onefile --windowed --add-data "src/log:log" --add-data "src/resources:resources" src/main.py

#!/bin/bash
# 清理旧文件
rm -rf build dist *.spec

# 执行打包命令
pyinstaller --clean \
  --name "Begleiter" \
  --windowed \
  --onefile \
  --noconfirm \
  --icon "src/resources/cursor.png" \
  --add-data "src/resources:resources" \
  --add-data "src/log:log" \
  --add-data "src/config.json:." \
  --hidden-import "PIL._tkinter_finder" \
  --collect-all "pynput" \
  --collect-all "Crypto" \
  --target-arch arm64 \
  --osx-bundle-identifier "com.begleiter.app" \
  --distpath "./dist" \
  --workpath "./build" \
  --specpath "." \
  src/main.py