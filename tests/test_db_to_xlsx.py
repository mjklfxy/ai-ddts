from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from datetime import datetime

import infrastructure.db_to_xlsx as db_to_xlsx
from infrastructure.db_to_xlsx import _click, _export_steps, _hover, describe_export_file


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

    def test_export_steps_use_order_status_and_current_page_without_time_filtering(self) -> None:
        target_path = Path("input") / "销售单查询.xlsx"

        steps = _export_steps(target_path)
        step_names = [step[0] for step in steps]

        self.assertIn("open_order_status_filter", step_names)
        self.assertIn("click_export_current_page", step_names)
        self.assertIn("replace_save_as_path", step_names)
        self.assertIn("click_save_as_button", step_names)
        self.assertIn("press_overwrite_yes", step_names)
        self.assertNotIn("open_status_filter", step_names)
        self.assertNotIn("click_export_all_pages", step_names)
        self.assertNotIn("focus_order_time_start", step_names)
        self.assertNotIn("replace_order_time_start", step_names)
        self.assertNotIn("focus_order_time_end", step_names)
        self.assertNotIn("replace_order_time_end", step_names)

        step_by_name = {step[0]: step for step in steps}
        self.assertEqual(step_by_name["open_order_status_filter"][2], (230, 583))
        self.assertEqual(step_by_name["click_export_current_page"][2], (1730, 220))
        self.assertEqual(step_by_name["click_save_as_button"][2], (1321, 804))
        self.assertEqual(step_by_name["press_overwrite_yes"][2], "y")
        self.assertTrue(
            str(step_by_name["replace_save_as_path"][2]).endswith(
                "input\\销售单查询.xlsx"
            )
        )

    def test_export_steps_fill_time_window_when_provided(self) -> None:
        target_path = Path("input") / "销售单查询.xlsx"

        steps = _export_steps(
            target_path,
            start_time=datetime(2026, 5, 21, 9, 30, 0),
            end_time=datetime(2026, 5, 22, 9, 30, 0),
        )
        step_by_name = {step[0]: step for step in steps}

        self.assertEqual(step_by_name["open_statistics_time_type"][2], (230, 418))
        self.assertEqual(step_by_name["select_order_time_type"][2], "home")
        self.assertEqual(step_by_name["confirm_order_time_type"][2], "enter")
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
    # === MODIFIED END ===
