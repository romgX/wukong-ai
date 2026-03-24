#!/usr/bin/env python3
"""
悟空邀请码自动抢码工具 (macOS / Windows 双平台)

用法:
  pip install playwright && playwright install chromium
  python grab_code.py

规则: 每个整点后 0~5 分钟内随机放码
策略: XX:58 检查 App → XX:00~XX:06 高频抢码 → 其余时间待机
      注册成功后自动退出
"""

import asyncio
import subprocess
import platform
import re
import tempfile
import os
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# ── 配置 ─────────────────────────────────────
CODE_URL      = "https://www.dingtalk.com/wukong?from=wukong_yqm_guide"
POLL_S        = 0.3      # 高频轮询间隔(秒)
REFRESH_S     = 0.5      # 高频刷新网页间隔(秒)
HEADLESS      = True
USER_DATA_DIR = os.path.join(os.path.expanduser("~"), ".wukong_browser")
IS_WIN        = platform.system() == "Windows"
# ─────────────────────────────────────────────


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}", flush=True)


# ═══════════════════════════════════════════════
#  平台相关：OCR / App 操控
# ═══════════════════════════════════════════════

if IS_WIN:
    # ── Windows: PowerShell 调用系统自带 OCR + UI 自动化 ──

    def ocr_image(image_path: str) -> str:
        """Windows 10/11 自带 OCR (Windows.Media.Ocr)"""
        ps = f'''
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime]

function Await($WinRtTask, $ResultType) {{
    $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    }} | Select-Object -First 1
    $generic = $asTask.MakeGenericMethod($ResultType)
    $task = $generic.Invoke($null, @($WinRtTask))
    $task.Wait()
    return $task.Result
}}

$path = "{image_path}"
$stream = [System.IO.File]::OpenRead($path)
$raStream = [System.IO.WindowsRuntimeStreamExtensions]::AsRandomAccessStream($stream)
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($raStream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage("zh-Hans-CN")
if ($engine -eq $null) {{ $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }}
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$lines = @()
foreach ($line in $result.Lines) {{ $lines += $line.Text }}
$stream.Close()
Write-Output ($lines -join "|||")
'''
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=10
            )
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""

    def _find_wukong_window():
        """用 PowerShell 查找悟空窗口，返回窗口句柄"""
        ps = '''
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty, "悟空"
)
$win = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
if ($win -eq $null) {
    # 尝试按进程名查找
    $procs = Get-Process | Where-Object { $_.ProcessName -match "Wukong|DingTalk" -and $_.MainWindowHandle -ne 0 }
    foreach ($proc in $procs) {
        $hwnd = $proc.MainWindowHandle
        $cond2 = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NativeWindowHandleProperty, [int]$hwnd
        )
        $win = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond2)
        if ($win -ne $null) { break }
    }
}
if ($win -ne $null) { Write-Output $win.Current.NativeWindowHandle } else { Write-Output "NOT_FOUND" }
'''
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip()

    def check_wukong_app() -> dict:
        ps = '''
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement

# 查找悟空窗口
$procs = Get-Process | Where-Object { $_.ProcessName -match "Wukong|DingTalk" -and $_.MainWindowHandle -ne 0 }
$win = $null
foreach ($proc in $procs) {
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NativeWindowHandleProperty, [int]$proc.MainWindowHandle
    )
    $w = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
    if ($w -ne $null) { $win = $w; break }
}
if ($win -eq $null) { Write-Output "no_process"; exit }

# 找编辑框 (Edit / TextBox)
$editCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Edit
)
$edit = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $editCond)
if ($edit -ne $null) { Write-Output "ready" } else { Write-Output "no_input" }
'''
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, timeout=10)
            out = r.stdout.strip()
        except Exception:
            return {"running": False, "ready": False, "msg": "检测异常"}

        if out == "ready":
            return {"running": True, "ready": True, "msg": "App 就绪，输入框可用"}
        elif out == "no_process":
            return {"running": False, "ready": False, "msg": "悟空 App 未启动"}
        elif out == "no_input":
            return {"running": True, "ready": False, "msg": "未找到邀请码输入框"}
        else:
            return {"running": True, "ready": False, "msg": f"未知状态: {out}"}

    def fill_wukong_app(code: str) -> bool:
        ps = f'''
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
$root = [System.Windows.Automation.AutomationElement]::RootElement

# 查找悟空窗口
$procs = Get-Process | Where-Object {{ $_.ProcessName -match "Wukong|DingTalk" -and $_.MainWindowHandle -ne 0 }}
$win = $null; $hwnd = 0
foreach ($proc in $procs) {{
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NativeWindowHandleProperty, [int]$proc.MainWindowHandle
    )
    $w = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
    if ($w -ne $null) {{ $win = $w; $hwnd = $proc.MainWindowHandle; break }}
}}
if ($win -eq $null) {{ Write-Output "no_window"; exit }}

# 激活窗口
Add-Type @"
using System; using System.Runtime.InteropServices;
public class Win32 {{
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}}
"@
[Win32]::ShowWindow([IntPtr]$hwnd, 9)
[Win32]::SetForegroundWindow([IntPtr]$hwnd)
Start-Sleep -Milliseconds 200

# 找编辑框
$editCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Edit
)
$edit = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $editCond)
if ($edit -eq $null) {{ Write-Output "no_edit"; exit }}

# 填入文字
try {{
    $vp = $edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    $vp.SetValue("{code}")
}} catch {{
    # fallback: 用 SendKeys
    $edit.SetFocus()
    Start-Sleep -Milliseconds 100
    [System.Windows.Forms.SendKeys]::SendWait("{{HOME}}")
    [System.Windows.Forms.SendKeys]::SendWait("+{{END}}")
    [System.Windows.Forms.SendKeys]::SendWait("{code}")
}}
Start-Sleep -Milliseconds 150

# 找按钮 "立即体验"
$btnCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty, "立即体验"
)
$btn = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
if ($btn -eq $null) {{
    # 尝试按 ControlType 找所有按钮
    $btnTypeCond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Button
    )
    $btns = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnTypeCond)
    foreach ($b in $btns) {{
        if ($b.Current.Name -match "立即体验|体验|提交") {{ $btn = $b; break }}
    }}
}}
if ($btn -ne $null) {{
    $ip = $btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $ip.Invoke()
    Write-Output "ok"
}} else {{
    Write-Output "no_button"
}}
'''
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, timeout=10)
            return r.stdout.strip() == "ok"
        except Exception as e:
            log(f"  PowerShell 异常: {e}")
            return False

    def check_register_success() -> bool:
        ps = '''
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$procs = Get-Process | Where-Object { $_.ProcessName -match "Wukong|DingTalk" -and $_.MainWindowHandle -ne 0 }
$win = $null
foreach ($proc in $procs) {
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NativeWindowHandleProperty, [int]$proc.MainWindowHandle
    )
    $w = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
    if ($w -ne $null) { $win = $w; break }
}
if ($win -eq $null) { Write-Output "no_window"; exit }
$editCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Edit
)
$edit = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $editCond)
if ($edit -eq $null) { Write-Output "success" } else { Write-Output "still_input" }
'''
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, timeout=5)
            return r.stdout.strip() == "success"
        except Exception:
            return False

