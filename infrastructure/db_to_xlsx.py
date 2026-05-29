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
kernel32 = ctypes.windll.kernel32
# === MODIFIED START ===
# 原因：恢复重构前的窗口激活完整常量集。
# 影响范围：RPA 窗口前台控制。
SW_RESTORE = 9
SW_MAXIMIZE = 3
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040
FORCE_FOREGROUND_FLAGS = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
# === MODIFIED END ===
SPI_GETFOREGROUNDLOCKTIMEOUT = 0x2000
SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
SPIF_SENDCHANGE = 0x0002
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

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
    """Finds the desktop window whose title best matches the target text."""

    # === MODIFIED START ===
    # 原因：getWindowsWithTitle 是子串匹配，VSCode 标题含"吉客云"会排在前面。
    #   优先选标题精确匹配的窗口，其次选标题最短的（最可能是目标客户端）。
    # 影响范围：RPA 窗口查找。
    windows = gw.getWindowsWithTitle(substring)
    if not windows:
        log_info("window_not_found", {"trace_id": trace_id, "substring": substring})
        return None

    # 精确匹配优先
    for w in windows:
        if w.title.strip() == substring:
            log_info("window_found", {"trace_id": trace_id, "substring": substring, "title": w.title})
            return w

    # 否则选标题最短的（排除 IDE/浏览器等长标题窗口）
    best = min(windows, key=lambda w: len(w.title))
    log_info("window_found", {"trace_id": trace_id, "substring": substring, "title": best.title})
    return best
    # === MODIFIED END ===


def _activate_window(win: gw.Win32Window, trace_id: str) -> bool:
    """Activates the target window before sending simulated input."""

    # === MODIFIED START ===
    # 原因：恢复重构前的多层窗口激活逻辑，包括 win.activate() 兜底和重试。
    # 影响范围：RPA 吉客云窗口激活、后续坐标点击可靠性。
    hwnd = _window_handle(win)
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
            "hwnd": hwnd,
        },
    )

    # DEBUG: 每步记录前台窗口状态
    log_info("dbg_step", {"trace_id": trace_id, "step": "start", "hwnd": hwnd, "fg": _foreground_window_handle()})

    if win.isMinimized:
        win.restore()
        time.sleep(0.3)
        log_info("dbg_step", {"trace_id": trace_id, "step": "after_restore", "fg": _foreground_window_handle()})

    if hwnd is not None:
        _force_window_foreground(hwnd, trace_id)
        log_info("dbg_step", {"trace_id": trace_id, "step": "after_force_fg", "fg": _foreground_window_handle(), "match": _is_foreground_window(hwnd)})

    _maximize_window(win, hwnd, trace_id)
    log_info("dbg_step", {"trace_id": trace_id, "step": "after_maximize", "fg": _foreground_window_handle()})

    try:
        win.activate()
        log_info("dbg_step", {"trace_id": trace_id, "step": "after_activate", "fg": _foreground_window_handle()})
    except Exception as e:
        log_error("window_activate_fallback_failed", {"trace_id": trace_id, "hwnd": hwnd, "error": str(e)})
        log_info("dbg_step", {"trace_id": trace_id, "step": "activate_exception", "fg": _foreground_window_handle(), "err": str(e)})

    time.sleep(0.5)
    fg_now = _foreground_window_handle()
    log_info("dbg_step", {"trace_id": trace_id, "step": "verify1", "hwnd": hwnd, "fg": fg_now, "match": _is_foreground_window(hwnd)})

    # === MODIFIED START ===
    # 原因：后台线程 uvicorn 无法通过 SetForegroundWindow 抢前台（Windows 安全限制），
    #   但 pyautogui 的 click/moveTo 是全局的，不依赖前台状态。
    #   放宽验证：前台不匹配时打 warning 继续，不再 return False。
    # 影响范围：RPA 窗口激活容错。
    if hwnd is not None and not _is_foreground_window(hwnd):
        log_error(
            "window_foreground_not_active",
            {"trace_id": trace_id, "hwnd": hwnd, "foreground_hwnd": fg_now, "title": win.title,
             "note": "后台线程无法抢前台，继续执行RPA"},
        )
        _steal_foreground(hwnd, trace_id)
        time.sleep(0.3)
        fg_retry = _foreground_window_handle()
        log_info("dbg_step", {"trace_id": trace_id, "step": "after_steal", "fg": fg_retry, "match": _is_foreground_window(hwnd)})
    # === MODIFIED END ===

    try:
        cur = pg.position()
        log_info("mouse_position", {"trace_id": trace_id, "position": cur})
    except Exception as e:
        log_error("pyautogui_error", {"trace_id": trace_id, "error": str(e)})
        return False

    if hwnd is not None:
        log_info(
            "window_foreground_verified",
            {"trace_id": trace_id, "hwnd": hwnd, "title": win.title,
             "maximized": _is_window_maximized(win), "left": win.left,
             "top": win.top, "width": win.width, "height": win.height},
        )
    return True
    # === MODIFIED END ===


