# AI-DDTS — 订单自动分发推送系统

## 项目概述

本项目是一个订单自动处理流水线，从 **吉客云（Jikeyun/JackYun）** 拉取订单，经过规则引擎过滤与拆分，生成 CSV 文件并上传到公网文件服务器，最终通过 **祺信（Qixin）** API 向企业微信群推送文本消息（内含文件下载链接），实现订单的自动分发。

### 整体架构

```
吉客云 OpenAPI
    ↓ (拉取订单)
规则引擎 (RuleEngine)
    ↓ (过滤/校验)
订单拆分 (OrderSplitter)
    ↓ (按群分组)
CSV 文件生成 (CsvFileGenerator)
    ↓
文件上传 → 公网文件服务器 (:243 服务器)
    ↓
消息推送 → 企业微信群 (祺信 API)
```

### 端到端流程状态

**已跑通。** 从吉客云拉单 → 规则过滤 → 拆分 → 生成 CSV → 上传 → 推送消息，全链路验证通过。

---

## 项目结构

```
AI-DDTS/
├── main.py                      # CLI 入口
├── application/                 # 应用层（编排逻辑）
│   ├── manual_runner.py         # 手动运行入口
│   ├── pipeline.py              # 流水线编排
│   ├── config_service.py        # 配置加载
│   ├── file_generator.py        # CSV 文件生成
│   ├── order_splitter.py        # 按群拆分
│   ├── task_service.py          # 任务服务
│   └── ...
├── domain/                      # 领域层（业务规则）
│   ├── rule_engine.py           # 规则引擎
│   └── rules/                   # 具体规则实现
│       ├── warehouse_rule.py    # 仓库排除规则
│       ├── sku_rule.py          # SKU 启用规则
│       ├── region_rule.py       # 区域限发规则
│       ├── group_rule.py        # 群组配置规则
│       └── ...
├── infrastructure/              # 基础设施层（外部依赖适配）
│   ├── jikeyun_client.py        # 吉客云 OpenAPI 客户端
│   ├── qixin_client.py          # 祺信消息推送客户端
│   ├── file_upload_client.py    # 文件上传客户端
│   ├── message_adapter.py       # 消息重试适配器
│   ├── cloud_warehouse_client.py# 云仓 API 客户端
│   └── images/                  # 鼠标自动化截图
│       ├── 1.png ~ 10.png
│       └── ...
├── interfaces/                  # Web 接口层
│   └── app.py                   # FastAPI 应用
├── config/
│   └── config.json              # 应用配置
└── input/
    └── 销售单查询.xlsx           # 吉客云导出（地址兜底）
```

---

## 吉客云收件人信息获取说明

目前通过 **PyAutoGUI 鼠标模拟自动化** 从吉客云界面获取收件人地址和电话。

### 首次使用步骤

1. 打开浏览器进入吉客云 **销售单查询** 页面
2. **手动下载一单**，输入验证码完成验证
3. 之后自动化脚本可自动操作

### 吉客云 API 更新后的切换

当吉客云 OpenAPI 提供收件人信息字段后，打开 `infrastructure/jikeyun_client.py`，第 215 行加上注释：

```python
 export_orders_to_xlsx()   →  # export_orders_to_xlsx()
```

其余代码无需改动。

---

## 配置说明

### 环境变量

#### 本项目所需

| 变量名                | 说明                     | 来源/备注                      |
| --------------------- | ------------------------ | ------------------------------ |
| `JIKEYUN_APPKEY`      | 吉客云开放平台 AppKey    | 吉客云开放平台获取             |
| `JIKEYUN_APP_SECRET`  | 吉客云开放平台 AppSecret | 吉客云开放平台获取             |
| `DOWNLOAD_SECRET_KEY` | 文件下载链接签名密钥     | 自行设定，与服务器一致         |
| `KINGDEE_TOKEN`       | 金蝶 API Token           | 金蝶系统获取（如未启用可忽略） |

#### 配套服务（:243 服务器）所需

| 变量名            | 说明          |
| ----------------- | ------------- |
| `ODPS_ACCESS_ID`  | ODPS 访问 ID  |
| `ODPS_SECRET_KEY` | ODPS 访问密钥 |

### 固定 ID 与密钥

以下值已配置或引用在 `config/config.json` 中，供参考：

| 名称         | 值                                           | 说明                               |
| ------------ | -------------------------------------------- | ---------------------------------- |
| `CALLER_ID`  | `10002`                                      | 祺信 API 调用方 ID                 |
| `SECRET_KEY` | `EuZFTaZWXm7ezguXQM8soUtO6LnTbjrQW7y2A9rLZ8` | 祺信 API HMAC 签名密钥（测试环境） |

### 推送模式

`config.json` 中 `qixin.push_mode` 字段：

- `"link"`（当前默认）：上传文件后推送文本消息，内容为文件下载链接
- `"file"`：直接推送文件消息（需要文件 URL 公网可达）

---

## 配套服务

本项目的订单文件需上传到公网服务器供客户下载，配套服务运行在 **`xxx.xxx.x.243:8088`**：

### 功能

1. **手机号 → userid 解析**
   - `POST /api/userid`，参数 `{"mobile": "..."}`，返回 `{"userid": "..."}`
2. **文件托管与下载**
   - `POST /api/files/upload` — 接收本项目上传的 CSV 文件
   - `GET /api/files/{uuid}.csv` — 供外网客户下载订单文件

### 启动前配置

```python
ODPS_ACCESS_ID = os.getenv("ODPS_ACCESS_ID", "")
ODPS_SECRET_KEY = os.getenv("ODPS_SECRET_KEY", "")这两个在环境中没有需要配置
```

该服务已在服务器上的 `tmux` 会话中运行，会话名称为 **`wuliu**。

---

## 运行

```bash
# 设置环境变量
export QIXIN_SECRET_KEY="your_key"

# 运行订单处理
python main.py
```

---

## 截图

config.json中将

"source": {

"mode": "mock"

},配置为mock可以使用测试订单进行测试

以下为测试订单的推送结果的截图：

![image-20260518223257590](C:\Users\gain\AppData\Roaming\Typora\typora-user-images\image-20260518223257590.png)

---

## 注意

**通过手机号获取 userid 的方法可能存在 bug**（远程 API 不稳定或返回数据异常）。如果出现消息推送失败，**请优先检查 userid 是否正确**，推送接口本身是正常的。

推送接口的详细文档请参见项目根目录下的 [message-api.md](message-api.md)。
