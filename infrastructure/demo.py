from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pyautogui as pg
import pyperclip

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.logging.logger import log_error, log_info

pg.FAILSAFE = True
pg.PAUSE = 0.05

_TRACE_ID = f"db-to-xlsx-img-{os.getpid()}"

# ============================================================
# 步骤模板（把下面的 PLACEHOLDER 替换为实际截图路径）
# ============================================================
# 每个步骤的 "image" 字段指向参考截图文件（相对于 images/ 目录）。
#
# 准备工作：
#   1. 打开吉客云，进入导出流程的起始页面
#   2. 用截图工具截取每个要点击的按钮 / 输入框，保存到 infrastructure/images/
#   3. 截图尽量小，只包含目标控件本身的特征部分
#   4. 填入下面的 image 字段
#
# confidence 是可选参数（0.0~1.0），需要 pip install opencv-python
# ============================================================

STEPS: list[dict] = [
    {
        "action": "click",
        "image": "1.png",
        "confidence": 0.9,
        "delay": 3,
        "comment": "步骤1：点击第1个Hyperlink（超链接）",
    },
    {
        "action": "click",
        "image": "2.png",
        "confidence": 0.9,
        "delay": 2,
        "comment": "步骤2：点击 xxx",
    },
    {
        "action": "type",
        "text": "待发货-已递交",
        "delay": 2,
        "comment": "步骤3：向当前焦点输入文本",
    },
    {
        "action": "click",
        "image": "3.png",
        "confidence": 0.9,
        "delay": 3,
        "comment": "步骤4：点击确认/查询",
    },
    {
        "action": "click",
        "image": "4.png",
        "confidence": 0.9,
        "delay": 3,
        "comment": "步骤5：点击 xxx",
    },
    {
        "action": "click",
        "image": "5.png",
        "confidence": 0.9,
        "delay": 1,
        "comment": "步骤6：点击 xxx",
    },
    {
        "action": "hover",
        "image": "6.png",
        "confidence": 0.9,
        "delay": 1,
        "comment": "步骤7：悬停打开子菜单",
    },
    {
        "action": "click",
        "image": "7.png",
        "confidence": 0.9,
        "delay": 9,
        "comment": "步骤8：点击子菜单项（导出需等待较久）",
    },
    {
        "action": "click",
        "image": "8.png",
        "confidence": 0.9,
        "delay": 1,
        "comment": "步骤9：点击保存/确认",
    },
    {
        "action": "click",
        "image": "9.png",
        "confidence": 0.9,
        "delay": 1,
        "comment": "步骤10：点击文件名输入框",
    },
    {
        "action": "click",
        "image": "10.png",
        "confidence": 0.9,
        "delay": 1,
        "comment": "步骤11：点击保存",
    },
]

# 参考截图存放目录
_IMAGES_DIR = Path(__file__).resolve().parent / "images"


# ============================================================
# 窗口查找 & 激活
# ============================================================


def _find_window(
    title_substring: str = "",
    *,
    class_name: str = "",
) -> int | None:
    """查找顶级窗口句柄，支持按标题子串（pygetwindow）或 ClassName（UIA）。"""
    # 优先用 pygetwindow 按标题查找
    if title_substring:
        import pygetwindow as gw

        windows = gw.getWindowsWithTitle(title_substring)
        if windows:
            hwnd = windows[0]._hWnd
            log_info(
                "window_found",
                {
                    "trace_id": _TRACE_ID,
                    "title": windows[0].title,
                    "hwnd": hwnd,
                },
            )
            return hwnd

    # 回落 UIA 按 ClassName 查找
    if class_name:
        import uiautomation

        desktop = uiautomation.GetRootControl()
        for child in desktop.GetChildren():
            if child.ClassName == class_name:
                hwnd = child.NativeWindowHandle
                log_info(
                    "window_found",
                    {
                        "trace_id": _TRACE_ID,
                        "name": child.Name,
                        "class_name": child.ClassName,
                        "hwnd": hwnd,
                    },
                )
                return hwnd

    log_error(
        "window_not_found",
        {
            "trace_id": _TRACE_ID,
            "title_substring": title_substring,
            "class_name": class_name,
        },
    )
    return None


