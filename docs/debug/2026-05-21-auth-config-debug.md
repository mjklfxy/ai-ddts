# 2026-05-21 后台登录与配置生效排查

## 结论

- 后台登录验证已增加为可选能力：设置 `AI_DDTS_ADMIN_PASSWORD` 后，后台页面、静态资源和管理 API 都需要 HTTP Basic 登录。
- `GET /health` 与已签名的 `/order-files/download` 不拦截，分别用于探活和群消息中的文件下载。
- 真实 `run_once()` 链路在上一个里程碑已验证可触发真实推送；本轮登录验证用接口测试确认“未登录不能触发，登录后可以触发任务入口”。
- SKU 群配置存在一个确认为真的持久化 bug：部分更新/导入路径会丢失 `user_id`，导致已解析过的推送身份被覆盖为空。

## 根因

1. `application.api_service.ApiService.upload_sku_group_xlsx` 只保存 `group_name` 和 `owner_mobile`。
2. `application.sku_group_map.SkuGroupMapStore` 只读写 `group_name` 和 `owner_mobile`。
3. `Pipeline` 的实际推送路径是：
   `sku_group_map -> OrderSplitter -> GroupOrderBatch -> Pipeline._deliver_batches -> MessagePayload`
4. 如果 `user_id` 为空，`Pipeline` 会用 `owner_mobile` 调 `_build_cached_user_resolver()` 解析；解析失败时兜底用手机号。

所以“手机号配置不生效”的常见表现可能有两类：

- 配置在导入/保存后丢了 `user_id`，导致每次推送都重新按手机号解析。
- 手机号解析接口返回失败或非预期 `userId`，最终祺信接口找不到对应机器人/群。

## 本轮修复

- `upload_sku_group_xlsx` 更新群名和手机号时保留已有 `user_id`。
- `SkuGroupMapStore` 读写 `user_id`。
- `OrderSplitter` 测试覆盖 `group_name / owner_mobile / user_id` 会进入批次。
- 后台 Basic Auth 由环境变量控制：
  - `AI_DDTS_ADMIN_USER`，默认 `admin`
  - `AI_DDTS_ADMIN_PASSWORD`，为空时不启用登录

## 已验证配置

- `source.mode = jikeyun`：真实吉客云抓单已验证。
- `rpa.enabled = true`：完整 `run_once()` 中会触发 RPA，并记录 `jikeyun_rpa_export_*` 与 `export_*` 日志。
- `rules.sku_group_map_enabled`：开启后 `GroupRule` 会拦截未配置 SKU，配置后进入拆分。
- `sku_group_map.group_name`：会进入 `MessagePayload.group_name`，真实已推到 `12121`。
- `sku_group_map.owner_mobile`：会进入 `GroupOrderBatch.owner_mobile`，并用于懒解析 `user_id`。
- `sku_group_map.user_id`：本轮修复后不会被导入/Store 写入路径清空。
- `kingdee.enabled = false`：真实任务中金蝶阶段为 `未启用`。

## 临时方案

- 若某个群手机号解析不稳定，可以在 `sku_group_map` 里显式填 `user_id`，绕过手机号解析。
- 若需要临时把整批导到测试群，优先使用临时配置文件跑 `run_once(config_path=...)`，跑完删除临时配置，不污染正式 `config.json`。

## 未处理

- RPA 当前可用，但有多余动作，本轮按要求暂不处理。
- `tests.test_interfaces_app` 里仍有部分历史 mock 断言与当前 mock 数据不一致，属于既有测试数据漂移，不是本轮登录/配置修复引入。