else:
    # ── macOS: AppleScript + Vision OCR ──

    # macOS 必须用系统 Python (有 pyobjc)，venv 里的没有
    _SYS_PYTHON = "/usr/bin/python3"

    def ocr_image(image_path: str) -> str:
        script = f'''
import Cocoa, Vision
url = Cocoa.NSURL.fileURLWithPath_("{image_path}")
req = Vision.VNRecognizeTextRequest.alloc().init()
req.setRecognitionLanguages_(["zh-Hans", "en"])
req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
handler.performRequests_error_([req], None)
parts = []
for obs in (req.results() or []):
    parts.append(obs.topCandidates_(1)[0].string())
print("|||".join(parts))
'''
        try:
            r = subprocess.run([_SYS_PYTHON, "-c", script], capture_output=True, text=True, timeout=5)
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""

    def check_wukong_app() -> dict:
        r = subprocess.run(["pgrep", "-f", "Wukong.app"], capture_output=True)
        if r.returncode != 0:
            return {"running": False, "ready": False, "msg": "悟空 App 未启动"}
        script = '''
        tell application "System Events"
            if not (exists process "DingTalkReal") then return "no_process"
            tell process "DingTalkReal"
                if (count of windows) is 0 then return "no_window"
                try
                    set tf to text field 1 of UI element 1 of scroll area 1 of group 1 of group 1 of window 1
                    return "ready"
                on error
                    try
                        set allText to name of every UI element of window 1
                        return "need_login:" & (allText as text)
                    end try
                    return "no_input"
                end try
            end tell
        end tell
        '''
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        out = r.stdout.strip()
        if out == "ready":
            return {"running": True, "ready": True, "msg": "App 就绪，输入框可用"}
        elif "need_login" in out:
            return {"running": True, "ready": False, "msg": "需要扫码登录!"}
        elif out == "no_window":
            return {"running": True, "ready": False, "msg": "App 没有窗口"}
        elif out == "no_input":
            return {"running": True, "ready": False, "msg": "未找到邀请码输入框"}
        else:
            return {"running": True, "ready": False, "msg": f"未知状态: {out}"}

    def fill_wukong_app(code: str) -> bool:
        script = f'''
        tell application "System Events"
            tell process "DingTalkReal"
                set frontmost to true
                delay 0.1
                set tf to text field 1 of UI element 1 of scroll area 1 of group 1 of group 1 of window 1
                set focused of tf to true
                set value of tf to "{code}"
                delay 0.1
                click button "立即体验" of UI element 1 of scroll area 1 of group 1 of group 1 of window 1
            end tell
        end tell
        '''
        try:
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
            return r.returncode == 0
        except Exception as e:
            log(f"  AppleScript 异常: {e}")
            return False

    def check_register_success() -> bool:
        script = '''
        tell application "System Events"
            tell process "DingTalkReal"
                try
                    set tf to text field 1 of UI element 1 of scroll area 1 of group 1 of group 1 of window 1
                    return "still_input"
                on error
                    return "no_input"
                end try
            end tell
        end tell
        '''
        try:
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            return r.stdout.strip() == "no_input"
        except Exception:
            return False


