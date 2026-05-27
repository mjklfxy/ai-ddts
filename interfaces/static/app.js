const state = {
  view: "dashboard",
  tasks: [],
  // === MODIFIED START ===
  // 原因：新增执行日志可视化页面，需要缓存最近日志记录。
  // 影响范围：执行日志页面渲染和筛选。
  logs: [],
  // === MODIFIED END ===
  config: null,
  suppliers: [],
  scheduler: null,
  selectedTask: null,
  selectedReceiptTask: null,
  search: "",
  // === MODIFIED START ===
  // 原因：规则配置页改为多项联动面板，需要记录当前选中的配置模块。
  // 影响范围：规则配置 tab 与下方面板联动。
  ruleTab: "warehouse",
  // === MODIFIED END ===
  // === MODIFIED START ===
  // 原因：规则配置中心新增多条定时任务配置，需要在前端维护可编辑草稿。
  // 影响范围：定时任务配置表格、保存配置。
  schedulesDraft: [],
  // === MODIFIED END ===
};

const viewMeta = {
  dashboard: { title: "厂直订单推送工作台", name: "总览" },
  tasks: { title: "任务清单", name: "任务清单" },
  rules: { title: "规则配置中心", name: "规则配置" },
  // === MODIFIED START ===
  // 原因：新增执行日志页面。
  // 影响范围：页面标题与面包屑。
  logs: { title: "执行日志", name: "执行日志" },
  // === MODIFIED END ===
  receipts: { title: "付款回执管理", name: "付款回执" },
};

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  updateClock();
  setInterval(updateClock, 1000);
  loadApp();
});

function bindEvents() {
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  document.querySelectorAll("[data-view-link]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.viewLink));
  });
  document.getElementById("menuButton").addEventListener("click", () => {
    document.body.classList.toggle("menu-open");
  });
  document.getElementById("refreshButton").addEventListener("click", loadApp);
  // === MODIFIED START ===
  // 原因：RPA 桌面导出需要前端可控开关，实时切换 rpa.enabled。
  // 影响范围：顶部操作栏 RPA toggle。
  document.getElementById("rpaToggle").addEventListener("change", toggleRpa);
  // === MODIFIED END ===
  // === MODIFIED START ===
  // 原因：页面顶部删除“立即执行”入口，任务执行改由调度/后端流程触发。
  // 影响范围：前端初始化事件绑定。
  const runTaskButton = document.getElementById("runTaskButton");
  if (runTaskButton) runTaskButton.addEventListener("click", runTask);
  // === MODIFIED END ===
  document.getElementById("saveRulesButton").addEventListener("click", saveRules);
  // === MODIFIED START ===
  // 原因：规则配置页新增手动同步 SKU 群推送人配置按钮。
  // 影响范围：规则配置页顶部操作区。
  document.getElementById("syncSkuGroupCallerConfigsButton").addEventListener("click", syncSkuGroupCallerConfigs);
  // === MODIFIED END ===
  // === MODIFIED START ===
  // 原因：定时任务配置支持在规则配置中心新增多条记录。
  // 影响范围：定时任务配置表格交互。
  document.getElementById("addScheduleButton").addEventListener("click", addScheduleRow);
  // === MODIFIED END ===
  document.getElementById("uploadReceiptButton").addEventListener("click", uploadReceipt);
  document.getElementById("uploadRegionXlsxButton").addEventListener("click", uploadRegionXlsx);
  document.getElementById("uploadSkuGroupXlsxButton").addEventListener("click", uploadSkuGroupXlsx);
  document.getElementById("uploadExcludedSkuXlsxButton").addEventListener("click", uploadExcludedSkuXlsx);
  document.getElementById("drawerCloseButton").addEventListener("click", closeDrawer);
  document.getElementById("globalSearch").addEventListener("input", (event) => {
    state.search = event.target.value.trim().toLowerCase();
    renderAll();
  });
  document.getElementById("taskPushFilter").addEventListener("change", renderTaskTable);
  document.getElementById("taskPaymentFilter").addEventListener("change", renderTaskTable);
  // === MODIFIED START ===
  // 原因：执行日志页面需要支持按任务批次、阶段和结果筛选，并导出当前筛选结果。
  // 影响范围：执行日志页面交互。
  document.getElementById("logTraceFilter").addEventListener("input", renderExecutionLogs);
  document.getElementById("logStageFilter").addEventListener("change", renderExecutionLogs);
  document.getElementById("logResultFilter").addEventListener("change", renderExecutionLogs);
  // === MODIFIED START ===
  // 原因：执行日志展示改为按周期拉取，周期变化需要重新查询后端。
  // 影响范围：执行日志页面交互。
  document.getElementById("logPeriodFilter").addEventListener("change", () => {
    updateLogCustomRangeVisibility();
    refreshExecutionLogs();
  });
  document.getElementById("logStartInput").addEventListener("change", refreshExecutionLogs);
  document.getElementById("logEndInput").addEventListener("change", refreshExecutionLogs);
  // === MODIFIED END ===
  document.getElementById("downloadLogsButton").addEventListener("click", downloadExecutionLogs);
  // === MODIFIED END ===
  document.querySelectorAll("[data-rule-tab]").forEach((button) => {
    // === MODIFIED START ===
    // 原因：规则配置上方入口需要和下方配置面板一一联动。
    // 影响范围：规则配置 tab 点击交互。
    button.addEventListener("click", () => setRuleTab(button.dataset.ruleTab));
    // === MODIFIED END ===
  });
  document.body.addEventListener("click", handleActionClick);
}

