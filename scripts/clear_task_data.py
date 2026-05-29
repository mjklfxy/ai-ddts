"""清除任务执行痕迹：task_runs.json 和 scheduler_state.json。"""

import json
import os
import sys

OUTPUTS_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs")
TASK_RUNS = os.path.join(OUTPUTS_DIR, "task_runs.json")
SCHEDULER_STATE = os.path.join(OUTPUTS_DIR, "scheduler_state.json")


def clear():
    for path in (TASK_RUNS, SCHEDULER_STATE):
        if path.endswith("task_runs.json"):
            data = "[]"
        else:
            data = json.dumps(
                {"last_run_date": None, "last_run_at": None, "last_trace_id": None, "schedule_runs": {}},
                ensure_ascii=False,
                indent=2,
            ) + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
        print(f"已清空: {os.path.basename(path)}")


if __name__ == "__main__":
    clear()