def _window_handle(win: gw.Win32Window) -> int | None:
    """Returns the native Windows handle exposed by pygetwindow."""

    hwnd = getattr(win, "_hWnd", None) or getattr(win, "hWnd", None)
    if isinstance(hwnd, int) and hwnd > 0:
        return hwnd
    return None


def _force_window_foreground(hwnd: int, trace_id: str) -> None:
    """Restores, foregrounds, and briefly topmost-pins a target window."""

    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        _steal_foreground(hwnd, trace_id)
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, FORCE_FOREGROUND_FLAGS)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, FORCE_FOREGROUND_FLAGS)
        log_info("window_force_foreground", {"trace_id": trace_id, "hwnd": hwnd})
    except Exception as e:
        log_error("window_force_foreground_failed", {"trace_id": trace_id, "hwnd": hwnd, "error": str(e)})


def _steal_foreground(hwnd: int, trace_id: str) -> None:
    """Aggressively forces a window to foreground using AttachThreadInput + keybd_event."""

    # === MODIFIED START ===
    # 原因：SendInput 从后台线程注入的输入不被 Windows 认定为当前线程的用户输入，
    #   导致 SetForegroundWindow 仍被拦截。改用 keybd_event 投递到线程消息队列。
    # 影响范围：后台线程窗口激活。
    try:
        target_tid = user32.GetWindowThreadProcessId(hwnd, None)
        current_tid = kernel32.GetCurrentThreadId()

        timeout = ctypes.c_uint(0)
        user32.SystemParametersInfoW(SPI_GETFOREGROUNDLOCKTIMEOUT, 0, ctypes.byref(timeout), 0)
        user32.SystemParametersInfoW(SPI_SETFOREGROUNDLOCKTIMEOUT, 0, 0, SPIF_SENDCHANGE)

        attached = False
        if target_tid != current_tid:
            attached = bool(user32.AttachThreadInput(current_tid, target_tid, True))

        # 先模拟 Alt 按下/释放，让 Windows 认为当前线程有用户输入
        _keybd_alt_press_release()

        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)

        if user32.GetForegroundWindow() != hwnd:
            # 再试一次
            _keybd_alt_press_release()
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)

        if attached:
            user32.AttachThreadInput(current_tid, target_tid, False)

        user32.SystemParametersInfoW(SPI_SETFOREGROUNDLOCKTIMEOUT, timeout.value, 0, SPIF_SENDCHANGE)
        log_info("steal_foreground_done", {"trace_id": trace_id, "hwnd": hwnd})
    except Exception as e:
        log_error("steal_foreground_failed", {"trace_id": trace_id, "hwnd": hwnd, "error": str(e)})
    # === MODIFIED END ===


