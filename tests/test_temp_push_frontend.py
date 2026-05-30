from pathlib import Path
from unittest import TestCase


class TempPushFrontendTests(TestCase):
    """Tests the static temporary push history UI."""

    def test_temp_push_history_uses_task_list_table_layout(self) -> None:
        html = Path("interfaces/static/index.html").read_text(encoding="utf-8")
        section = html.split('id="view-temp-push"', 1)[1]

        self.assertIn('class="panel task-list-panel tp-history-panel"', section)
        self.assertIn('class="table-wrap task-list-table-wrap tp-history-wrap"', section)
        self.assertIn("<th>批次号</th>", section)
        self.assertIn("<th>创建时间</th>", section)
        self.assertIn("<th>订单统计</th>", section)
        self.assertIn("<th>推送状态</th>", section)
        self.assertNotIn("<th>推送数</th>", section)

    def test_temp_push_history_rows_render_task_like_fields(self) -> None:
        js = Path("interfaces/static/app.js").read_text(encoding="utf-8")
        temp_push_render = js.split("async function loadTempPushHistory()", 1)[1].split("function focusRuleEditor", 1)[0]

        self.assertIn("formatDate(item.created_at)", temp_push_render)
        self.assertIn("订单统计", Path("interfaces/static/index.html").read_text(encoding="utf-8"))
        self.assertIn('colspan="6">暂无临时推送记录', temp_push_render)

    # === MODIFIED START ===
    # 原因：正常推送下载按钮应按实际订单明细启用，避免 delivery_count 解析异常时误置灰。
    # 影响范围：临时推送历史表格按钮状态。
    def test_temp_push_normal_download_button_uses_order_count(self) -> None:
        js = Path("interfaces/static/app.js").read_text(encoding="utf-8")
        temp_push_render = js.split("async function loadTempPushHistory()", 1)[1].split("function focusRuleEditor", 1)[0]

        self.assertIn("Number(item.order_count || 0) > 0", temp_push_render)
    # === MODIFIED END ===