async function loadApp() {
  setBusy(true);
  try {
    const [tasks, scheduler, config, suppliers, logs] = await Promise.all([
      api("/tasks/history?limit=50").catch(() => []),
      api("/scheduler/status").catch(() => null),
      api("/config").catch(() => null),
      api("/supplier-mappings").catch(() => ({ items: [] })),
      // === MODIFIED START ===
      // 原因：执行日志默认按周期查询，不再固定拉取最近 100 条。
      // 影响范围：应用初始化数据加载。
      api(`/execution-logs?${buildExecutionLogQuery(false)}`).catch(() => ({ items: [] })),
      // === MODIFIED END ===
    ]);
    state.tasks = Array.isArray(tasks) ? tasks : [];
    state.scheduler = scheduler;
    state.config = config;
    state.suppliers = Array.isArray(suppliers.items) ? suppliers.items : [];
    // === MODIFIED START ===
    // 原因：刷新配置后同步 RPA toggle 状态。
    // 影响范围：顶部 RPA 开关。
    const rpaToggle = document.getElementById("rpaToggle");
    if (rpaToggle && state.config) rpaToggle.checked = !!state.config.rpa?.enabled;
    // === MODIFIED END ===
    // === MODIFIED START ===
    // 原因：执行日志接口返回 items 结构，前端需要落到统一状态。
    // 影响范围：执行日志页面刷新。
    state.logs = Array.isArray(logs.items) ? logs.items : [];
    // === MODIFIED END ===
    updateLogCustomRangeVisibility();
    if (!state.selectedReceiptTask && state.tasks.length) {
      state.selectedReceiptTask = state.tasks[0];
    }
    hydrateRuleInputs();
    // === MODIFIED START ===
    // 原因：刷新配置后保留当前规则配置模块，并确保面板状态和 tab 状态一致。
    // 影响范围：规则配置页刷新后的联动状态。
    setRuleTab(state.ruleTab, false);
    // === MODIFIED END ===
    renderAll();
    showNotice("数据已刷新");
  } catch (error) {
    showNotice(error.message || "数据加载失败", true);
  } finally {
    setBusy(false);
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: options.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...options,
  });
  // === MODIFIED START ===
  // 原因：后台登录态过期后，前端需要回到登录页而不是只显示接口错误。
  // 影响范围：所有通过 api() 发出的后台请求。
  if (response.status === 401) {
    redirectToLogin();
    throw new Error("请先登录后台");
  }
  // === MODIFIED END ===
  if (!response.ok) {
    let detail = `请求失败：${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (_error) {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }
  return response.json();
}

// === MODIFIED START ===
// 原因：后台登录态改为 Cookie，会话过期时需要统一跳回登录页。
// 影响范围：管理台 API 请求和上传请求的未登录处理。
function redirectToLogin() {
  const next = encodeURIComponent("/app");
  window.location.href = `/login?next=${next}`;
}

function handleUnauthorizedResponse(response) {
  if (response.status !== 401) return false;
  redirectToLogin();
  return true;
}
// === MODIFIED END ===

// === MODIFIED START ===
// 原因：执行日志按周期查询，页面切换周期时只刷新日志数据，不重载全部工作台数据。
// 影响范围：执行日志页面数据加载。
async function refreshExecutionLogs() {
  setBusy(true);
  try {
    const payload = await api(`/execution-logs?${buildExecutionLogQuery(false)}`);
    state.logs = Array.isArray(payload.items) ? payload.items : [];
    renderExecutionLogs();
    showNotice("执行日志已刷新");
  } catch (error) {
    showNotice(error.message || "执行日志加载失败", true);
  } finally {
    setBusy(false);
  }
}

function buildExecutionLogQuery(includeCurrentFilters) {
  const params = new URLSearchParams();
  const range = currentLogRange();
  if (range.startAt) params.set("start_at", range.startAt);
  if (range.endAt) params.set("end_at", range.endAt);
  if (includeCurrentFilters) {
    const traceId = document.getElementById("logTraceFilter").value.trim();
    const stage = document.getElementById("logStageFilter").value;
    const result = document.getElementById("logResultFilter").value;
    if (traceId) params.set("trace_id", traceId);
    if (stage) params.set("stage", stage);
    if (result) params.set("result", result);
  }
  return params.toString();
}

function currentLogRange() {
  const period = document.getElementById("logPeriodFilter").value || "7d";
  const now = new Date();
  if (period === "all") return {};
  if (period === "custom") {
    return {
      startAt: datetimeLocalToIso(document.getElementById("logStartInput").value),
      endAt: datetimeLocalToIso(document.getElementById("logEndInput").value),
    };
  }
  if (period === "today") {
    const start = new Date(now);
    start.setHours(0, 0, 0, 0);
    return { startAt: start.toISOString(), endAt: now.toISOString() };
  }
  const hours = period === "24h" ? 24 : period === "30d" ? 24 * 30 : 24 * 7;
  const start = new Date(now.getTime() - hours * 60 * 60 * 1000);
  return { startAt: start.toISOString(), endAt: now.toISOString() };
}

function datetimeLocalToIso(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString();
}

function updateLogCustomRangeVisibility() {
  const isCustom = document.getElementById("logPeriodFilter").value === "custom";
  document.querySelectorAll(".log-custom-range").forEach((input) => {
    input.classList.toggle("is-hidden", !isCustom);
  });
  if (isCustom && !document.getElementById("logStartInput").value && !document.getElementById("logEndInput").value) {
    const now = new Date();
    const start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    document.getElementById("logStartInput").value = toDatetimeLocalValue(start);
    document.getElementById("logEndInput").value = toDatetimeLocalValue(now);
  }
}

function toDatetimeLocalValue(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ].join("-") + `T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
// === MODIFIED END ===

async function runTask() {
  setBusy(true);
  try {
    const result = await api("/tasks/run", { method: "POST" });
    showNotice(`任务已执行：${shortId(result.trace_id)}`);
    await loadApp();
  } catch (error) {
    showNotice(error.message || "任务执行失败", true);
  } finally {
    setBusy(false);
  }
}

// === MODIFIED START ===
// 原因：RPA 桌面导出需要前端可控开关，实时切换 rpa.enabled。
// 影响范围：顶部 RPA 开关。
async function toggleRpa() {
  const toggle = document.getElementById("rpaToggle");
  const enabled = toggle.checked;
  try {
    await api("/config/rpa", {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    });
    state.config.rpa.enabled = enabled;
    showNotice(enabled ? "RPA 已开启（桌面导出+XLSX回填）" : "RPA 已关闭（纯API拉单）");
  } catch (err) {
    toggle.checked = !enabled;
    showNotice(`RPA 开关切换失败：${err.message}`, true);
  }
}
// === MODIFIED END ===

async function saveRules() {
  if (!state.config) {
    showNotice("配置尚未加载完成", true);
    return;
  }
  setBusy(true);
  try {
    const rules = {
      // === MODIFIED START ===
      // 原因：排除库房模块新增总开关，保存时同步写入后端配置。
      // 影响范围：规则配置保存请求。
      excluded_warehouses_enabled: document.getElementById("excludedWarehousesEnabledInput").checked,
      // === MODIFIED END ===
      excluded_warehouses: lines("excludedWarehousesInput"),
      // === MODIFIED START ===
      // 原因：SKU 规则是排除逻辑，不是启用逻辑。
      // 影响范围：规则配置保存请求。
      excluded_skus_enabled: document.getElementById("excludedSkusEnabledInput").checked,
      excluded_skus: lines("excludedSkusInput"),
      // === MODIFIED END ===
      // === MODIFIED START ===
      restricted_regions_enabled: document.getElementById("restrictedRegionsEnabledInput").checked,
      restricted_regions: collectRegionsFromText(),
      sku_group_map_enabled: document.getElementById("skuGroupMapEnabledInput").checked,
      // === MODIFIED END ===
      sku_group_map: parseMap(document.getElementById("skuGroupMapInput").value),
    };
    const supplierItems = parseSuppliers(document.getElementById("supplierMappingsInput").value);
    // === MODIFIED START ===
    // 原因：保存规则配置时同时保存多条定时任务配置，避免 router/API 写业务拼装逻辑。
    // 影响范围：规则配置保存请求。
    const schedules = collectScheduleRows();
    const kingdee = {
      ...(state.config.kingdee || {}),
      // === MODIFIED START ===
      // 原因：保存金蝶推送启用开关，当前默认不启用。
      // 影响范围：规则配置中心保存完整配置。
      enabled: document.getElementById("kingdeeEnabledInput").checked,
      // === MODIFIED END ===
    };
    const config = {
      ...state.config,
      rules,
      kingdee,
      schedules,
      schedule: schedules[0],
    };
    await api("/config", { method: "PUT", body: JSON.stringify(config) });
    // === MODIFIED END ===
    await api("/supplier-mappings", {
      method: "PUT",
      body: JSON.stringify({ items: supplierItems }),
    });
    showNotice("规则配置已保存");
    await loadApp();
  } catch (error) {
    showNotice(error.message || "规则保存失败", true);
  } finally {
    setBusy(false);
  }
}

// === MODIFIED START ===
// 原因：规则配置页需要主动触发 SKU 群推送人配置同步，并把后端返回体反馈给用户。
// 影响范围：规则配置页同步按钮。
async function syncSkuGroupCallerConfigs() {
  setBusy(true);
  try {
    const result = await api("/config/sku-groups/sync-caller-configs", { method: "POST" });
    if (result.status === "success") {
      const remote = result.remote_response || {};
      showNotice(`同步完成：${remote.synced ?? result.count ?? 0} 条`);
    } else if (result.status === "skipped") {
      showNotice(`同步跳过：${result.reason || "未配置同步地址"}`, true);
    } else {
      showNotice(`同步失败：${result.reason || "请查看执行日志"}`, true);
    }
  } catch (error) {
    showNotice(error.message || "同步失败", true);
  } finally {
    setBusy(false);
  }
}
// === MODIFIED END ===

async function uploadReceipt() {
  if (!state.selectedReceiptTask) {
    showNotice("请先选择一个任务", true);
    return;
  }
  const input = document.getElementById("receiptFileInput");
  if (!input.files || !input.files[0]) {
    showNotice("请选择付款凭证文件", true);
    return;
  }
  const formData = new FormData();
  formData.append("file", input.files[0]);
  setBusy(true);
  try {
    const result = await api(`/tasks/${encodeURIComponent(state.selectedReceiptTask.trace_id)}/payment-receipt`, {
      method: "POST",
      body: formData,
    });
    document.getElementById("recentUploadInfo").textContent = `${result.original_filename} 已上传`;
    input.value = "";
    showNotice("付款回执已上传");
    await loadApp();
  } catch (error) {
    showNotice(error.message || "付款回执上传失败", true);
  } finally {
    setBusy(false);
  }
}

function renderAll() {
  renderMetrics();
  renderDashboardTasks();
  renderRuleOverview();
  renderTaskTable();
  renderExecutionLogs();
  renderReceiptTable();
  renderSelectedReceiptTask();
}

function setView(view) {
  state.view = view;
  const meta = viewMeta[view] || viewMeta.dashboard;
  document.getElementById("pageTitle").textContent = meta.title;
  document.getElementById("currentViewName").textContent = meta.name;
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("is-active", item.dataset.view === view);
  });
  document.querySelectorAll(".view").forEach((section) => {
    section.classList.toggle("is-active", section.id === `view-${view}`);
  });
  document.body.classList.remove("menu-open");
  closeDrawer();
}