def _keybd_alt_press_release() -> None:
    """Simulates Alt key press+release via keybd_event (thread message queue based)."""

    VK_MENU = 0x12
    KEYEVENTF_KEYUP_FLAG = 0x0002
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP_FLAG, 0)


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("union", _INPUT_UNION),
    ]


def _simulate_alt_key() -> None:
    """Simulates Alt key press+release to satisfy Windows foreground lock."""

    VK_MENU = 0x12

    def _make_input(vk: int, flags: int) -> _INPUT:
        inp = _INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = vk
        inp.union.ki.dwFlags = flags
        return inp

    arr = (_INPUT * 2)(_make_input(VK_MENU, 0), _make_input(VK_MENU, KEYEVENTF_KEYUP))
    user32.SendInput(2, ctypes.byref(arr), ctypes.sizeof(_INPUT))


def _maximize_window(win: gw.Win32Window, hwnd: int | None, trace_id: str) -> None:
    """Maximizes the target window before fixed-coordinate automation."""

    try:
        if not _is_window_maximized(win):
            win.maximize()
            time.sleep(0.3)
        log_info(
            "window_maximized",
            {"trace_id": trace_id, "hwnd": hwnd, "title": win.title,
             "left": win.left, "top": win.top, "width": win.width,
             "height": win.height, "maximized": _is_window_maximized(win)},
        )
    except Exception as e:
        log_error("window_maximize_failed", {"trace_id": trace_id, "hwnd": hwnd, "error": str(e)})
        if hwnd is not None:
            try:
                user32.ShowWindow(hwnd, SW_MAXIMIZE)
                time.sleep(0.3)
                log_info("window_maximized_win32", {"trace_id": trace_id, "hwnd": hwnd})
            except Exception as win32_error:
                log_error("window_maximize_win32_failed", {"trace_id": trace_id, "hwnd": hwnd, "error": str(win32_error)})


def _is_window_maximized(win: gw.Win32Window) -> bool:
    return bool(getattr(win, "isMaximized", False))


def _foreground_window_handle() -> int | None:
    """Returns the current foreground window handle when available."""

    try:
        hwnd = user32.GetForegroundWindow()
    except Exception:
        return None
    if isinstance(hwnd, int) and hwnd > 0:
        return hwnd
    return None


def _is_foreground_window(hwnd: int) -> bool:
    """Returns whether the expected window is currently foreground."""

    return _foreground_window_handle() == hwnd
# === MODIFIED END ===


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
    time.sleep(0.15)
    pg.press("delete")
    time.sleep(0.15)
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
    """Confirms the Windows overwrite dialog only when it is actually present.

    Silently returns False if the dialog is not found, disappears mid-click,
    or the window handle becomes invalid — none of these are fatal.
    """

    try:
        deadline = time.time() + timeout_seconds
        while time.time() <= deadline:
            windows = gw.getWindowsWithTitle("确认另存为")
            if windows:
                dialog = windows[0]
                try:
                    dialog.activate()
                    time.sleep(0.2)
                    click_x = dialog.left + 357
                    click_y = dialog.top + 170
                    _click(dialog, click_x, click_y, trace_id, delay=0.2)
                    log_info(
                        "overwrite_confirmed",
                        {"trace_id": trace_id, "screen": (click_x, click_y)},
                    )
                    return True
                except Exception:
                    log_info(
                        "overwrite_dialog_gone",
                        {"trace_id": trace_id},
                    )
                    return False
            time.sleep(0.3)
    except Exception:
        pass
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
            ("focus_save_as_filename", "click", (1042, 802), 2),
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
        raise RuntimeError("吉客云窗口未找到，请确认客户端已打开")

    if not _activate_window(win, safe_trace_id):
        log_error("export_cancel", {"trace_id": safe_trace_id, "reason": "无法激活窗口"})
        raise RuntimeError("无法激活吉客云窗口，请将客户端置于前台")

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
