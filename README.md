# Wukong Auto Grab - 悟空邀请码自动抢码工具

> **手太慢，抢不到悟空邀请码？**
>
> 钉钉悟空每个整点放出限量邀请码，几秒就被抢光。手动刷网页、复制粘贴、点提交——等你操作完，码早没了。
>
> 这个工具帮你全自动完成：**刷新网页 → OCR 识别邀请码 → 填入悟空 App → 点击提交**，全程不到 2 秒。让手慢的玩家也能体验悟空！

## 工作原理

```
┌─────────────┐    OCR     ┌─────────────┐  AppleScript/  ┌─────────────┐
│  悟空官网    │ ────────→  │  识别邀请码  │ ──PowerShell─→ │  悟空 App    │
│  (Playwright)│           │  (系统自带)  │               │  (自动填入)  │
└──────┬──────┘           └─────────────┘               └─────────────┘
       │ 每0.5秒刷新
       └─── 整点前2分钟自动检查 App 状态
```

**全程自动：**
1. 整点前 2 分钟检查悟空 App 是否就绪
2. 整点开始高频刷新官网（每 0.5 秒）
3. 发现新邀请码 → OCR 识别 → 自动填入 App → 点击"立即体验"
4. 注册成功后自动退出

## 支持平台

| | macOS | Windows |
|---|---|---|
| OCR | Vision 框架 (系统自带) | Windows.Media.Ocr (Win10+ 自带) |
| App 操控 | AppleScript | PowerShell + UIAutomation |
| 额外依赖 | 仅 Playwright | 仅 Playwright |

## 快速开始

### macOS / Linux

```bash
git clone https://github.com/romgX/wukong.git
cd wukong
bash wk.sh
```

### Windows

```
git clone https://github.com/romgX/wukong.git
cd wukong
双击 wk.bat
```

**首次运行会自动：**
- 检查 Python（没有则提示安装）
- 创建虚拟环境
- 安装 Playwright + Chromium

之后直接运行即可。

## 使用前提

1. 已安装 [悟空 App](https://www.dingtalk.com/wukong) 并打开到邀请码输入页面
2. 悟空 App 已登录钉钉账号
3. macOS 需授予终端 "辅助功能" 权限（系统设置 → 隐私与安全 → 辅助功能）

## 配置

编辑 `grab_code.py` 顶部：

```python
POLL_S     = 0.3   # 轮询间隔(秒)
REFRESH_S  = 0.5   # 网页刷新间隔(秒)
HEADLESS   = True  # True=隐藏浏览器 False=显示
```

工作时间（默认 8:00-23:00，非工作时间不轮询）：

```python
WORK_HOUR_START = 8
WORK_HOUR_END   = 23
```

## 文件说明

```
├── wk.sh          # macOS/Linux 启动脚本
├── wk.bat         # Windows 启动脚本
├── grab_code.py   # 核心逻辑
├── invite_img.png # 邀请码示例图片
└── README.md
```

## 原理细节

- 邀请码以**图片**形式展示在官网，不是文本，所以需要 OCR
- macOS 用系统自带的 Vision 框架做中文 OCR，Windows 用 Windows.Media.Ocr
- 通过 AppleScript (macOS) / UIAutomation (Windows) 操控悟空桌面 App
- 浏览器使用持久化上下文，登录态自动保存

## License

MIT