// === MODIFIED START ===
// 原因：规则配置页需要通过多个入口切换对应的单一配置面板。
// 影响范围：规则配置 tab、面板显示和输入焦点。
function setRuleTab(tab, shouldFocus = true) {
  const knownTabs = ["warehouse", "sku", "region", "group", "supplier", "schedule"];
  const nextTab = knownTabs.includes(tab) ? tab : "warehouse";
  state.ruleTab = nextTab;
  document.querySelectorAll("[data-rule-tab]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.ruleTab === nextTab);
  });
  document.querySelectorAll("[data-rule-panel]").forEach((panel) => {
    panel.classList.toggle("is-active", panel.dataset.rulePanel === nextTab);
  });
  if (shouldFocus) focusRuleEditor(nextTab);
}
// === MODIFIED END ===

function renderMetrics() {
  const totals = summarizeTasks();
  const metrics = [
    // === MODIFIED START ===
    // 原因：工作台指标角标统一改为中文，避免页面按键/标识混用英文缩写。
    // 影响范围：工作台指标卡展示。
    { label: "抓取订单", value: totals.orders, foot: "最近任务合计", color: "blue", mark: "订" },
    { label: "正常推送", value: totals.deliveries, foot: "已生成推送批次", color: "green", mark: "推" },
    { label: "异常订单", value: totals.errors, foot: "规则失败或推送失败", color: "orange", mark: "异" },
    { label: "待付款任务", value: totals.unpaid, foot: "以回执判断付款", color: "purple", mark: "款" },
    // === MODIFIED END ===
  ];
  document.getElementById("dashboardMetrics").innerHTML = metrics
    .map(
      (item) => `
        <article class="metric-card">
          <div class="metric-dot ${item.color}">${item.mark}</div>
          <div class="metric-label">${escapeHtml(item.label)}</div>
          <div class="metric-value">${formatNumber(item.value)}</div>
          <div class="metric-foot">${escapeHtml(item.foot)}</div>
        </article>
      `,
    )
    .join("");
}

function renderDashboardTasks() {
  const tasks = filteredTasks().slice(0, 8);
  document.getElementById("dashboardTaskRows").innerHTML = tableRows(
    tasks,
    (task) => `
      <tr>
        <td>${shortId(task.trace_id)}</td>
        <!-- === MODIFIED START ===
        原因：任务概览只保留任务批次作为每次运行的唯一识别字段。
        影响范围：工作台任务概览行渲染。
        === MODIFIED END === -->
        <td>${statusBadge(task.push_status)}</td>
        <td>${statusBadge(task.kingdee_status)}</td>
        <td>${statusBadge(task.payment_status)}</td>
        <td>${formatNumber(task.error_count || 0)}</td>
        <td>${taskActions(task)}</td>
      </tr>
    `,
    6,
  );
}

function renderTaskTable() {
  const pushFilter = document.getElementById("taskPushFilter").value;
  const paymentFilter = document.getElementById("taskPaymentFilter").value;
  const tasks = filteredTasks().filter((task) => {
    if (pushFilter && task.push_status !== pushFilter) return false;
    if (paymentFilter && task.payment_status !== paymentFilter) return false;
    return true;
  });
  document.getElementById("taskRows").innerHTML = tableRows(
    tasks,
    (task) => `
      <tr>
        <td>${shortId(task.trace_id)}</td>
        <td>${formatDate(task.created_at)}</td>
        <td>通过 ${task.passed_count || 0} / 异常 ${task.error_count || 0} / 忽略 ${task.ignored_count || 0}</td>
        <td>${statusBadge(task.push_status)}</td>
        <td>${statusBadge(task.kingdee_status)}</td>
        <td>${statusBadge(task.payment_status)}</td>
        <td>${taskActions(task)}</td>
      </tr>
    `,
    7,
  );
}

// === MODIFIED START ===
// 原因：执行日志页面改为按批次分组的阶段时间线。
// 影响范围：执行日志页面。
function renderExecutionLogs() {
  const logs = filteredExecutionLogs();
  updateExecutionLogFilterStatus(logs.length);
  const target = document.getElementById("logRows");
  if (!logs.length) {
    target.innerHTML = `<div class="empty-row log-empty">暂无数据</div>`;
    return;
  }
  target.innerHTML = groupExecutionLogs(logs).map(renderExecutionLogGroup).join("");
}

