"""手动推送测试消息到祺信群聊。用法: python scripts/manual_push_group.py"""

import hashlib
import hmac
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Windows 终端中文输出兼容
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# ── 配置 ──────────────────────────────────────────────
API_BASE_URL = "https://state.renruikeji.cn/api/marketengine"
CALLER_ID = "10002"
SECRET_KEY = "EuZFTaZWXm7ezguXQM8soUtO6LnTbjrQW7y2A9rLZ8"
USERID_API_URL = "http://mengyang.renruikeji.cn/api/userid"

GROUP_NAME = "天合人康@清涟国产贝贝"
OWNER_MOBILE = "18231132648"
TEST_CONTENT = "测试消息：手动推送验证群消息通道是否正常。"


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


# ── Step 1: 通过手机号解析 user_id ────────────────────
def resolve_userid(mobile: str) -> str:
    log(f"[Step 1] 解析 user_id — mobile={mobile}")
    body = json.dumps({"mobile": mobile}).encode("utf-8")
    log(f"  请求 URL: {USERID_API_URL}")
    log(f"  请求体: {body.decode('utf-8')}")

    req = urllib.request.Request(
        USERID_API_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        raw = resp.read()
        resp.close()
    except urllib.error.URLError as exc:
        log(f"  网络错误: {exc}")
        return ""

    log(f"  响应状态: 200")
    log(f"  响应体: {raw.decode('utf-8', errors='replace')}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log("  响应不是合法 JSON")
        return ""

    userid = data.get("userid", "")
    if userid:
        log(f"  解析成功: userid={userid}")
    else:
        log(f"  响应中无 userid 字段")
    return userid


# ── Step 2: 构造签名 ──────────────────────────────────
def build_sign(caller_id: str, timestamp: str, canonical_query: str, canonical_body: str) -> str:
    sign_content = (
        f"callerId={urllib.parse.quote(caller_id, safe='')}"
        f"&timestamp={urllib.parse.quote(timestamp, safe='')}"
        f"&canonicalQuery={urllib.parse.quote(canonical_query, safe='')}"
        f"&canonicalBody={urllib.parse.quote(canonical_body, safe='')}"
    )
    sign = hmac.new(
        SECRET_KEY.encode("utf-8"),
        sign_content.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return sign


# ── Step 3: 发送文本消息到群 ──────────────────────────
def send_text(group_name: str, user_id: str, content: str) -> dict:
    log(f"[Step 2] 发送群消息 — group={group_name}, user_id={user_id}")

    raw_body = json.dumps(
        {"userId": user_id, "groupName": group_name, "content": content},
        ensure_ascii=False,
    )
    canonical_body = json.dumps(
        json.loads(raw_body), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    timestamp = str(int(time.time()))
    sign = build_sign(CALLER_ID, timestamp, "", canonical_body)

    send_url = f"{API_BASE_URL.rstrip('/')}/agent/auth/message/sendTextToGroup"
    log(f"  请求 URL: {send_url}")
    log(f"  请求体: {raw_body}")
    log(f"  timestamp: {timestamp}")
    log(f"  sign: {sign}")

    req = urllib.request.Request(
        send_url,
        data=raw_body.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "callerId": CALLER_ID,
            "timestamp": timestamp,
            "sign": sign,
        },
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        raw = resp.read()
        resp.close()
    except urllib.error.URLError as exc:
        log(f"  网络错误: {exc}")
        return {"error": str(exc)}

    log(f"  响应状态: 200")
    log(f"  响应体: {raw.decode('utf-8', errors='replace')}")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "response is not valid JSON", "raw": raw.decode("utf-8", errors="replace")}


# ── 主流程 ─────────────────────────────────────────────
def main() -> None:
    log("=" * 60)
    log("手动推送祺信群聊消息")
    log("=" * 60)
    log(f"群名: {GROUP_NAME}")
    log(f"群主手机号: {OWNER_MOBILE}")
    log(f"消息内容: {TEST_CONTENT}")
    log("")

    userid = resolve_userid(OWNER_MOBILE)
    if not userid:
        log("WARNING: user_id 为空，尝试直接发送（可能会报错）")
    log("")

    result = send_text(GROUP_NAME, userid, TEST_CONTENT)
    log("")

    code = result.get("code")
    message = result.get("message", "")
    data = result.get("data", {})

    if code in (0, 200):
        log(f"推送成功! messageId={data.get('messageId', 'N/A')}")
    else:
        log(f"推送失败: code={code}, message={message}")
        if "error" in result:
            log(f"异常: {result['error']}")

    log("=" * 60)


if __name__ == "__main__":
    main()