# ═══════════════════════════════════════════════
#  通用逻辑
# ═══════════════════════════════════════════════

def parse_invite_code(ocr_text: str):
    parts = ocr_text.split("|||")
    full = " ".join(parts)
    code = None
    sold_out = "已领完" in full or "已抢完" in full
    for part in parts:
        if "当前邀请码" in part or "邀请码" in part:
            m = re.search(r'[：:]\s*(.+)', part)
            if m:
                code = m.group(1).strip()
            break
    return code, sold_out


JS_GET_IMG_URL = """
() => {
    const img = document.querySelector('img.wk-hero-invite-img');
    return img ? img.src : null;
}
"""


# 工作时间范围 (整点放码只在这个范围内)
WORK_HOUR_START = 8   # 早8点
WORK_HOUR_END   = 23  # 晚11点


def time_to_next_window():
    """返回距离下一个抢码窗口的秒数。非工作时间直接跳到次日工作时间。"""
    now = datetime.now()

    # 非工作时间: 睡到明天 WORK_HOUR_START:58
    if now.hour < WORK_HOUR_START or now.hour >= WORK_HOUR_END:
        if now.hour >= WORK_HOUR_END:
            target = (now + timedelta(days=1)).replace(
                hour=WORK_HOUR_START, minute=58, second=0, microsecond=0)
        else:
            target = now.replace(
                hour=WORK_HOUR_START, minute=58, second=0, microsecond=0)
        return (target - now).total_seconds()

    # 工作时间且在窗口内 (XX:58~XX:06)
    if now.minute >= 58 or now.minute < 6:
        return 0

    # 工作时间，等到 XX:58
    target = now.replace(minute=58, second=0, microsecond=0)
    return max(0, (target - now).total_seconds())