function filteredExecutionLogs() {
  const traceFilter = document.getElementById("logTraceFilter").value.trim().toLowerCase();
  const stageFilter = document.getElementById("logStageFilter").value;
  const resultFilter = document.getElementById("logResultFilter").value;
  return (state.logs || []).filter((item) => {
    if (traceFilter && !String(item.trace_id || "").toLowerCase().includes(traceFilter)) return false;
    if (stageFilter && item.stage !== stageFilter) return false;
    if (resultFilter && item.result !== resultFilter) return false;
    if (!state.search) return true;
    const haystack = [
      item.trace_id,
      item.stage,
      item.result,
      item.summary,
      item.impact,
      item.suggestion,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(state.search);
  });
}

// === MODIFIED START ===
// 原因：执行日志筛选为自动生效，需要在筛选区展示当前周期和结果数量。
// 影响范围：执行日志筛选状态提示。
function updateExecutionLogFilterStatus(count) {
  const status = document.getElementById("logFilterStatus");
  if (!status) return;
  status.textContent = `已自动筛选 · 当前${currentLogPeriodLabel()} · 共 ${formatNumber(count)} 条`;
}

function currentLogPeriodLabel() {
  const select = document.getElementById("logPeriodFilter");
  const option = select && select.selectedOptions ? select.selectedOptions[0] : null;
  return option ? option.textContent.trim() : "近 7 天";
}
// === MODIFIED END ===

function downloadExecutionLogs() {
  const query = buildExecutionLogQuery(true);
  window.location.href = query ? `/execution-logs/download?${query}` : "/execution-logs/download";
}

function groupExecutionLogs(logs) {
  const groups = new Map();
  logs.forEach((item) => {
    const traceId = item.trace_id || "未关联批次";
    if (!groups.has(traceId)) {
      groups.set(traceId, {
        trace_id: traceId,
        task_name: item.task_name || "",
        items: [],
      });
    }
    const group = groups.get(traceId);
    if (!group.task_name && item.task_name) group.task_name = item.task_name;
    group.items.push(item);
  });
  return Array.from(groups.values())
    .map((group) => ({
      ...group,
      items: group.items.slice().sort(compareExecutionLogs),
      latest_at: latestLogTime(group.items),
    }))
    .sort((left, right) => new Date(right.latest_at || 0) - new Date(left.latest_at || 0));
}

function renderExecutionLogGroup(group) {
  const counts = summarizeExecutionLogGroup(group.items);
  return `
    <article class="log-group">
      <div class="log-group-head">
        <div>
          <span class="log-batch">${escapeHtml(group.trace_id)}</span>
          <!-- === MODIFIED START ===
          原因：内部任务类型不对业务用户展示，执行日志按任务批次识别即可。
          影响范围：执行日志批次标题。
          === MODIFIED END === -->
          <h3>任务执行记录</h3>
          <p>最近记录：${formatDate(group.latest_at)}</p>
        </div>
        <div class="log-group-summary">
          ${statusBadge(counts.result)}
          <span>${counts.total} 条记录</span>
        </div>
      </div>
      <div class="log-step-list">
        ${group.items.map(renderExecutionLogItem).join("")}
      </div>
    </article>
  `;
}

function renderExecutionLogItem(item) {
  return `
    <div class="log-step ${logStepClass(item.result)}">
      <div class="log-step-marker" aria-hidden="true"></div>
      <div class="log-step-content">
        <div class="log-step-title">
          <strong>${escapeHtml(item.stage || "--")}</strong>
          ${statusBadge(item.result)}
          <time>${formatDate(item.created_at)}</time>
        </div>
        <p>${escapeHtml(item.summary || "--")}</p>
        <!-- === MODIFIED START ===
        原因：单条执行记录需要支持收起/展开详细信息，避免批次时间线默认占用过多纵向空间。
        影响范围：执行日志单条记录渲染。
        === MODIFIED END === -->
        <details class="log-step-details">
          <summary>
            <span class="log-step-toggle-icon" aria-hidden="true"></span>
            <span>详细信息</span>
          </summary>
          <div class="log-step-meta">
            <div>
              <span>影响</span>
              <strong>${escapeHtml(item.impact || "--")}</strong>
            </div>
            <div>
              <span>建议</span>
              <strong>${escapeHtml(item.suggestion || "--")}</strong>
            </div>
            ${renderExecutionLogDetails(item.details)}
          </div>
        </details>
        <!-- === MODIFIED END === -->
      </div>
    </div>
  `;
}

// === MODIFIED START ===
// 原因：执行日志后端可能携带结构化 details，展开区需要以可读方式展示。
// 影响范围：执行日志单条记录详细信息。
function renderExecutionLogDetails(details) {
  if (!details || typeof details !== "object" || Array.isArray(details) || !Object.keys(details).length) {
    return "";
  }
  return `
    <div class="log-step-detail-json">
      <span>详情</span>
      <strong>${escapeHtml(JSON.stringify(details, null, 2))}</strong>
    </div>
  `;
}
// === MODIFIED END ===

function summarizeExecutionLogGroup(items) {
  const total = items.length;
  if (items.some((item) => item.result === "失败")) return { total, result: "失败" };
  if (items.some((item) => item.result === "部分成功")) return { total, result: "部分成功" };
  if (items.every((item) => item.result === "跳过")) return { total, result: "跳过" };
  return { total, result: "成功" };
}

function compareExecutionLogs(left, right) {
  const leftTime = new Date(left.created_at || 0).getTime();
  const rightTime = new Date(right.created_at || 0).getTime();
  if (!Number.isNaN(leftTime) && !Number.isNaN(rightTime) && leftTime !== rightTime) {
    return leftTime - rightTime;
  }
  return executionLogRank(left) - executionLogRank(right);
}

function executionLogRank(item) {
  if (item.stage === "任务" && String(item.summary || "").includes("开始")) return 0;
  if (item.stage === "任务" && String(item.summary || "").includes("完成")) return 60;
  const ranks = {
    抓单: 10,
    规则判断: 20,
    生成文件: 30,
    推送群: 40,
    金蝶: 50,
    回执: 70,
  };
  return ranks[item.stage] || 90;
}

function latestLogTime(items) {
  return items
    .map((item) => item.created_at)
    .filter(Boolean)
    .sort((left, right) => new Date(right) - new Date(left))[0];
}

function logStepClass(result) {
  if (result === "失败") return "is-failed";
  if (result === "部分成功") return "is-partial";
  if (result === "跳过") return "is-skipped";
  return "is-success";
}
// === MODIFIED END ===

function renderReceiptTable() {
  const tasks = filteredTasks();
  document.getElementById("receiptRows").innerHTML = tableRows(
    tasks,
    (task) => `
      <tr>
        <td>${shortId(task.trace_id)}</td>
        <td>${statusBadge(task.kingdee_status)}</td>
        <td>${statusBadge(task.payment_status)}</td>
        <td>
          <div class="row-actions">
            <button type="button" data-action="select-receipt" data-trace="${escapeAttr(task.trace_id)}">选择</button>
            <button type="button" data-action="detail" data-trace="${escapeAttr(task.trace_id)}">详情</button>
          </div>
        </td>
      </tr>
    `,
    4,
  );
}

function renderRuleOverview() {
  const config = state.config || {};
  const rules = config.rules || {};
  const kingdee = config.kingdee || {};
  // === MODIFIED START ===
  // 原因：规则概览同步展示各规则模块启用状态，并补齐 SKU 供应商对照为第 5 项。
  // 影响范围：规则引擎概览卡片。
  const warehouseEnabled = Boolean(rules.excluded_warehouses_enabled);
  const skuExclusionEnabled = Boolean(rules.excluded_skus_enabled);
  const regionEnabled = Boolean(rules.restricted_regions_enabled);
  const groupEnabled = Boolean(rules.sku_group_map_enabled);
  const items = [
    {
      label: "排除库房",
      value: (rules.excluded_warehouses || []).length,
      foot: warehouseEnabled ? "命中后忽略订单" : "未启用，不应用排除库房",
      mark: "WH",
    },
    {
      label: "排除SKU",
      value: (rules.excluded_skus || []).length,
      foot: skuExclusionEnabled ? "SKU=商品名称，命中后忽略" : "未启用，不应用排除SKU",
      mark: "SK",
    },
    {
      label: "限发区域",
      value: (rules.restricted_regions || []).length,
      foot: regionEnabled ? "命中后整单异常" : "未启用，不应用限发区域",
      mark: "RG",
    },
    {
      label: "SKU群配置",
      value: Object.keys(rules.sku_group_map || {}).length,
      foot: groupEnabled ? "未配置群进入异常" : "未启用，不检查缺失群",
      mark: "GP",
    },
    {
      label: "SKU供应商对照",
      value: (state.suppliers || []).length,
      foot: kingdee.enabled ? "缺失供应商影响金蝶" : "金蝶未启用，仅保存对照",
      mark: "SP",
    },
  ];
  // === MODIFIED END ===
  document.getElementById("ruleOverview").innerHTML = items
    .map(
      (item) => `
        <div class="rule-card">
          <div class="rule-card-icon">${item.mark}</div>
          <div>
            <strong>${escapeHtml(item.label)}</strong>
            <p>${escapeHtml(item.foot)}</p>
          </div>
          <strong>${formatNumber(item.value)}</strong>
        </div>
      `,
    )
    .join("");
}

function renderSelectedReceiptTask() {
  const label = document.getElementById("selectedReceiptTask");
  if (!state.selectedReceiptTask) {
    label.textContent = "请选择左侧任务";
    return;
  }
  label.textContent = `当前任务：${shortId(state.selectedReceiptTask.trace_id)}，${state.selectedReceiptTask.payment_status || "未付款"}`;
}

function hydrateRuleInputs() {
  if (!state.config) return;
  const rules = state.config.rules || {};
  // === MODIFIED START ===
  // 原因：排除库房模块新增总开关，加载配置时需要回填当前启用状态。
  // 影响范围：规则配置表单回填。
  document.getElementById("excludedWarehousesEnabledInput").checked = Boolean(rules.excluded_warehouses_enabled);
  // === MODIFIED END ===
  document.getElementById("excludedWarehousesInput").value = (rules.excluded_warehouses || []).join("\n");
  // === MODIFIED START ===
  // 原因：排除 SKU 新增模块级开关，且列表字段迁移为 excluded_skus；兼容旧 enabled_skus 返回。
  // 影响范围：规则配置表单回填。
  document.getElementById("excludedSkusEnabledInput").checked = Boolean(rules.excluded_skus_enabled);
  document.getElementById("excludedSkusInput").value = (rules.excluded_skus || rules.enabled_skus || []).join("\n");
  // === MODIFIED END ===
  document.getElementById("restrictedRegionsEnabledInput").checked = Boolean(rules.restricted_regions_enabled);
  renderRegionGroups(rules.restricted_regions || []);
  document.getElementById("skuGroupMapEnabledInput").checked = Boolean(rules.sku_group_map_enabled);
  // === MODIFIED END ===
  document.getElementById("skuGroupMapInput").value = Object.entries(rules.sku_group_map || {})
    .map(([sku, info]) => {
      const gn = typeof info === "string" ? info : (info.group_name || "");
      const om = typeof info === "string" ? "" : (info.owner_mobile || "");
      return om ? `${sku},${gn},${om}` : `${sku},${gn}`;
    })
    .join("\n");
  document.getElementById("supplierMappingsInput").value = (state.suppliers || [])
    // === MODIFIED START ===
    // 原因：SKU-供应商对照不再维护供应商编码，页面只展示商品名称与供应商名称。
    // 影响范围：规则配置中心供应商对照回填。
    .map((item) => [item.sku_code, item.supplier_name].join(","))
    // === MODIFIED END ===
    .join("\n");
  // === MODIFIED START ===
  // 原因：加载配置时回填金蝶推送启用开关。
  // 影响范围：规则配置中心 SKU 供应商对照面板。
  document.getElementById("kingdeeEnabledInput").checked = Boolean((state.config.kingdee || {}).enabled);
  // === MODIFIED END ===
  // === MODIFIED START ===
  // 原因：配置中心新增多条定时任务配置，需要从 /config 回填到可编辑表格。
  // 影响范围：规则配置表单回填。
  const schedules = Array.isArray(state.config.schedules) && state.config.schedules.length
    ? state.config.schedules
    : state.config.schedule
      ? [state.config.schedule]
      : [];
  state.schedulesDraft = schedules.map((item, index) => ({
    schedule_id: item.schedule_id || `schedule-${index + 1}`,
    name: item.name || `定时任务${index + 1}`,
    enabled: Boolean(item.enabled),
    run_at: item.run_at || "09:00",
    check_interval_seconds: Number(item.check_interval_seconds || 60),
  }));
  if (state.schedulesDraft.length === 0) {
    state.schedulesDraft = [defaultScheduleRow()];
  }
  renderScheduleRows();
  // === MODIFIED END ===
}

async function openDrawer(task) {
  state.selectedTask = task;
  const payment = await api(`/tasks/${encodeURIComponent(task.trace_id)}/payment`).catch(() => null);
  const content = document.getElementById("drawerContent");
  content.innerHTML = `
    <div class="drawer-title">
      <h2>任务详情 ${shortId(task.trace_id)}</h2>
      <p>${escapeHtml(task.trace_id)}</p>
    </div>
    <div class="detail-grid">
      ${detailCell("推送状态", statusBadge(task.push_status))}
      ${detailCell("金蝶状态", statusBadge(task.kingdee_status))}
      ${detailCell("付款状态", statusBadge(task.payment_status))}
      ${detailCell("金蝶追踪号", escapeHtml(task.kingdee_tracking_id || "--"))}
      ${detailCell("通过订单", formatNumber(task.passed_count || 0))}
      ${detailCell("异常订单", formatNumber(task.error_count || 0))}
      ${detailCell("忽略订单", formatNumber(task.ignored_count || 0))}
      ${detailCell("推送批次", formatNumber(task.delivery_count || 0))}
    </div>
    <div class="panel-head">
      <div>
        <h2>状态时间线</h2>
        <p>${escapeHtml(task.failure_reason || "暂无失败原因")}</p>
      </div>
    </div>
    <div class="timeline">
      ${timelineItem("任务创建", formatDate(task.created_at))}
      ${timelineItem("订单窗口开始", formatDate(task.window_start))}
      ${timelineItem("订单窗口结束", formatDate(task.window_end))}
      ${timelineItem(`推送状态：${task.push_status || "--"}`, task.failure_stage === "message_push" ? task.failure_reason : "")}
      ${timelineItem(`金蝶状态：${task.kingdee_status || "--"}`, task.failure_stage === "kingdee_submit" ? task.failure_reason : "")}
      ${timelineItem(`付款状态：${task.payment_status || "--"}`, payment && payment.uploaded_at ? formatDate(payment.uploaded_at) : "等待上传回执")}
    </div>
  `;
  document.getElementById("detailDrawer").classList.add("is-open");
}

function closeDrawer() {
  document.getElementById("detailDrawer").classList.remove("is-open");
}

function handleActionClick(event) {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  // === MODIFIED START ===
  // 原因：定时任务配置表格删除按钮不是任务行操作，需要先处理。
  // 影响范围：页面全局 action 点击分发。
  if (target.dataset.action === "remove-schedule") {
    removeScheduleRow(Number(target.dataset.index));
    return;
  }
  // === MODIFIED END ===
  const task = state.tasks.find((item) => item.trace_id === target.dataset.trace);
  if (!task) return;
  // === MODIFIED START ===
  // 原因：下载入口需要页面反馈，避免浏览器静默下载时用户误以为按钮无效。
  // 影响范围：任务行下载操作。
  if (target.dataset.action === "download-exceptions") {
    startTaskDownload(task, "exceptions");
    return;
  }
  if (target.dataset.action === "download-pushed") {
    startTaskDownload(task, "pushed");
    return;
  }
  // === MODIFIED END ===
  // === MODIFIED START ===
  // 原因：任务清单新增复推按钮，按原时间窗口重新拉单+RPA+推送。
  // 影响范围：任务行复推操作。
  if (target.dataset.action === "repush") {
    repushTask(task);
    return;
  }
  // === MODIFIED END ===
  if (target.dataset.action === "detail") {
    openDrawer(task);
  }
  if (target.dataset.action === "select-receipt") {
    state.selectedReceiptTask = task;
    renderSelectedReceiptTask();
    setView("receipts");
  }
}

// === MODIFIED START ===
// 原因：CSV 下载本身不会改变页面状态，需要显式提示用户已开始下载。
// 影响范围：任务清单下载交互。
function startTaskDownload(task, kind) {
  const trace = encodeURIComponent(task.trace_id || "");
  if (kind === "exceptions") {
    if (Number(task.error_count || 0) <= 0) {
      showNotice("当前任务没有异常订单", true);
      return;
    }
    showNotice(`正在下载异常订单：${shortId(task.trace_id)}`);
    triggerDownload(`/exception-orders/download?trace_id=${trace}`);
    return;
  }
  if (Number(task.delivery_count || 0) <= 0) {
    showNotice("当前任务没有正常推送订单", true);
    return;
  }
  showNotice(`正在下载正常推送订单：${shortId(task.trace_id)}`);
  triggerDownload(`/tasks/${trace}/pushed-orders/download`);
}

function triggerDownload(url) {
  const link = document.createElement("a");
  link.href = url;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
}
// === MODIFIED END ===

// === MODIFIED START ===
// 原因：任务清单新增复推按钮，按原时间窗口重新拉单+RPA+推送。
// 影响范围：任务行复推操作。
async function repushTask(task) {
  const trace = encodeURIComponent(task.trace_id || "");
  if (!task.window_start || !task.window_end) {
    showNotice("当前任务缺少时间窗口信息，无法复推", true);
    return;
  }
  const ok = confirm(`确认用原时间窗口复推？\n\n时间窗口：${task.window_start} → ${task.window_end}`);
  if (!ok) return;
  showNotice(`正在复推：${shortId(task.trace_id)}...`);
  try {
    const result = await api(`/tasks/${trace}/repush`, { method: "POST" });
    showNotice(`复推完成：${shortId(result.trace_id)}，通过 ${result.passed_count || 0} 单`);
    loadApp();
  } catch (err) {
    showNotice(`复推失败：${err.message}`, true);
  }
}
// === MODIFIED END ===

function focusRuleEditor(tab) {
  const map = {
    warehouse: "excludedWarehousesInput",
    // === MODIFIED START ===
    // 原因：SKU tab 聚焦排除 SKU 输入框。
    // 影响范围：规则配置 tab 交互。
    sku: "excludedSkusInput",
    // === MODIFIED END ===
    region: "regionTextInput",
    group: "skuGroupMapInput",
    // === MODIFIED START ===
    // 原因：规则配置联动项新增 SKU 供应商对照。
    // 影响范围：供应商对照 tab 焦点。
    supplier: "supplierMappingsInput",
    // === MODIFIED END ===
    // === MODIFIED START ===
    // 原因：规则配置中心新增定时任务配置面板。
    // 影响范围：定时任务 tab 焦点。
    schedule: "scheduleRows",
    // === MODIFIED END ===
  };
  const target = document.getElementById(map[tab]);
  if (!target) return;
  target.focus();
}

// === MODIFIED START ===
// 原因：规则配置中心新增多条定时任务配置，需要前端表格增删改和保存前校验。
// 影响范围：定时任务配置面板。
function renderScheduleRows() {
  const rows = state.schedulesDraft || [];
  document.getElementById("scheduleRows").innerHTML = tableRows(
    rows,
    (item, index) => `
      <tr>
        <td>
          <input class="schedule-input" data-schedule-field="schedule_id" data-index="${index}" value="${escapeAttr(item.schedule_id)}" />
        </td>
        <td>
          <input class="schedule-input" data-schedule-field="name" data-index="${index}" value="${escapeAttr(item.name)}" />
        </td>
        <td>
          <label class="toggle-row compact">
            <input data-schedule-field="enabled" data-index="${index}" type="checkbox" ${item.enabled ? "checked" : ""} />
            <span class="switch" aria-hidden="true"></span>
          </label>
        </td>
        <td>
          <input class="schedule-input" data-schedule-field="run_at" data-index="${index}" value="${escapeAttr(item.run_at)}" placeholder="09:00" />
        </td>
        <td>
          <input class="schedule-input" data-schedule-field="check_interval_seconds" data-index="${index}" type="number" min="1" step="1" value="${escapeAttr(item.check_interval_seconds)}" />
        </td>
        <td>
          <button type="button" data-action="remove-schedule" data-index="${index}">删除</button>
        </td>
      </tr>
    `,
    6,
  );
  document.querySelectorAll("[data-schedule-field]").forEach((input) => {
    input.addEventListener("input", handleScheduleFieldChange);
    input.addEventListener("change", handleScheduleFieldChange);
  });
}

function addScheduleRow() {
  state.schedulesDraft.push({
    ...defaultScheduleRow(),
    schedule_id: nextScheduleId(),
    name: `定时任务${state.schedulesDraft.length + 1}`,
  });
  renderScheduleRows();
}

function removeScheduleRow(index) {
  if (!Number.isInteger(index) || index < 0 || index >= state.schedulesDraft.length) return;
  state.schedulesDraft.splice(index, 1);
  if (state.schedulesDraft.length === 0) {
    state.schedulesDraft.push(defaultScheduleRow());
  }
  renderScheduleRows();
}

function handleScheduleFieldChange(event) {
  const index = Number(event.target.dataset.index);
  const field = event.target.dataset.scheduleField;
  if (!Number.isInteger(index) || !state.schedulesDraft[index] || !field) return;
  if (field === "enabled") {
    state.schedulesDraft[index][field] = event.target.checked;
    return;
  }
  if (field === "check_interval_seconds") {
    state.schedulesDraft[index][field] = Number(event.target.value || 0);
    return;
  }
  state.schedulesDraft[index][field] = event.target.value;
}

function collectScheduleRows() {
  const rows = (state.schedulesDraft || [])
    .map((item) => ({
      schedule_id: String(item.schedule_id || "").trim(),
      name: String(item.name || "").trim(),
      enabled: Boolean(item.enabled),
      run_at: String(item.run_at || "").trim(),
      check_interval_seconds: Number(item.check_interval_seconds || 0),
    }))
    .filter((item) => item.schedule_id || item.name || item.run_at);

  const schedules = rows.length ? rows : [defaultScheduleRow()];
  const seen = new Set();
  schedules.forEach((item, index) => {
    if (!item.schedule_id) throw new Error(`第 ${index + 1} 条定时任务缺少配置ID`);
    if (!item.name) throw new Error(`第 ${index + 1} 条定时任务缺少名称`);
    item.run_at = normalizeRunAt(item.run_at, index);
    if (!Number.isInteger(item.check_interval_seconds) || item.check_interval_seconds < 1) {
      throw new Error(`第 ${index + 1} 条定时任务检查间隔必须是正整数`);
    }
    if (seen.has(item.schedule_id)) throw new Error(`定时任务配置ID重复：${item.schedule_id}`);
    seen.add(item.schedule_id);
  });
  return schedules;
}

function normalizeRunAt(value, index) {
  const parts = String(value || "").trim().split(":");
  if (parts.length !== 2 || !/^\d{1,2}$/.test(parts[0]) || !/^\d{1,2}$/.test(parts[1])) {
    throw new Error(`第 ${index + 1} 条定时任务运行时间必须是 HH:MM`);
  }
  const hour = Number(parts[0]);
  const minute = Number(parts[1]);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
    throw new Error(`第 ${index + 1} 条定时任务运行时间必须是有效时间`);
  }
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function defaultScheduleRow() {
  return {
    schedule_id: "default",
    name: "默认定时任务",
    enabled: false,
    run_at: "09:00",
    check_interval_seconds: 60,
  };
}

function nextScheduleId() {
  const existing = new Set((state.schedulesDraft || []).map((item) => item.schedule_id));
  let index = state.schedulesDraft.length + 1;
  let candidate = `schedule-${index}`;
  while (existing.has(candidate)) {
    index += 1;
    candidate = `schedule-${index}`;
  }
  return candidate;
}
// === MODIFIED END ===

function filteredTasks() {
  if (!state.search) return state.tasks;
  return state.tasks.filter((task) => {
    const haystack = [
      task.trace_id,
      task.push_status,
      task.kingdee_status,
      task.payment_status,
      task.failure_reason,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(state.search);
  });
}

function summarizeTasks() {
  return state.tasks.reduce(
    (sum, task) => {
      sum.orders += (task.passed_count || 0) + (task.ignored_count || 0) + (task.error_count || 0);
      sum.deliveries += task.delivery_count || 0;
      sum.errors += task.error_count || 0;
      if (task.payment_status === "未付款") sum.unpaid += 1;
      return sum;
    },
    { orders: 0, deliveries: 0, errors: 0, unpaid: 0 },
  );
}

function taskActions(task) {
  // === MODIFIED START ===
  // 原因：任务清单下载需要区分异常订单和正常推送订单明细。
  // 影响范围：任务行操作按钮。
  const exceptionDownload = Number(task.error_count || 0) > 0
    ? `<button type="button" data-action="download-exceptions" data-trace="${escapeAttr(task.trace_id)}">异常订单</button>`
    : `<span class="action-disabled" title="当前任务没有异常订单">异常订单</span>`;
  const pushedDownload = Number(task.delivery_count || 0) > 0
    ? `<button type="button" data-action="download-pushed" data-trace="${escapeAttr(task.trace_id)}">正常推送订单</button>`
    : `<span class="action-disabled" title="当前任务没有正常推送订单">正常推送订单</span>`;
  // === MODIFIED END ===
  return `
    <div class="row-actions">
      <button type="button" data-action="detail" data-trace="${escapeAttr(task.trace_id)}">详情</button>
      <button type="button" data-action="select-receipt" data-trace="${escapeAttr(task.trace_id)}">回执</button>
      <!-- === MODIFIED START ===
      原因：任务清单下载拆分为当前批次异常订单与正常推送订单明细。
      影响范围：任务行操作按钮。
      === MODIFIED END === -->
      ${exceptionDownload}
      ${pushedDownload}
      <button type="button" data-action="repush" data-trace="${escapeAttr(task.trace_id)}">复推</button>
    </div>
  `;
}

function tableRows(items, mapper, colspan) {
  if (!items || items.length === 0) {
    return `<tr><td class="empty-row" colspan="${colspan}">暂无数据</td></tr>`;
  }
  return items.map(mapper).join("");
}

function statusBadge(value) {
  const text = value || "--";
  const color = statusColor(text);
  return `<span class="status ${color}">${escapeHtml(text)}</span>`;
}

function statusColor(value) {
  if (["已推送", "已付款", "采购申请单已提交", "已提交", "成功"].includes(value)) return "green";
  // === MODIFIED START ===
  // 原因：部分推送代表需要用户查看详情的提醒状态，不等同于完全失败。
  // 影响范围：任务清单与详情抽屉状态徽标颜色。
  if (["未付款", "采购申请单待提交", "部分推送", "部分成功"].includes(value)) return "orange";
  // === MODIFIED END ===
  if (["推送失败", "采购申请单提交失败", "异常待处理", "失败"].includes(value)) return "red";
  if (["待推送", "待提交"].includes(value)) return "blue";
  return "gray";
}

function detailCell(label, value) {
  return `
    <div class="detail-cell">
      <span>${escapeHtml(label)}</span>
      <strong>${value}</strong>
    </div>
  `;
}

function timelineItem(title, detail) {
  return `
    <div class="timeline-item">
      <strong>${escapeHtml(title)}</strong>
      <small>${escapeHtml(detail || "--")}</small>
    </div>
  `;
}

function lines(id) {
  return document
    .getElementById(id)
    .value.split(/\r?\n|;/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function parseMap(value) {
  const result = {};
  value
    .split(/\r?\n|;/)
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const parts = splitCsvLine(line);
      const sku = parts[0];
      const groupName = parts[1];
      const ownerMobile = parts[2] || "";
      if (sku && groupName) {
        result[sku] = { group_name: groupName, owner_mobile: ownerMobile };
      }
    });
  return result;
}

function renderRegionGroups(regions) {
  const textarea = document.getElementById("regionTextInput");
  const lines = [];
  for (const r of regions) {
    if (!r.sku_code || !r.province) continue;
    const city = r.city || "";
    lines.push(`${r.sku_code},${r.province}${city ? "," + city : ""}`);
  }
  textarea.value = lines.join("\n");
}

function collectRegionsFromText() {
  const textarea = document.getElementById("regionTextInput");
  const text = textarea.value.trim();
  if (!text) return [];
  const regions = [];
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  for (const line of lines) {
    const parts = line.split(/[,，]/).map((part) => part.trim()).filter(Boolean);
    if (parts.length < 2) continue;
    const sku = parts[0];
    const province = parts[1] || "";
    const city = parts[2] || null;
    if (!sku || !province) continue;
    regions.push({ sku_code: sku, province, city, district: null });
  }
  return regions;
}

// === MODIFIED START ===
// 原因：限发区域上传改为两步流程 — 上传预览 → 用户确认 → 写入。
// 影响范围：限发区域 Excel 上传交互。
let regionPreviewData = null;

async function uploadRegionXlsx() {
  const fileInput = document.getElementById("regionXlsxInput");
  const statusEl = document.getElementById("regionXlsxStatus");
  const file = fileInput.files[0];
  if (!file) {
    showNotice("请先选择一个 .xls 或 .xlsx 文件", true);
    return;
  }
  const suffix = file.name.split(".").pop().toLowerCase();
  if (!["xls", "xlsx"].includes(suffix)) {
    showNotice("仅支持 .xls 或 .xlsx 文件", true);
    return;
  }
  setBusy(true);
  statusEl.textContent = "上传解析中...";
  regionPreviewData = null;
  try {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch("/config/regions/upload-xlsx", {
      method: "POST",
      body: formData,
    });
    if (handleUnauthorizedResponse(response)) return;
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `HTTP ${response.status}`);
    }
    const result = await response.json();
    regionPreviewData = result;
    renderRegionPreview(result);
    fileInput.value = "";
    showNotice(`解析完成：${result.new_rules.length} 条规则，请确认后导入`);
  } catch (error) {
    statusEl.textContent = "";
    showNotice(error.message || "上传失败", true);
  } finally {
    setBusy(false);
  }
}

