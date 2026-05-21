from __future__ import annotations

from application.manual_runner import RunSummary, run_once
from shared.logging.logger import log_info
from infrastructure.db_to_xlsx import export_orders_to_xlsx

# === MODIFIED START ===
# 原因：FastAPI 接口需要复用手动运行能力，将原 main.py 业务组装迁移到 application.manual_runner。
# 影响范围：main.py 保留为薄 CLI 入口，并继续向旧测试/调用方导出 RunSummary 和 run_once。
if __name__ == "__main__":
    # export_orders_to_xlsx()
    summary = run_once()
    log_info(
        "manual_run_summary",
        {
            "trace_id": summary.trace_id,
            "passed_count": summary.passed_count,
            "ignored_count": summary.ignored_count,
            "error_count": summary.error_count,
            "delivery_count": summary.delivery_count,
            "kingdee_tracking_id": summary.kingdee_tracking_id,
        },
    )
# === MODIFIED END ===
