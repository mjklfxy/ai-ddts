from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import time
from datetime import datetime
from pathlib import Path

import pyautogui as pg
import pygetwindow as gw
import pyperclip

from shared.logging.logger import log_error, log_info

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

pg.FAILSAFE = True
pg.PAUSE = 0.05

_TRACE_ID = f"db-to-xlsx-{os.getpid()}"
# === MODIFIED START ===
# 原因：RPA 导出文件名和统计时间类型需要集中定义，确保 API 与 Excel 回填窗口口径一致。
# 影响范围：导出保存文件名、统计时间类型选择。
DEFAULT_EXPORT_FILENAME = "销售单查询.xlsx"
RPA_STATISTICS_TIME_TYPE = "审核时间"
# === MODIFIED END ===


# === MODIFIED START ===
# 原因：RPA 导出完成后需要明确记录目标文件位置和文件状态，方便确认导出落点。
# 影响范围：桌面导出日志、Jikeyun RPA 调试。
def describe_export_file(target_path: Path | str) -> tuple[str, dict[str, object]]:
    """Builds the export-file log event and payload for one target path."""

    path = Path(target_path)
    payload: dict[str, object] = {
        "path": str(path),
        "exists": path.exists(),
    }
    if not path.exists():
        return "export_file_missing", payload

    stat = path.stat()
    payload["size_bytes"] = stat.st_size
    payload["modified_at"] = time.strftime(
        "%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime)
    )
    return "export_file_detected", payload


# === MODIFIED END ===


def _find_window(substring: str, trace_id: str) -> gw.Win32Window | None:
    """Finds the first desktop window whose title contains the target text."""

    windows = gw.getWindowsWithTitle(substring)
    if not windows:
        log_info("window_not_found", {"trace_id": trace_id, "substring": substring})
        return None
    log_info(
        "window_found",
        {"trace_id": trace_id, "substring": substring, "title": windows[0].title},
    )
    return windows[0]