function renderRegionPreview(result) {
  const container = document.getElementById("regionXlsxPreview");
  const statusEl = document.getElementById("regionXlsxStatus");
  const diff = result.diff || {};
  const added = diff.added || [];
  const unchanged = diff.unchanged || [];
  const removed = diff.removed || [];

  statusEl.textContent = `现有 ${result.current_count} 条 → 解析出 ${result.new_rules.length} 条（新增 ${added.length}，不变 ${unchanged.length}，移除 ${removed.length}）`;

  let html = `<div class="preview-summary">`;
  html += `<p><strong>预览：</strong>新增 ${added.length} 条，不变 ${unchanged.length} 条，移除 ${removed.length} 条</p>`;
  html += `</div>`;

  if (added.length > 0) {
    html += `<div class="preview-section"><h4>新增规则（${added.length} 条）</h4><table class="preview-table"><tr><th>产品名称</th><th>省</th><th>市</th></tr>`;
    for (const r of added) {
      html += `<tr class="preview-added"><td>${escapeHtml(r.sku_code)}</td><td>${escapeHtml(r.province)}</td><td>${escapeHtml(r.city || "")}</td></tr>`;
    }
    html += `</table></div>`;
  }

  if (removed.length > 0) {
    html += `<div class="preview-section"><h4>将被移除（${removed.length} 条）</h4><table class="preview-table"><tr><th>产品名称</th><th>省</th><th>市</th></tr>`;
    for (const r of removed) {
      html += `<tr class="preview-removed"><td>${escapeHtml(r.sku_code)}</td><td>${escapeHtml(r.province)}</td><td>${escapeHtml(r.city || "")}</td></tr>`;
    }
    html += `</table></div>`;
  }

  html += `<div class="preview-actions">`;
  html += `<button type="button" id="confirmRegionImportButton" onclick="confirmRegionImport()">确认导入 ${result.new_rules.length} 条规则</button>`;
  html += `<button type="button" onclick="cancelRegionPreview()">取消</button>`;
  html += `</div>`;

  container.innerHTML = html;
  container.classList.remove("is-hidden");
}

