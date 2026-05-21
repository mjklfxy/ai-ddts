# RPA Jikeyun Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a configurable JackYun RPA XLSX export step.

**Architecture:** Keep pipeline orchestration unchanged. Add config parsing in the application layer, dependency injection in `manual_runner`, and optional execution in `JikeyunClient`.

**Tech Stack:** Python 3.12, unittest, uv, pyautogui.

---

### Task 1: Config Model

**Files:**
- Modify: `application/config_service.py`
- Test: `tests/test_config_service.py`

- [ ] Add a failing test that `rpa.enabled` defaults false and `rpa.xlsx_path` defaults to `input/销售单查询.xlsx`.
- [ ] Add a failing test that explicit RPA config is parsed and serialized.
- [ ] Add `RpaConfig` and include it in `AppConfig`.
- [ ] Parse and serialize the `rpa` section.
- [ ] Run `uv run python -m unittest tests.test_config_service`.

### Task 2: JackYun Client Injection

**Files:**
- Modify: `infrastructure/jikeyun_client.py`
- Test: `tests/test_jikeyun_client.py`

- [ ] Add a failing test that an injected exporter runs before XLSX lookup.
- [ ] Add a failing test that exporter failure does not block order mapping.
- [ ] Add optional `rpa_exporter`, `xlsx_path`, and logger dependencies to `JikeyunClient`.
- [ ] Run the exporter before loading the XLSX lookup and log failures.
- [ ] Run `uv run python -m unittest tests.test_jikeyun_client`.

### Task 3: Application Wiring

**Files:**
- Modify: `application/manual_runner.py`
- Modify: `config/config.json`
- Test: `tests/test_main.py`

- [ ] Add a failing test that `build_jikeyun_client_from_config` injects an exporter when RPA is enabled.
- [ ] Wire `export_orders_to_xlsx` only when `config.rpa.enabled` is true.
- [ ] Set current branch config `rpa.enabled` to true and `rpa.xlsx_path` to `input/销售单查询.xlsx`.
- [ ] Run focused tests for config, client, and main wiring.
