# 开发规则（强制）

## 一、架构约束

1. 所有业务规则必须继承 OrderRule
2. 不允许在 pipeline 写业务逻辑（只能编排流程）
3. 不允许在 router / API 写逻辑
4. domain 层不得依赖 infrastructure
5. 所有状态必须使用 Enum（禁止字符串）

---

## 二、日志与安全

1. 所有核心流程必须记录日志（log_info / log_error）
2. 所有日志必须包含 trace_id
3. 禁止使用 print
4. 禁止记录敏感信息（APP_SECRET / token）

---

## 三、规则系统

1. 规则必须返回 RuleResult
2. 所有异常必须包含：
   - reason
   - rule_name
3. WarehouseRule 必须返回 IGNORE（不是 ERROR）

---

## 四、代码修改规范

修改已有代码必须标记：

```python
# === MODIFIED START ===
# 原因：
# 影响范围：
# === MODIFIED END ===
```

---

## 五、开发流程（必须遵守）

每个任务必须：
1. 先给设计方案
2. 再写代码
3. 每个类必须有注释

---

# =========================
# 任务清单（按顺序执行）
# =========================

## 任务1：理解架构
只分析代码，不写代码

---

## 任务2：实现 WarehouseRule
要求：
- 命中仓库 → IGNORE
- 不进入异常

---

## 任务3：实现 SkuServiceRule
- 未启用 → ERROR

---

## 任务4：实现 RegionRule
- 支持省市区匹配
- 命中 → 整单 ERROR

---

## 任务5：实现 GroupRule
- 未配置群 → ERROR

---

## 任务6：实现 RuleEngine 日志
- 记录 rule_hit

---

## 任务7：实现 OrderSplitter
- 按 group 拆分

---

## 任务8：实现 FileGenerator
- 生成 CSV

---

## 任务9：实现 MessageAdapter
- 支持 retry

---

## 任务10：实现 Task + trace_id

---

## 任务11：实现 Pipeline
- 分阶段执行
- 不允许写规则逻辑

---

## 任务12：实现异常订单模型

---

## 任务13：实现日志模块

---

## 任务14：集成测试