async def grab_loop(page, tmp_img):
    """高频抢码循环，返回 True 表示注册成功"""
    last_code = None
    n = 0
    last_refresh = asyncio.get_event_loop().time()

    while True:
        n += 1
        now_t = asyncio.get_event_loop().time()
        now_dt = datetime.now()

        if now_dt.minute >= 6 and now_dt.minute < 58:
            log(f"本轮抢码结束 (已过 {now_dt.strftime('%H')}:06)")
            return False

        if now_t - last_refresh > REFRESH_S:
            try:
                await page.reload(wait_until="domcontentloaded")
                await asyncio.sleep(0.3)
                try:
                    skip = page.locator("text=跳过动画")
                    if await skip.is_visible(timeout=500):
                        await skip.click()
                        await asyncio.sleep(0.5)
                except Exception:
                    pass
                last_refresh = asyncio.get_event_loop().time()
            except Exception:
                pass

        try:
            img_url = await page.evaluate(JS_GET_IMG_URL)
            if not img_url:
                if n % 20 == 1:
                    log(f"未找到邀请码图片... (#{n})")
                await asyncio.sleep(POLL_S)
                continue

            fetch_url = img_url + ("&" if "?" in img_url else "?") + f"_t={n}"
            resp = await page.evaluate(f'''
                async () => {{
                    const r = await fetch("{fetch_url}");
                    const blob = await r.blob();
                    const buf = await blob.arrayBuffer();
                    return Array.from(new Uint8Array(buf));
                }}
            ''')
            with open(tmp_img, "wb") as f:
                f.write(bytes(resp))

            ocr_result = ocr_image(tmp_img)
            code, sold_out = parse_invite_code(ocr_result)

            if code and not sold_out:
                log(f">>> 发现可用邀请码: {code}")
                ok = fill_wukong_app(code)
                log(f"{'提交成功!' if ok else '提交失败!'}")
                last_code = code
                if ok:
                    await asyncio.sleep(2)
                    if check_register_success():
                        log("注册成功! 自动退出")
                        return True
                    log("输入框仍在，可能未成功，继续重试...")
                await asyncio.sleep(0.5)
            elif code and sold_out:
                if code != last_code:
                    log(f"[{code}] 已领完")
                    last_code = code
                elif n % 20 == 1:
                    log(f"[{code}] 仍已领完... (#{n})")
            else:
                if n % 20 == 1:
                    log(f"OCR 未识别到邀请码 (#{n})")

        except Exception as e:
            if n % 20 == 1:
                log(f"异常: {e}")

        await asyncio.sleep(POLL_S)


async def main():
    tmp_img = os.path.join(tempfile.gettempdir(), "wukong_invite.png")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            USER_DATA_DIR, headless=HEADLESS,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        log(f"平台: {platform.system()}")
        log("打开邀请码页面...")
        await page.goto(CODE_URL, wait_until="networkidle")
        await asyncio.sleep(2)
        try:
            await page.locator("text=跳过动画").click(timeout=5000)
            await asyncio.sleep(1)
        except Exception:
            pass
        log("页面就绪")

        while True:
            wait_s = time_to_next_window()

            if wait_s > 0:
                wake = datetime.now() + timedelta(seconds=wait_s)
                log(f"待机中... 下次抢码窗口: {wake.strftime('%H:%M:%S')} (等待 {int(wait_s)}s)")
                await asyncio.sleep(wait_s)

            # 整点前2分钟检查 App
            now = datetime.now()
            if now.minute >= 58:
                log("=== 整点前检查 ===")
                status = check_wukong_app()
                if status["ready"]:
                    log(f"App 状态: {status['msg']}")
                else:
                    log(f"⚠️  {status['msg']}")
                    log("请立即处理!")

                target = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                wait = (target - datetime.now()).total_seconds()
                if wait > 0:
                    log(f"距离整点还有 {int(wait)}s")
                    await asyncio.sleep(wait)

            status = check_wukong_app()
            if not status["ready"]:
                log(f"⚠️  App 未就绪: {status['msg']}，但仍尝试抢码...")

            log("=== 开始抢码! ===")
            try:
                await page.reload(wait_until="domcontentloaded")
                await asyncio.sleep(0.5)
                try:
                    skip = page.locator("text=跳过动画")
                    if await skip.is_visible(timeout=1000):
                        await skip.click()
                        await asyncio.sleep(0.5)
                except Exception:
                    pass
            except Exception:
                pass

            success = await grab_loop(page, tmp_img)

            if success:
                log("=== 注册成功，程序退出 ===")
                await context.close()
                return

            log("=== 本轮结束，等待下一轮 ===")


if __name__ == "__main__":
    print("=" * 50)
    print("  悟空邀请码自动抢码工具 (macOS / Windows)")
    print("  整点前2分钟自动检查 App，整点开始抢码")
    print("  注册成功后自动退出")
    print("  Ctrl+C 停止")
    print("=" * 50)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("已停止")