async function confirmRegionImport() {
  if (!regionPreviewData || !regionPreviewData.new_rules) return;
  setBusy(true);
  try {
    const response = await fetch("/config/regions/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rules: regionPreviewData.new_rules }),
    });
    if (handleUnauthorizedResponse(response)) return;
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `HTTP ${response.status}`);
    }
    const result = await response.json();
    showNotice(`导入成功：${result.count} 条规则（共 ${result.total} 条）`);
    regionPreviewData = null;
    document.getElementById("regionXlsxPreview").classList.add("is-hidden");
    document.getElementById("regionXlsxStatus").textContent = "";
    await loadApp();
  } catch (error) {
    showNotice(error.message || "确认导入失败", true);
  } finally {
    setBusy(false);
  }
}

function cancelRegionPreview() {
  regionPreviewData = null;
  document.getElementById("regionXlsxPreview").classList.add("is-hidden");
  document.getElementById("regionXlsxStatus").textContent = "已取消";
}
// === MODIFIED END ===

// === MODIFIED START ===
// 原因：SKU 群上传改为两步流程 — 上传预览 → 用户确认 → 写入。
// 影响范围：SKU 群 Excel 上传交互。
let skuGroupPreviewData = null;

async function uploadSkuGroupXlsx() {
  const fileInput = document.getElementById("skuGroupXlsxInput");
  const statusEl = document.getElementById("skuGroupXlsxStatus");
  const file = fileInput.files[0];
  if (!file) {
    showNotice("请先选择一个 .xls 或 .xlsx 文件", true);
    return;
  }
  const suffix = file.name.split(".").pop().toLowerCase();
  if (!["xls", "xlsx"].includes(suffix)) {
    showNotice("仅支持 .xls 或 .xlsx 文件", true);
    return;
  }
  setBusy(true);
  statusEl.textContent = "上传解析中...";
  skuGroupPreviewData = null;
  try {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch("/config/sku-groups/upload-xlsx", {
      method: "POST",
      body: formData,
    });
    if (handleUnauthorizedResponse(response)) return;
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `HTTP ${response.status}`);
    }
    const result = await response.json();
    skuGroupPreviewData = result;
    renderSkuGroupPreview(result);
    fileInput.value = "";
    showNotice(`解析完成：${result.new_rules.length} 条规则，请确认后导入`);
  } catch (error) {
    statusEl.textContent = "";
    showNotice(error.message || "上传失败", true);
  } finally {
    setBusy(false);
  }
}