def _activate_window(win: gw.Win32Window, trace_id: str) -> bool:
    """Activates the target window before sending simulated input."""

    log_info(
        "window_activate",
        {
            "trace_id": trace_id,
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
        log_info("mouse_position", {"trace_id": trace_id, "position": cur})
    except Exception as e:
        log_error("pyautogui_error", {"trace_id": trace_id, "error": str(e)})
        return False
    return True


# === MODIFIED START ===
# 原因：恢复之前更可靠的模拟键鼠实现，避免 pg.click 在吉客云 Flutter 桌面端未触发真实点击。
# 影响范围：所有 RPA click 步骤、点击日志。
def _click(win: gw.Win32Window, rx: int, ry: int, trace_id: str, delay: float = 1) -> None:
    """Clicks one screen coordinate using explicit down/up mouse events."""

    _ = win
    x, y = rx, ry
    log_info(
        "click",
        {"trace_id": trace_id, "relative": (rx, ry), "screen": (x, y)},
    )
    pg.moveTo(x, y, duration=0.2)
    pg.mouseDown()
    pg.mouseUp()
    try:
        actual_position = pg.position()
    except Exception as e:
        log_error("pyautogui_error", {"trace_id": trace_id, "error": str(e)})
        actual_position = None
    log_info(
        "click_complete",
        {
            "trace_id": trace_id,
            "relative": (rx, ry),
            "screen": (x, y),
            "actual_position": actual_position,
        },
    )
    time.sleep(delay)


def _move_click(
    win: gw.Win32Window, rx: int, ry: int, trace_id: str, delay: float = 1
) -> None:
    """Moves horizontally then vertically to the target, then clicks.

    Used for Flutter submenus where diagonal movement can leave the menu area
    and cause the submenu to close.
    """

    _ = win
    cur_x, cur_y = pg.position()
    target_x, target_y = rx, ry
    log_info(
        "move_click",
        {"trace_id": trace_id, "from": (cur_x, cur_y), "to": (target_x, target_y)},
    )
    pg.moveTo(target_x, cur_y, duration=0.2)
    time.sleep(0.1)
    pg.moveTo(target_x, target_y, duration=0.2)
    pg.mouseDown()
    pg.mouseUp()
    time.sleep(delay)


def _hover(win: gw.Win32Window, rx: int, ry: int, trace_id: str, delay: float = 1) -> None:
    """Moves the mouse to one screen coordinate and waits for hover menus."""

    _ = win
    x, y = rx, ry
    log_info(
        "hover",
        {"trace_id": trace_id, "relative": (rx, ry), "screen": (x, y)},
    )
    pg.moveTo(x, y, duration=0.3)
    time.sleep(delay)


# === MODIFIED END ===


def _type(text: str, trace_id: str, delay: float = 1) -> None:
    """Inputs text through the clipboard."""

    log_info(
        "clipboard_type",
        {
            "trace_id": trace_id,
            "text_preview": text[:12],
            "text_length": len(text),
        },
    )
    pyperclip.copy(text)
    pg.hotkey("ctrl", "v")
    pyperclip.copy("")
    time.sleep(delay)


# === MODIFIED START ===
# 原因：恢复可测试的 RPA 导出步骤，并显式选择复核时间、状态筛选、明文合并导出当前页、另存为和覆盖确认。
# 影响范围：吉客云桌面导出流程、RPA 回归测试。
def _replace_text(text: str, trace_id: str, delay: float = 1) -> None:
    """Selects existing text and replaces it through the clipboard."""

    log_info(
        "clipboard_replace",
        {
            "trace_id": trace_id,
            "text_preview": text[:12],
            "text_length": len(text),
        },
    )
    pg.hotkey("ctrl", "a")
    time.sleep(0.3)
    _type(text, trace_id, delay)


def _press(key: str, trace_id: str, delay: float = 1) -> None:
    """Presses one keyboard key and waits for the desktop to react."""

    log_info("key_press", {"trace_id": trace_id, "key": key})
    pg.press(key)
    time.sleep(delay)


def _export_target_path(xlsx_path: Path | str) -> Path:
    """Returns the absolute XLSX path written into the Save As filename box."""

    return Path(xlsx_path).resolve()


def _confirm_overwrite_if_present(
    trace_id: str,
    timeout_seconds: float = 5,
) -> bool:
    """Confirms the Windows overwrite dialog only when it is actually present."""

    deadline = time.time() + timeout_seconds
    while time.time() <= deadline:
        windows = gw.getWindowsWithTitle("确认另存为")
        if windows:
            dialog = windows[0]
            dialog.activate()
            time.sleep(0.2)
            _click(dialog, dialog.left + 357, dialog.top + 170, trace_id, delay=0.2)
            log_info(
                "overwrite_confirmed",
                {
                    "trace_id": trace_id,
                    "title": dialog.title,
                    "screen": (dialog.left + 357, dialog.top + 170),
                },
            )
            return True
        time.sleep(0.3)
    log_info(
        "overwrite_not_present",
        {"trace_id": trace_id, "timeout_seconds": timeout_seconds},
    )
    return False


def _wait_for_window(
    title: str,
    trace_id: str,
    timeout_seconds: float = 120,
    poll_seconds: float = 0.5,
) -> bool:
    """Waits until a Windows dialog appears instead of relying on fixed delays."""

    log_info(
        "window_wait_start",
        {
            "trace_id": trace_id,
            "title": title,
            "timeout_seconds": timeout_seconds,
            "poll_seconds": poll_seconds,
        },
    )
    deadline = time.time() + timeout_seconds
    while time.time() <= deadline:
        windows = gw.getWindowsWithTitle(title)
        if windows:
            log_info(
                "window_wait_found",
                {
                    "trace_id": trace_id,
                    "title": title,
                    "window_title": windows[0].title,
                },
            )
            return True
        time.sleep(poll_seconds)
    log_error(
        "window_wait_timeout",
        {"trace_id": trace_id, "title": title, "timeout_seconds": timeout_seconds},
    )
    return False


def _export_steps(
    xlsx_path: Path | str,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> list[tuple[str, str, tuple[int, int] | str, float]]:
    """Builds the desktop RPA steps with an optional review-time window."""

    target_path = str(_export_target_path(xlsx_path))
    # 订单状态是 Flutter 多选复选框下拉：先点击输入区域，再点箭头展开列表，逐个勾选复选框，点确认。
    steps: list[tuple[str, str, tuple[int, int] | str, float]] = [
        ("focus_order_status_input", "click", (277, 584), 1),
        ("open_order_status_filter", "click", (188, 588), 1),
        ("type_order_status_keyword", "type", "待发货", 1),
        ("check_status_pending_submit", "click", (173, 656), 1),
        ("check_status_submitting", "click", (173, 690), 1),
        ("check_status_submitted", "click", (173, 723), 1),
        ("confirm_order_status_filter", "click", (194, 866), 1),
    ]
    if start_time is not None and end_time is not None:
        # Flutter combobox 下拉选择：点击展开列表，再点击列表项"审核时间"。
        steps.extend(
            [
                ("open_statistics_time_type", "click", (173, 411), 1),
                ("click_statistics_time_type_item", "click", (142, 550), 1),
                ("focus_order_time_start", "click", (82, 482), 1),
                (
                    "replace_order_time_start",
                    "replace_text",
                    _format_ui_datetime(start_time),
                    1,
                ),
                ("confirm_order_time_start", "press", "enter", 2),
                ("focus_order_time_end", "click", (82, 520), 1),
                (
                    "replace_order_time_end",
                    "replace_text",
                    _format_ui_datetime(end_time),
                    1,
                ),
                ("confirm_order_time_end", "press", "enter", 2),
            ]
        )
    steps.extend(
        [
            ("pre_filter_click_1", "click", (522, 215), 1),
            ("pre_filter_click_2", "click", (447, 247), 1),
            ("pre_filter_click_3", "click", (447, 247), 1),
            ("pre_filter_click_4", "click", (501, 360), 1),
            ("pre_filter_click_5", "click", (688, 394), 3),
            ("apply_left_filters", "click", (68, 933), 9),
            ("open_export_menu", "click", (1383, 172), 2),
            ("hover_plain_merge_export", "hover", (1384, 363), 2),
            ("click_export_all_pages", "move_click", (1743, 461), 2),
            ("wait_save_as_dialog", "wait_window", "另存为", 120),
            ("focus_save_as_filename", "click", (1042, 802), 1),
            ("replace_save_as_path", "replace_text", target_path, 1),
            ("click_save_as_button", "click", (1321, 804), 3),
            ("confirm_overwrite_if_present", "confirm_overwrite", "", 5),
        ]
    )
    return steps


def _format_ui_datetime(value: datetime) -> str:
    """Formats one datetime for the JiKeYun desktop filter inputs."""

    return value.strftime("%Y-%m-%d %H:%M:%S")


# === MODIFIED END ===


def export_orders_to_xlsx(
    trace_id: str | None = None,
    xlsx_path: Path | str = Path("input") / DEFAULT_EXPORT_FILENAME,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> None:
    """Exports order data from the JiKeYun desktop app into an xlsx file."""

    safe_trace_id = trace_id or _TRACE_ID
    target_path = _export_target_path(xlsx_path)
    start_epoch = time.time()
    log_info("export_start", {"trace_id": safe_trace_id})
    log_info(
        "export_target_path",
        {
            "trace_id": safe_trace_id,
            "xlsx_path": str(target_path),
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
        },
    )

    pg.moveTo(1, 1, duration=0.1)

    win = _find_window("吉客云", safe_trace_id)
    if not win:
        log_error(
            "export_cancel", {"trace_id": safe_trace_id, "reason": "吉客云窗口未找到"}
        )
        return

    if not _activate_window(win, safe_trace_id):
        log_error("export_cancel", {"trace_id": safe_trace_id, "reason": "无法激活窗口"})
        return

    steps = _export_steps(target_path, start_time=start_time, end_time=end_time)

    for index, (step_name, action, value, delay) in enumerate(steps, start=1):
        payload = {
            "trace_id": safe_trace_id,
            "step_index": index,
            "step_count": len(steps),
            "step_name": step_name,
            "action": action,
            "delay_seconds": delay,
        }
        if isinstance(value, tuple):
            payload["relative"] = value
        else:
            payload["text_preview"] = value[:12]
            payload["text_length"] = len(value)
        log_info("export_step_start", payload)
        if action in ("hover", "click", "move_click") and isinstance(value, tuple):
            rx, ry = value
            if action == "hover":
                _hover(win, rx, ry, safe_trace_id, delay)
            elif action == "move_click":
                _move_click(win, rx, ry, safe_trace_id, delay)
            else:
                _click(win, rx, ry, safe_trace_id, delay)
        elif action == "type" and isinstance(value, str):
            _type(value, safe_trace_id, delay)
        elif action == "replace_text" and isinstance(value, str):
            _replace_text(value, safe_trace_id, delay)
        elif action == "press" and isinstance(value, str):
            _press(value, safe_trace_id, delay)
        elif action == "wait_window" and isinstance(value, str):
            _wait_for_window(value, safe_trace_id, timeout_seconds=delay)
        elif action == "confirm_overwrite":
            _confirm_overwrite_if_present(safe_trace_id, timeout_seconds=delay)
        log_info("export_step_complete", payload)

    log_info(
        "export_complete",
        {
            "trace_id": safe_trace_id,
            "step_count": len(steps),
            "duration_ms": int((time.time() - start_epoch) * 1000),
        },
    )
    event, payload = describe_export_file(target_path)
    payload["trace_id"] = safe_trace_id
    payload["xlsx_path"] = str(target_path)
    if event == "export_file_missing":
        log_error(event, payload)
    else:
        log_info(event, payload)


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
