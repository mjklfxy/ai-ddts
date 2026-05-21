# 消息发送接口

## 概览

| 项目 | 说明 |
| --- | --- |
| 请求方式 | `POST` |
| 基础路径 | `/agent/auth/message` |
| Content-Type | `application/json` |
| 鉴权方式 | HMAC-SHA256 签名（Header 传参） |
| Client 接口 | `com.thrk.market.client.api.MessageApi` |

### 环境地址

| 环境 | 请求前缀 |
| --- | --- |
| 测试环境 | `https://teststate.renruikeji.cn/api/marketengine` |
| 生产环境 | `https://state.renruikeji.cn/api/marketengine` |

---

## 鉴权

所有 `/agent/auth/**` 路径均需签名鉴权。调用方在 HTTP Header 中传入以下三个字段：

| Header | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `callerId` | 是 | string | 调用方标识，由服务端分配 |
| `timestamp` | 是 | string | 请求时间戳（秒或毫秒），服务端默认允许 ±30 分钟时间窗 |
| `sign` | 是 | string | HMAC-SHA256 签名值 |

### 签名算法

```
1. 构造 canonicalBody：将请求体 JSON 的 key 按字典序（ASCII 升序）重新排列后序列化为紧凑 JSON 字符串
2. 构造 canonicalQuery：将 URL query 参数按 key 字典序拼接为 key1=val1&key2=val2（POST JSON 无 query 参数时为空字符串）
3. 拼接 signContent = "callerId=" + URLEncode(callerId) + "&timestamp=" + URLEncode(timestamp) + "&canonicalQuery=" + URLEncode(canonicalQuery) + "&canonicalBody=" + URLEncode(canonicalBody)
4. 使用分配的 secretKey 计算 sign = HMAC-SHA256(secretKey, signContent)，结果转 hex 小写
```

> **关键点：** signContent 是 key=value 形式用 `&` 连接，每个 value 都经过 URL 编码（不是用换行符拼接）。canonicalBody 中的 `{`、`"`、`:` 等字符经过 URL 编码后会变成 `%7B`、`%22`、`%3A` 等。

> 完整签名规则参考：`market-brain/docs/agent/agent-scrm-chat-log-api.md`

#### canonicalBody 字段排序说明

**签名前必须将请求体 JSON 的 key 按字典序（ASCII 升序）重新序列化**，而不是直接使用原始请求体。
字典序比较规则：逐字符比较 ASCII 码，`a < b < c ...`，相同前缀时短的在前。

以发送文件接口为例，原始请求体：

```json
{"userId":"ZhangSan","groupName":"测试群","fileUrl":"https://oss.example.com/file.xlsx","fileName":"报告.xlsx"}
```

排序后的 canonicalBody（用于签名计算）：

```json
{"fileName":"报告.xlsx","fileUrl":"https://oss.example.com/file.xlsx","groupName":"测试群","userId":"ZhangSan"}
```

排序依据：`fileName` < `fileUrl` < `groupName` < `userId`

#### Java 实现

Java 中使用 Jackson 的 `ObjectMapper` 将原始 JSON 反序列化为 `TreeMap`（自动按 key 字典序排列），再序列化回字符串：

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.TreeMap;

ObjectMapper objectMapper = new ObjectMapper();

@SuppressWarnings("unchecked")
TreeMap<String, Object> sorted = objectMapper.readValue(rawBody, TreeMap.class);
String canonicalBody = objectMapper.writeValueAsString(sorted);
```

#### Python 实现

Python 中使用 `json.loads` 解析后，`json.dumps` 时指定 `sort_keys=True`：

```python
import json

raw_body = '{"userId":"ZhangSan","groupName":"测试群","fileUrl":"https://oss.example.com/file.xlsx","fileName":"报告.xlsx"}'