def _activate_window(hwnd: int) -> bool:
    """激活窗口（pygetwindow 方式，和 db_to_xlsx.py 一致）。"""
    import pygetwindow as gw

    try:
        win = gw.Win32Window(hwnd)
        if win.isMinimized:
            win.restore()
            time.sleep(0.3)
        win.activate()
        time.sleep(0.5)
        log_info("window_activated", {"trace_id": _TRACE_ID, "hwnd": hwnd, "title": win.title})
        return True
    except Exception as e:
        log_error("window_activate_failed", {"trace_id": _TRACE_ID, "error": str(e)})
        return False


# ============================================================
# 图像识别定位
# ============================================================


def _locate_on_screen(
    image_path: str,
    confidence: float | None = None,
):
    """在屏幕上查找参考截图的位置，返回中心点坐标。"""
    full_path = _IMAGES_DIR / image_path
    if not full_path.exists():
        log_error(
            "image_not_found",
            {"trace_id": _TRACE_ID, "path": str(full_path)},
        )
        return None

    try:
        if confidence is not None:
            location = pg.locateCenterOnScreen(str(full_path), confidence=confidence)
        else:
            location = pg.locateCenterOnScreen(str(full_path))
    except Exception as e:
        log_error(
            "locate_failed",
            {"trace_id": _TRACE_ID, "image": image_path, "error": str(e)},
        )
        return None

    if location is None:
        log_error(
            "image_not_matched",
            {"trace_id": _TRACE_ID, "image": image_path},
        )
    return location


# ============================================================
# 操作函数
# ============================================================


def _click_image(image_path: str, confidence: float | None, delay: float) -> None:
    """按截图定位并点击。"""
    pt = _locate_on_screen(image_path, confidence)
    if pt is None:
        return
    log_info(
        "click_image",
        {"trace_id": _TRACE_ID, "image": image_path, "position": (pt.x, pt.y)},
    )
    pg.click(pt.x, pt.y)
    time.sleep(delay)


def _hover_image(image_path: str, confidence: float | None, delay: float) -> None:
    """按截图定位并悬停（用于展开子菜单）。"""
    pt = _locate_on_screen(image_path, confidence)
    if pt is None:
        return
    log_info(
        "hover_image",
        {"trace_id": _TRACE_ID, "image": image_path, "position": (pt.x, pt.y)},
    )
    pg.moveTo(pt.x, pt.y, duration=0.3)
    time.sleep(delay)


def _type_into_image(
    image_path: str,
    text: str,
    confidence: float | None,
    delay: float,
) -> None:
    """按截图找到输入框 → 点击聚焦 → 清空 → 粘贴文本。"""
    pt = _locate_on_screen(image_path, confidence)
    if pt is None:
        return
    log_info(
        "type_into_image",
        {"trace_id": _TRACE_ID, "image": image_path, "text": text},
    )
    pg.click(pt.x, pt.y)
    time.sleep(0.2)
    pg.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyperclip.copy(text)
    pg.hotkey("ctrl", "v")
    pyperclip.copy("")
    time.sleep(delay)


def _type_text(text: str, delay: float) -> None:
    """直接粘贴文本（不定位控件，依赖当前焦点）。"""
    pyperclip.copy(text)
    pg.hotkey("ctrl", "v")
    pyperclip.copy("")
    time.sleep(delay)


# ============================================================
# 调试 / 运行模式
# ============================================================


