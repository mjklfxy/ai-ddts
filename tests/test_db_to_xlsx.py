from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from datetime import datetime

import infrastructure.db_to_xlsx as db_to_xlsx
from infrastructure.db_to_xlsx import (
    _click,
    _confirm_overwrite_if_present,
    _export_steps,
    _hover,
    _wait_for_window,
    describe_export_file,
)


class DbToXlsxTests(TestCase):
    """Tests export-file state reporting for the desktop RPA exporter."""

    def test_describe_export_file_reports_missing_target(self) -> None:
        with TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "missing.xlsx"

            event, payload = describe_export_file(target_path)

        self.assertEqual(event, "export_file_missing")
        self.assertEqual(payload["path"], str(target_path))
        self.assertEqual(payload["exists"], False)

    def test_describe_export_file_reports_detected_target(self) -> None:
        with TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "orders.xlsx"
            target_path.write_bytes(b"demo-xlsx")

            event, payload = describe_export_file(target_path)

        self.assertEqual(event, "export_file_detected")
        self.assertEqual(payload["path"], str(target_path))
        self.assertEqual(payload["exists"], True)
        self.assertEqual(payload["size_bytes"], 9)
        self.assertIn("modified_at", payload)

    # === MODIFIED START ===
    # 原因：RPA 点击必须恢复为可验证的鼠标移动、按下、抬起流程，避免 pg.click 在 Flutter 桌面端吞事件。
    # 影响范围：吉客云桌面导出模拟键鼠点击。
    def test_click_moves_mouse_down_and_up_at_target_screen_position(self) -> None:
        calls: list[tuple[str, object]] = []
        logs: list[tuple[str, dict[str, object]]] = []
        original_pg = db_to_xlsx.pg
        original_sleep = db_to_xlsx.time.sleep
        original_log_info = db_to_xlsx.log_info

        class FakePyAutoGui:
            """Captures mouse calls issued by the RPA click helper."""

            def moveTo(self, x, y, duration=0):
                calls.append(("moveTo", (x, y, duration)))

            def mouseDown(self):
                calls.append(("mouseDown", None))

            def mouseUp(self):
                calls.append(("mouseUp", None))

            def position(self):
                return (1200, 715)

            def click(self, x, y):
                calls.append(("click", (x, y)))

        class FakeWindow:
            """Represents the desktop window passed into coordinate helpers."""

            left = 50
            top = 60

        try:
            db_to_xlsx.pg = FakePyAutoGui()
            db_to_xlsx.time.sleep = lambda delay: None
            db_to_xlsx.log_info = lambda event, payload: logs.append((event, payload))

            _click(FakeWindow(), 1200, 715, "TRACE-CLICK", delay=0.2)
        finally:
            db_to_xlsx.pg = original_pg
            db_to_xlsx.time.sleep = original_sleep
            db_to_xlsx.log_info = original_log_info

        self.assertEqual(
            calls,
            [
                ("moveTo", (1200, 715, 0.2)),
                ("mouseDown", None),
                ("mouseUp", None),
            ],
        )
        self.assertNotIn(("click", (1200, 715)), calls)
        self.assertEqual(logs[-1][0], "click_complete")
        self.assertEqual(logs[-1][1]["screen"], (1200, 715))
        self.assertEqual(logs[-1][1]["actual_position"], (1200, 715))

    def test_hover_uses_target_screen_position(self) -> None:
        calls: list[tuple[str, object]] = []
        original_pg = db_to_xlsx.pg
        original_sleep = db_to_xlsx.time.sleep
        original_log_info = db_to_xlsx.log_info

        class FakePyAutoGui:
            """Captures hover movement issued by the RPA helper."""

            def moveTo(self, x, y, duration=0):
                calls.append(("moveTo", (x, y, duration)))

        class FakeWindow:
            """Represents the desktop window passed into coordinate helpers."""

            left = 50
            top = 60

        try:
            db_to_xlsx.pg = FakePyAutoGui()
            db_to_xlsx.time.sleep = lambda delay: None
            db_to_xlsx.log_info = lambda event, payload: None

            _hover(FakeWindow(), 1371, 220, "TRACE-HOVER", delay=0.2)
        finally:
            db_to_xlsx.pg = original_pg
            db_to_xlsx.time.sleep = original_sleep
            db_to_xlsx.log_info = original_log_info

        self.assertEqual(calls, [("moveTo", (1371, 220, 0.3))])

    def test_export_steps_use_order_status_and_merge_current_page_without_time_filtering(self) -> None:
        target_path = Path("input") / "销售单查询.xlsx"

        steps = _export_steps(target_path)
        step_names = [step[0] for step in steps]

        self.assertIn("open_order_status_filter", step_names)
        self.assertIn("replace_order_status_keyword", step_names)
        self.assertIn("confirm_order_status_keyword", step_names)
        self.assertIn("apply_left_filters", step_names)
        self.assertIn("hover_merge_export", step_names)
        self.assertIn("click_merge_export_current_page", step_names)
        self.assertIn("wait_save_as_dialog", step_names)
        self.assertIn("replace_save_as_path", step_names)
        self.assertIn("click_save_as_button", step_names)
        self.assertIn("confirm_overwrite_if_present", step_names)
        self.assertNotIn("press_save_as_enter", step_names)
        self.assertNotIn("press_overwrite_yes", step_names)
        self.assertNotIn("press_overwrite_yes_again", step_names)
        self.assertNotIn("click_overwrite_yes", step_names)
        self.assertNotIn("wait_filter_results_stable", step_names)
        self.assertNotIn("open_status_filter", step_names)
        self.assertNotIn("click_export_all_pages", step_names)
        self.assertNotIn("focus_order_time_start", step_names)
        self.assertNotIn("replace_order_time_start", step_names)
        self.assertNotIn("focus_order_time_end", step_names)
        self.assertNotIn("replace_order_time_end", step_names)

        step_by_name = {step[0]: step for step in steps}
        self.assertEqual(step_by_name["open_order_status_filter"][2], (230, 583))
        self.assertEqual(step_by_name["replace_order_status_keyword"][2], "待发货-已递交")
        self.assertEqual(step_by_name["confirm_order_status_keyword"][2], "enter")
        self.assertEqual(step_by_name["apply_left_filters"][2], (68, 933))
        self.assertEqual(step_by_name["apply_left_filters"][3], 9)
        self.assertEqual(step_by_name["hover_merge_export"][2], (1371, 268))
        self.assertEqual(step_by_name["click_merge_export_current_page"][2], (1730, 268))
        self.assertEqual(step_by_name["wait_save_as_dialog"][1], "wait_window")
        self.assertEqual(step_by_name["wait_save_as_dialog"][2], "另存为")
        self.assertEqual(step_by_name["wait_save_as_dialog"][3], 120)
        self.assertEqual(step_by_name["click_save_as_button"][2], (1321, 804))
        self.assertEqual(step_by_name["confirm_overwrite_if_present"][1], "confirm_overwrite")
        save_as_path = Path(str(step_by_name["replace_save_as_path"][2]))
        self.assertTrue(save_as_path.is_absolute())
        self.assertEqual(save_as_path.name, "销售单查询.xlsx")
        self.assertEqual(save_as_path.parent.name, "input")

    def test_export_steps_fill_time_window_when_provided(self) -> None:
        target_path = Path("input") / "销售单查询.xlsx"

        steps = _export_steps(
            target_path,
            start_time=datetime(2026, 5, 21, 9, 30, 0),
            end_time=datetime(2026, 5, 22, 9, 30, 0),
        )
        step_by_name = {step[0]: step for step in steps}

        self.assertEqual(step_by_name["open_statistics_time_type"][2], (230, 418))
        self.assertEqual(step_by_name["replace_statistics_time_type"][2], "复核时间")
        self.assertEqual(step_by_name["confirm_statistics_time_type"][2], "enter")
        self.assertNotIn("select_order_time_type", step_by_name)
        self.assertNotIn("confirm_order_time_type", step_by_name)
        self.assertEqual(step_by_name["focus_order_time_start"][2], (82, 482))
        self.assertEqual(
            step_by_name["replace_order_time_start"][2],
            "2026-05-21 09:30:00",
        )
        self.assertEqual(step_by_name["focus_order_time_end"][2], (82, 520))
        self.assertEqual(
            step_by_name["replace_order_time_end"][2],
            "2026-05-22 09:30:00",
        )
        self.assertEqual(step_by_name["apply_left_filters"][2], (68, 933))
        self.assertEqual(step_by_name["apply_left_filters"][3], 9)

    def test_confirm_overwrite_only_clicks_when_dialog_exists(self) -> None:
        calls: list[tuple[str, object]] = []
        logs: list[tuple[str, dict[str, object]]] = []
        original_gw = db_to_xlsx.gw
        original_pg = db_to_xlsx.pg
        original_sleep = db_to_xlsx.time.sleep
        original_time = db_to_xlsx.time.time
        original_log_info = db_to_xlsx.log_info

        class FakeWindow:
            """Represents the Windows overwrite confirmation dialog."""

            left = 683
            top = 353
            title = "确认另存为"
            isMinimized = False

            def activate(self):
                calls.append(("activate", None))

        class FakeWindows:
            """Provides a deterministic overwrite dialog lookup."""

            def getWindowsWithTitle(self, title):
                return [FakeWindow()] if title == "确认另存为" else []

        class FakePyAutoGui:
            """Captures overwrite confirmation clicks."""

            def moveTo(self, x, y, duration=0):
                calls.append(("moveTo", (x, y, duration)))

            def mouseDown(self):
                calls.append(("mouseDown", None))

            def mouseUp(self):
                calls.append(("mouseUp", None))

            def position(self):
                return (1040, 523)

        try:
            db_to_xlsx.gw = FakeWindows()
            db_to_xlsx.pg = FakePyAutoGui()
            db_to_xlsx.time.sleep = lambda delay: None
            db_to_xlsx.time.time = lambda: 100.0
            db_to_xlsx.log_info = lambda event, payload: logs.append((event, payload))

            confirmed = _confirm_overwrite_if_present("TRACE-SAVE", timeout_seconds=1)
        finally:
            db_to_xlsx.gw = original_gw
            db_to_xlsx.pg = original_pg
            db_to_xlsx.time.sleep = original_sleep
            db_to_xlsx.time.time = original_time
            db_to_xlsx.log_info = original_log_info

        self.assertTrue(confirmed)
        self.assertIn(("moveTo", (1040, 523, 0.2)), calls)
        self.assertEqual(logs[-1][0], "overwrite_confirmed")

    def test_confirm_overwrite_does_not_type_when_dialog_absent(self) -> None:
        calls: list[tuple[str, object]] = []
        now_values = iter([100.0, 100.6, 101.2])
        original_gw = db_to_xlsx.gw
        original_pg = db_to_xlsx.pg
        original_sleep = db_to_xlsx.time.sleep
        original_time = db_to_xlsx.time.time
        original_log_info = db_to_xlsx.log_info

        class FakeWindows:
            """Provides no overwrite confirmation dialog."""

            def getWindowsWithTitle(self, title):
                return []

        class FakePyAutoGui:
            """Fails the test if any keyboard fallback is used."""

            def press(self, key):
                calls.append(("press", key))

            def moveTo(self, x, y, duration=0):
                calls.append(("moveTo", (x, y, duration)))

        try:
            db_to_xlsx.gw = FakeWindows()
            db_to_xlsx.pg = FakePyAutoGui()
            db_to_xlsx.time.sleep = lambda delay: None
            db_to_xlsx.time.time = lambda: next(now_values)
            db_to_xlsx.log_info = lambda event, payload: None

            confirmed = _confirm_overwrite_if_present("TRACE-SAVE", timeout_seconds=1)
        finally:
            db_to_xlsx.gw = original_gw
            db_to_xlsx.pg = original_pg
            db_to_xlsx.time.sleep = original_sleep
            db_to_xlsx.time.time = original_time
            db_to_xlsx.log_info = original_log_info

        self.assertFalse(confirmed)
        self.assertEqual(calls, [])

    def test_wait_for_window_polls_until_dialog_exists(self) -> None:
        calls: list[tuple[str, object]] = []
        logs: list[tuple[str, dict[str, object]]] = []
        now_values = iter([100.0, 100.5, 101.0, 101.5])
        original_gw = db_to_xlsx.gw
        original_sleep = db_to_xlsx.time.sleep
        original_time = db_to_xlsx.time.time
        original_log_info = db_to_xlsx.log_info

        class FakeWindow:
            """Represents a found Windows dialog."""

            title = "另存为"

        class FakeWindows:
            """Returns the dialog after one polling miss."""

            attempts = 0

            def getWindowsWithTitle(self, title):
                calls.append(("lookup", title))
                self.attempts += 1
                return [FakeWindow()] if self.attempts == 2 else []

        try:
            db_to_xlsx.gw = FakeWindows()
            db_to_xlsx.time.sleep = lambda delay: calls.append(("sleep", delay))
            db_to_xlsx.time.time = lambda: next(now_values)
            db_to_xlsx.log_info = lambda event, payload: logs.append((event, payload))

            found = _wait_for_window("另存为", "TRACE-WAIT", timeout_seconds=2)
        finally:
            db_to_xlsx.gw = original_gw
            db_to_xlsx.time.sleep = original_sleep
            db_to_xlsx.time.time = original_time
            db_to_xlsx.log_info = original_log_info

        self.assertTrue(found)
        self.assertEqual(calls, [("lookup", "另存为"), ("sleep", 0.5), ("lookup", "另存为")])
        self.assertEqual(logs[-1][0], "window_wait_found")

    # === MODIFIED END ===