parsed = json.loads(raw_body)
canonical_body = json.dumps(parsed, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
# 结果：{"fileName":"报告.xlsx","fileUrl":"https://oss.example.com/file.xlsx","groupName":"测试群","userId":"ZhangSan"}
```

> **注意：** `separators=(',', ':')` 去掉默认的空格，`ensure_ascii=False` 保留中文原文，与服务端序列化结果一致。

---

## 接口列表

### 1. 发送群文本消息

**请求路径：** `POST /agent/auth/message/sendTextToGroup`

#### 请求参数（Request Body）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `userId` | string | 是 | 店长 userId |
| `groupName` | string | 是 | 企信群名称（精确匹配） |
| `content` | string | 是 | 消息文本内容 |

请求体示例：

```json
{
  "userId": "ZhangSan",
  "groupName": "重点客户答疑群",
  "content": "您好，本周直播即将开始"
}
```

---

### 2. 发送群文件消息

**请求路径：** `POST /agent/auth/message/sendFileToGroup`

#### 请求参数（Request Body）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `userId` | string | 是 | 店长 userId |
| `groupName` | string | 是 | 企信群名称（精确匹配） |
| `fileUrl` | string | 是 | 文件下载地址（需公网可访问） |
| `fileName` | string | 是 | 文件显示名称（含后缀，如 `报告.pdf`） |

请求体示例：

```json
{
  "userId": "ZhangSan",
  "groupName": "重点客户答疑群",
  "fileUrl": "https://oss.example.com/files/report-2026.pdf",
  "fileName": "月度报告.pdf"
}
```

---

## 统一响应格式

### 成功响应

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {
    "messageId": "5d3a0b4f6a1c4d2bb6e6a25d29f8b3aa",
    "groupId": "R:1234567890",
    "robotKey": "abc123def456"
  }
}
```

### 失败响应

```json
{
  "code": 500,
  "message": "消息发送失败: 未找到对应企信群",
  "data": null
}
```

### data 字段说明（成功时）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `messageId` | string | 消息唯一标识 |
| `groupId` | string | 群ID |
| `robotKey` | string | 机器人Key |

---

## 错误码

通过外层 `code` 判断是否成功：`code=200` 为成功，非 200 为失败（业务异常、鉴权失败、参数校验等），失败信息在 `message` 字段中。

| 错误信息 | 原因 |
| --- | --- |
| `callerId不存在` | callerId 未注册 |
| `timestamp已过期` | 时间戳超出 ±30 分钟窗口 |
| `sign校验失败` | 签名不匹配，检查 secretKey 和拼接规则 |
| `userId/groupName/content 不能为空` | 文本消息必填参数缺失 |
| `userId/groupName/fileUrl/fileName 不能为空` | 文件消息必填参数缺失 |
| `未找到店长可用的机器人` | 该 userId 下无可用机器人 |
| `未找到对应企信群` | groupName 不匹配或该店长下无此群 |
| `消息发送失败: xxx` | 下游渠道返回失败，详见 message 字段 |

---

## 调用示例

### Java（发送文本）

```java
import com.fasterxml.jackson.databind.ObjectMapper;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.TreeMap;

public class SendGroupTextExample {

    private static final String BASE_URL = "https://teststate.renruikeji.cn/api/marketengine";
    private static final String CALLER_ID = "10001";
    private static final String SECRET_KEY = "your-secret-key";
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    public static void main(String[] args) throws Exception {
        String body = "{\"userId\":\"ZhangSan\",\"groupName\":\"重点客户答疑群\",\"content\":\"您好，本周直播即将开始\"}";

        // 1. canonicalBody：key 按字典序排列
        String canonicalBody = buildCanonicalBody(body);

        // 2. 构造 signContent（key=URLEncode(value) 用 & 连接）
        String timestamp = String.valueOf(System.currentTimeMillis() / 1000);
        String signContent = "callerId=" + urlEncode(CALLER_ID)
                + "&timestamp=" + urlEncode(timestamp)
                + "&canonicalQuery=" + urlEncode("")
                + "&canonicalBody=" + urlEncode(canonicalBody);

        // 3. HMAC-SHA256 签名
        String sign = hmacSha256(SECRET_KEY, signContent);

        // 4. 发起请求
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + "/agent/auth/message/sendTextToGroup"))
                .header("Content-Type", "application/json")
                .header("callerId", CALLER_ID)
                .header("timestamp", timestamp)
                .header("sign", sign)
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpResponse<String> response = HttpClient.newHttpClient()
                .send(request, HttpResponse.BodyHandlers.ofString());

        System.out.println("Status: " + response.statusCode());
        System.out.println("Body:   " + response.body());
    }

    /** 将 JSON body 的 key 按字典序排列后重新序列化 */
    @SuppressWarnings("unchecked")
    private static String buildCanonicalBody(String rawBody) throws Exception {
        TreeMap<String, Object> sorted = OBJECT_MAPPER.readValue(rawBody, TreeMap.class);
        return OBJECT_MAPPER.writeValueAsString(sorted);
    }

    private static String urlEncode(String value) throws Exception {
        return URLEncoder.encode(value == null ? "" : value, StandardCharsets.UTF_8.name());
    }

    private static String hmacSha256(String key, String data) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        byte[] hash = mac.doFinal(data.getBytes(StandardCharsets.UTF_8));
        StringBuilder hex = new StringBuilder();
        for (byte b : hash) {
            hex.append(String.format("%02x", b));
        }
        return hex.toString();
    }
}
```

### Java（发送文件）

```java
String body = "{\"userId\":\"ZhangSan\",\"groupName\":\"重点客户答疑群\",\"fileUrl\":\"https://oss.example.com/files/report.pdf\",\"fileName\":\"月度报告.pdf\"}";

String canonicalBody = buildCanonicalBody(body);
// 排序后：{"fileName":"月度报告.pdf","fileUrl":"https://oss.example.com/files/report.pdf","groupName":"重点客户答疑群","userId":"ZhangSan"}

String signContent = "callerId=" + urlEncode(CALLER_ID)
        + "&timestamp=" + urlEncode(timestamp)
        + "&canonicalQuery=" + urlEncode("")
        + "&canonicalBody=" + urlEncode(canonicalBody);
String sign = hmacSha256(SECRET_KEY, signContent);

// 路径改为：BASE_URL + "/agent/auth/message/sendFileToGroup"
```

### Python

```python
import hashlib
import hmac
import json
import time
from urllib.parse import quote

import requests

BASE_URL = "https://teststate.renruikeji.cn/api/marketengine"
CALLER_ID = "10001"
SECRET_KEY = "your-secret-key"


def build_canonical_body(raw_body: str) -> str:
    """将 JSON body 的 key 按字典序排列后重新序列化为紧凑 JSON"""
    parsed = json.loads(raw_body)
    return json.dumps(parsed, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def url_encode(value: str) -> str:
    """URL 编码，与 Java URLEncoder.encode 行为一致"""
    return quote(value or "", safe='')


def build_sign(caller_id: str, timestamp: str, canonical_query: str, canonical_body: str, secret_key: str) -> str:
    """
    构造 signContent 并计算 HMAC-SHA256 签名。
    signContent = callerId=URLEncode(callerId)&timestamp=URLEncode(timestamp)&canonicalQuery=URLEncode(canonicalQuery)&canonicalBody=URLEncode(canonicalBody)
    """
    sign_content = (
        "callerId=" + url_encode(caller_id)
        + "&timestamp=" + url_encode(timestamp)
        + "&canonicalQuery=" + url_encode(canonical_query)
        + "&canonicalBody=" + url_encode(canonical_body)
    )
    return hmac.new(
        secret_key.encode("utf-8"), sign_content.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def send_text_to_group(user_id: str, group_name: str, content: str) -> dict:
    body = json.dumps({
        "userId": user_id,
        "groupName": group_name,
        "content": content,
    }, ensure_ascii=False)

    canonical_body = build_canonical_body(body)
    timestamp = str(int(time.time()))
    sign = build_sign(CALLER_ID, timestamp, "", canonical_body, SECRET_KEY)

    resp = requests.post(
        f"{BASE_URL}/agent/auth/message/sendTextToGroup",
        headers={
            "Content-Type": "application/json",
            "callerId": CALLER_ID,
            "timestamp": timestamp,
            "sign": sign,
        },
        data=body.encode("utf-8"),
    )
    return resp.json()


def send_file_to_group(user_id: str, group_name: str, file_url: str, file_name: str) -> dict:
    body = json.dumps({
        "userId": user_id,
        "groupName": group_name,
        "fileUrl": file_url,
        "fileName": file_name,
    }, ensure_ascii=False)

    canonical_body = build_canonical_body(body)
    timestamp = str(int(time.time()))
    sign = build_sign(CALLER_ID, timestamp, "", canonical_body, SECRET_KEY)

    resp = requests.post(
        f"{BASE_URL}/agent/auth/message/sendFileToGroup",
        headers={
            "Content-Type": "application/json",
            "callerId": CALLER_ID,
            "timestamp": timestamp,
            "sign": sign,
        },
        data=body.encode("utf-8"),
    )
    return resp.json()


if __name__ == "__main__":
    # 发送文本
    result = send_text_to_group("ZhangSan", "重点客户答疑群", "您好，本周直播即将开始")
    print(f"文本: code={result.get('code')}, data={result.get('data')}")

    # 发送文件
    result = send_file_to_group("ZhangSan", "重点客户答疑群",
                                "https://oss.example.com/files/report.pdf", "月度报告.pdf")
    print(f"文件: code={result.get('code')}, data={result.get('data')}")
```

### curl 示例

```bash
# 发送文本
# 注意：curl 中 sign 需要提前用上述签名算法计算好
curl -X POST 'https://teststate.renruikeji.cn/api/marketengine/agent/auth/message/sendTextToGroup' \
  -H 'Content-Type: application/json' \
  -H 'callerId: 10001' \
  -H 'timestamp: 1714200000' \
  -H 'sign: {sign}' \
  -d '{
    "userId": "ZhangSan",
    "groupName": "重点客户答疑群",
    "content": "您好，本周直播即将开始"
  }'

# 发送文件
curl -X POST 'https://teststate.renruikeji.cn/api/marketengine/agent/auth/message/sendFileToGroup' \
  -H 'Content-Type: application/json' \
  -H 'callerId: 10001' \
  -H 'timestamp: 1714200000' \
  -H 'sign: {sign}' \
  -d '{
    "userId": "ZhangSan",
    "groupName": "重点客户答疑群",
    "fileUrl": "https://oss.example.com/files/report.pdf",
    "fileName": "月度报告.pdf"
  }'
```