def debug_steps() -> None:
    """试运行模式：逐个步骤查找截图并标记位置，不执行点击/输入。"""
    hwnd = _find_window(class_name="FLUTTER_RUNNER_WIN32_WINDOW")
    if not hwnd:
        print("未找到吉客云窗口。")
        return

    _activate_window(hwnd)
    print(f"\n找到窗口 (hwnd={hwnd})")
    print("逐步骤查找截图，鼠标会移到匹配位置...\n")

    for i, step in enumerate(STEPS):
        action = step["action"]
        image = step.get("image")
        comment = step.get("comment", "")
        confidence = step.get("confidence")

        print(f"{'─' * 60}")
        print(f"步骤 {i + 1}: {comment}")
        print(f"  action={action}  image={image}  confidence={confidence}")
        print(f"{'─' * 60}")

        if not image:
            print("  无截图 — 跳过\n")
            continue

        pt = _locate_on_screen(image, confidence)
        if pt is None:
            print(f"  [未匹配] 屏幕上未找到 {image}\n")
            continue

        print(f"  [匹配] 位置: ({pt.x}, {pt.y})")
        pg.moveTo(pt.x, pt.y, duration=0.3)
        print(f"  鼠标已移到匹配位置\n")
        time.sleep(1)

    print(f"{'─' * 60}")
    print("调试完成。确认所有截图匹配无误后，不加 --dry-run 执行实际导出。")
    print(f"{'─' * 60}")


def export_orders_to_xlsx() -> None:
    """使用图像识别从吉客云 OMS 桌面应用导出订单数据到 xlsx。

    通过 pyautogui.locateOnScreen 定位控件，不依赖窗口坐标或 DPI 缩放。
    """
    hwnd = _find_window(class_name="FLUTTER_RUNNER_WIN32_WINDOW")
    if not hwnd:
        log_error(
            "export_cancel",
            {"trace_id": _TRACE_ID, "reason": "吉客云窗口未找到"},
        )
        return

    _activate_window(hwnd)

    for step in STEPS:
        action = step["action"]
        delay = step.get("delay", 1)
        image = step.get("image", "")
        confidence = step.get("confidence")

        if action == "click":
            _click_image(image, confidence, delay)
        elif action == "hover":
            _hover_image(image, confidence, delay)
        elif action == "type":
            text = step.get("text", "")
            if image:
                _type_into_image(image, text, confidence, delay)
            else:
                _type_text(text, delay)
        elif action == "wait":
            deadline = time.time() + step.get("max_wait", 30)
            while time.time() < deadline:
                if _locate_on_screen(image, confidence) is not None:
                    time.sleep(delay)
                    break
                time.sleep(0.5)
            else:
                log_error(
                    "image_timeout",
                    {"trace_id": _TRACE_ID, "image": image},
                )
        else:
            log_error(
                "unknown_action",
                {"trace_id": _TRACE_ID, "action": action},
            )

    log_info("export_complete", {"trace_id": _TRACE_ID})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="图像识别 吉客云导出脚本")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="调试模式：只查找并标记位置，不执行点击/输入",
    )
    args = parser.parse_args()

    if args.dry_run:
        print("调试模式：图像识别，查找截图位置...")
        debug_steps()
    else:
        INTERVAL_SECONDS = 9
        time.sleep(INTERVAL_SECONDS)
        log_info(
            "scheduler_start",
            {
                "trace_id": _TRACE_ID,
                "interval_seconds": INTERVAL_SECONDS,
                "hint": "将鼠标移到屏幕左上角 (0,0) 可强制中断",
            },
        )
        try:
            while True:
                log_info(
                    "export_cycle_start",
                    {"trace_id": _TRACE_ID, "time": time.strftime("%H:%M:%S")},
                )
                export_orders_to_xlsx()
                log_info(
                    "waiting_next_cycle",
                    {"trace_id": _TRACE_ID, "interval_seconds": INTERVAL_SECONDS},
                )
                time.sleep(INTERVAL_SECONDS)
        except KeyboardInterrupt:
            log_info("scheduler_stopped", {"trace_id": _TRACE_ID})