function renderSkuGroupPreview(result) {
  const container = document.getElementById("skuGroupXlsxPreview");
  const statusEl = document.getElementById("skuGroupXlsxStatus");
  const diff = result.diff || {};
  const added = diff.added || [];
  const modified = diff.modified || [];
  const unchanged = diff.unchanged || [];

  statusEl.textContent = `现有 ${result.current_count} 个SKU群 → 解析出 ${result.new_rules.length} 个（新增 ${added.length}，修改 ${modified.length}，不变 ${unchanged.length}）`;

  let html = `<div class="preview-summary">`;
  html += `<p><strong>预览：</strong>新增 ${added.length} 个，修改 ${modified.length} 个，不变 ${unchanged.length} 个</p>`;
  html += `</div>`;

  if (added.length > 0) {
    html += `<div class="preview-section"><h4>新增（${added.length} 个）</h4><table class="preview-table"><tr><th>产品名称</th><th>群名称</th><th>群主手机号</th></tr>`;
    for (const r of added) {
      html += `<tr class="preview-added"><td>${escapeHtml(r.sku_code)}</td><td>${escapeHtml(r.group_name)}</td><td>${escapeHtml(r.owner_mobile)}</td></tr>`;
    }
    html += `</table></div>`;
  }

  if (modified.length > 0) {
    html += `<div class="preview-section"><h4>修改（${modified.length} 个）</h4><table class="preview-table"><tr><th>产品名称</th><th>旧群名</th><th>新群名</th><th>旧手机号</th><th>新手机号</th></tr>`;
    for (const r of modified) {
      html += `<tr class="preview-modified"><td>${escapeHtml(r.sku_code)}</td><td>${escapeHtml(r.old.group_name)}</td><td>${escapeHtml(r.new.group_name)}</td><td>${escapeHtml(r.old.owner_mobile)}</td><td>${escapeHtml(r.new.owner_mobile)}</td></tr>`;
    }
    html += `</table></div>`;
  }

  html += `<div class="preview-actions">`;
  html += `<button type="button" id="confirmSkuGroupImportButton" onclick="confirmSkuGroupImport()">确认导入 ${result.new_rules.length} 条规则</button>`;
  html += `<button type="button" onclick="cancelSkuGroupPreview()">取消</button>`;
  html += `</div>`;

  container.innerHTML = html;
  container.classList.remove("is-hidden");
}

