from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import time

import pyautogui as pg
import pygetwindow as gw
import pyperclip

from shared.logging.logger import log_error, log_info

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

pg.FAILSAFE = True
pg.PAUSE = 0.05

_TRACE_ID = f"db-to-xlsx-{os.getpid()}"


def _find_window(substring: str) -> gw.Win32Window | None:
    """查找标题包含 substring 的窗口，返回窗口对象。"""
    windows = gw.getWindowsWithTitle(substring)
    if not windows:
        log_info("window_not_found", {"trace_id": _TRACE_ID, "substring": substring})
        return None
    return windows[0]


def _activate_window(win: gw.Win32Window) -> bool:
    """激活窗口并返回是否成功。"""
    log_info(
        "window_activate",
        {
            "trace_id": _TRACE_ID,
            "title": win.title,
            "left": win.left,
            "top": win.top,
            "width": win.width,
            "height": win.height,
            "minimized": win.isMinimized,
        },
    )
    if win.isMinimized:
        win.restore()
        time.sleep(0.3)
    win.activate()
    time.sleep(0.5)
    try:
        cur = pg.position()
        log_info("mouse_position", {"trace_id": _TRACE_ID, "position": cur})
    except Exception as e:
        log_error("pyautogui_error", {"trace_id": _TRACE_ID, "error": str(e)})
        return False
    return True


def _click(win: gw.Win32Window, rx: int, ry: int, delay: float = 1) -> None:
    """点击窗口内相对坐标 (rx, ry)。"""
    # x, y = win.left + rx, win.top + ry
    x, y = rx, ry
    log_info(
        "click",
        {"trace_id": _TRACE_ID, "relative": (rx, ry), "screen": (x, y)},
    )
    pg.click(x, y)
    time.sleep(delay)


def _hover(win: gw.Win32Window, rx: int, ry: int, delay: float = 1) -> None:
    """悬浮到窗口内相对坐标。"""
    x, y = rx, ry
    log_info(
        "hover",
        {"trace_id": _TRACE_ID, "relative": (rx, ry), "screen": (x, y)},
    )
    pg.moveTo(x, y, duration=0.3)
    time.sleep(delay)


def _type(text: str, delay: float = 1) -> None:
    """通过剪贴板输入文本。"""
    pyperclip.copy(text)
    pg.hotkey("ctrl", "v")
    pyperclip.copy("")
    time.sleep(delay)


def export_orders_to_xlsx() -> None:
    """从吉客云 OMS 桌面应用导出订单数据到 xlsx。

    所有坐标均为相对窗口左上角的偏移量 (rx, ry)。
    窗口位置变化或 DPI 缩放都不会影响操作。
    """
    pg.moveTo(1, 1, duration=0.1)

    win = _find_window("吉客云")
    if not win:
        log_error(
            "export_cancel", {"trace_id": _TRACE_ID, "reason": "吉客云窗口未找到"}
        )
        return

    if not _activate_window(win):
        log_error("export_cancel", {"trace_id": _TRACE_ID, "reason": "无法激活窗口"})
        return

    # === 修改坐标从这里开始 ===
    # 每个步骤的坐标是相对于窗口左上角的 (rx, ry)
    # 如果发现点击位置不对，调整下面这些数字即可
    steps: list[tuple[str, tuple[int, int] | str, float]] = [
        ("click", (272, 171), 4),
        ("click", (550, 172), 2),
        ("type", "待发货-已递交", 2),
        ("click", (540, 198), 3),
        ("click", (629, 369), 3),
        # ("click", (868, 368), 3),
        ("click", (1592, 115), 1),
        ("hover", (1726, 244), 1),
        ("click", (1782, 300), 9),
        ("click", (1436, 1019), 1),
        ("click", (739, 131), 1),
        ("click", (1325, 207), 3),
        ("click", (1200, 715), 1),
        ("click", (1000, 530), 1),
        ("click", (950, 950), 1),
    ]
    # === 修改坐标到这里结束 ===

    for action, value, delay in steps:
        if action in ("hover", "click") and isinstance(value, tuple):
            rx, ry = value
            if action == "hover":
                _hover(win, rx, ry, delay)
            else:
                _click(win, rx, ry, delay)
        elif action == "type" and isinstance(value, str):
            _type(value, delay)

    log_info("export_complete", {"trace_id": _TRACE_ID})


if __name__ == "__main__":
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
