import hashlib
import hmac
import json
import time
from urllib.parse import quote

import requests

BASE_URL = "https://teststate.renruikeji.cn/api/marketengine"
CALLER_ID = "10002"
SECRET_KEY = "EuZFTaZWXm7ezguXQM8soUtO6LnTbjrQW7y2A9rLZ8"


def build_canonical_body(raw_body: str) -> str:
    """将 JSON body 的 key 按字典序排列后重新序列化为紧凑 JSON"""
    parsed = json.loads(raw_body)
    return json.dumps(parsed, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def url_encode(value: str) -> str:
    """URL 编码，与 Java URLEncoder.encode 行为一致"""
    return quote(value or "", safe="")


def build_sign(
    caller_id: str,
    timestamp: str,
    canonical_query: str,
    canonical_body: str,
    secret_key: str,
) -> str:
    """
    构造 signContent 并计算 HMAC-SHA256 签名。
    signContent = callerId=URLEncode(callerId)&timestamp=URLEncode(timestamp)&canonicalQuery=URLEncode(canonicalQuery)&canonicalBody=URLEncode(canonicalBody)
    """
    sign_content = (
        "callerId="
        + url_encode(caller_id)
        + "&timestamp="
        + url_encode(timestamp)
        + "&canonicalQuery="
        + url_encode(canonical_query)
        + "&canonicalBody="
        + url_encode(canonical_body)
    )
    return hmac.new(
        secret_key.encode("utf-8"), sign_content.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def send_text_to_group(user_id: str, group_name: str, content: str) -> dict:
    body = json.dumps(
        {
            "userId": user_id,
            "groupName": group_name,
            "content": content,
        },
        ensure_ascii=False,
    )

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


def send_file_to_group(
    user_id: str, group_name: str, file_url: str, file_name: str
) -> dict:
    body = json.dumps(
        {
            "userId": user_id,
            "groupName": group_name,
            "fileUrl": file_url,
            "fileName": file_name,
        },
        ensure_ascii=False,
    )

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
    result = send_text_to_group(
        "changdongfeng_vojh", "sop测试1", "您好，本周直播即将开始"
    )
    print(f"文本: code={result.get('code')}, data={result.get('data')}")

    # 发送文件
    result = send_file_to_group(
        "ZhangSan",
        "重点客户答疑群",
        "https://oss.example.com/files/report.pdf",
        "月度报告.pdf",
    )
    print(f"文件: code={result.get('code')}, data={result.get('data')}")