async function confirmSkuGroupImport() {
  if (!skuGroupPreviewData || !skuGroupPreviewData.new_rules) return;
  setBusy(true);
  try {
    const response = await fetch("/config/sku-groups/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rules: skuGroupPreviewData.new_rules }),
    });
    if (handleUnauthorizedResponse(response)) return;
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `HTTP ${response.status}`);
    }
    const result = await response.json();
    showNotice(`导入成功：${result.count} 个SKU群（新增 ${result.added}，修改 ${result.modified}，共 ${result.total} 个）`);
    skuGroupPreviewData = null;
    document.getElementById("skuGroupXlsxPreview").classList.add("is-hidden");
    document.getElementById("skuGroupXlsxStatus").textContent = "";
    await loadApp();
  } catch (error) {
    showNotice(error.message || "确认导入失败", true);
  } finally {
    setBusy(false);
  }
}

function cancelSkuGroupPreview() {
  skuGroupPreviewData = null;
  document.getElementById("skuGroupXlsxPreview").classList.add("is-hidden");
  document.getElementById("skuGroupXlsxStatus").textContent = "已取消";
}
// === MODIFIED END ===

async function uploadExcludedSkuXlsx() {
  const fileInput = document.getElementById("excludedSkuXlsxInput");
  const statusEl = document.getElementById("excludedSkuXlsxStatus");
  const file = fileInput.files[0];
  if (!file) {
    showNotice("请先选择一个 .xls 或 .xlsx 文件", true);
    return;
  }
  const suffix = file.name.split(".").pop().toLowerCase();
  if (!["xls", "xlsx"].includes(suffix)) {
    showNotice("仅支持 .xls 或 .xlsx 文件", true);
    return;
  }
  setBusy(true);
  statusEl.textContent = "上传解析中...";
  try {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch("/config/excluded-skus/upload-xlsx", {
      method: "POST",
      body: formData,
    });
    // === MODIFIED START ===
    // 原因：上传接口未登录时需要跳回登录页，保持后台会话行为一致。
    // 影响范围：排除 SKU Excel 上传。
    if (handleUnauthorizedResponse(response)) return;
    // === MODIFIED END ===
    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `HTTP ${response.status}`);
    }
    const result = await response.json();
    statusEl.textContent = `原有 ${result.before} 个，新增 ${result.added} 个，跳过 ${result.modified} 个重复（共 ${result.total} 个排除SKU）`;
    fileInput.value = "";
    showNotice(`导入成功：${result.count} 条记录（新增 ${result.added} 个，跳过 ${result.modified} 个重复）`);
    await loadApp();
  } catch (error) {
    statusEl.textContent = "";
    showNotice(error.message || "上传失败", true);
  } finally {
    setBusy(false);
  }
}

function parseSuppliers(value) {
  return value
    .split(/\r?\n|;/)
    .map((line) => splitCsvLine(line))
    // === MODIFIED START ===
    // 原因：供应商对照配置改为商品名称 + 供应商名称两列；兼容旧三列输入时忽略中间的供应商编码。
    // 影响范围：规则配置中心供应商对照保存。
    .filter((parts) => parts[0] && parts[1])
    .map((parts) => ({
      sku_code: parts[0],
      supplier_name: parts[2] || parts[1],
    }));
    // === MODIFIED END ===
}

function splitCsvLine(line) {
  return line
    .split(/[,，]/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("zh-CN");
}

function formatDate(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function shortId(value) {
  if (!value) return "--";
  if (value.length <= 12) return value;
  return `${value.slice(0, 8)}...${value.slice(-4)}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

function setBusy(isBusy) {
  // === MODIFIED START ===
  // 原因：页面顶部删除“立即执行”入口，忙碌态更新需兼容按钮不存在。
  // 影响范围：前端全局忙碌态。
  const runTaskButton = document.getElementById("runTaskButton");
  if (runTaskButton) runTaskButton.disabled = isBusy;
  // === MODIFIED END ===
  document.getElementById("refreshButton").disabled = isBusy;
  document.getElementById("saveRulesButton").disabled = isBusy;
  // === MODIFIED START ===
  // 原因：规则配置页新增同步按钮，需要纳入全局忙碌态防止重复提交。
  // 影响范围：规则配置页顶部操作区。
  document.getElementById("syncSkuGroupCallerConfigsButton").disabled = isBusy;
  // === MODIFIED END ===
  // === MODIFIED START ===
  // 原因：执行日志下载按钮需要跟随全局忙碌态。
  // 影响范围：执行日志页面交互。
  document.getElementById("downloadLogsButton").disabled = isBusy;
  // === MODIFIED END ===
  document.getElementById("uploadReceiptButton").disabled = isBusy;
}

function showNotice(message, isError = false) {
  const notice = document.getElementById("notice");
  notice.textContent = message;
  notice.classList.toggle("is-error", isError);
  notice.classList.remove("is-hidden");
  clearTimeout(showNotice.timer);
  showNotice.timer = setTimeout(() => notice.classList.add("is-hidden"), 3200);
}

function updateClock() {
  document.getElementById("taskTime").textContent = new Date().toLocaleString("zh-CN", { hour12: false });
}
