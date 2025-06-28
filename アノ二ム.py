#!/usr/bin/env python3
# marinchat_client.py
import hashlib
import os
import time
import logging
import requests
from dataclasses import dataclass
from typing import Optional
import json
import uuid


# ── 設定値 ──────────────────────────────────────────────
API_KEY = "0326307d87bf8b33d2c2e3a254625554553623bee54e9568683265d17ef240f0"
SHARED_KEY = "marinchatZ1"
DEVICE_UUID = str(uuid.uuid4()).upper()
SIGNED_VERSION = "4SHhGIDSlMR9PH7oOfEMWHIHpd6zeC4+DVQgpkxv6gQ="
APP_VERSION = "8.4.2"
BASE_URL = "https://himitsutalk-039.himahimatalk.com"
TIMEOUT = 10
LOG_LEVEL = logging.INFO
# プロキシ設定
PROXY_URL = "http://b1aa31bc096601743de9:c31ea60151896df8@gw.dataimpulse.com:823"
# ───────────────────────────────────────────────────────

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


@dataclass
class TokenPair:
    access_token: str
    user_id: int


class MarinChatClient:
    def __init__(self) -> None:
        self._device_uuid = DEVICE_UUID
        self._client_ip: str | None = None
        self._token_pair: Optional[TokenPair] = None

    # --------------- 低レベル共通メソッド -----------------

    def _create_session(self) -> requests.Session:
        """新しいセッションを作成してプロキシとヘッダーを設定"""
        session = requests.Session()
        # プロキシ設定
        proxies = {
            'http': PROXY_URL,
            'https': PROXY_URL
        }
        session.proxies.update(proxies)
        session.headers.update(self._default_headers())
        return session

    def _default_headers(self) -> dict[str, str]:
        ua = f"himitsutalk {APP_VERSION} Android 14 (1080x2205; sdk_gphone64_arm64)"
        return {
            "User-Agent": "himitsutalk 8.4.2 iOS 18.5 (iPhone16,1 3x 393x852)",
            "Accept-Language": "ja",
            "X-Device-Info": ua,
            "X-Device-Uuid": self._device_uuid,
            "X-Connection-Type": "cellular",
            "X-Connection-Speed": "",
        }

    def _get_timestamp(self) -> int:
        r = self._create_session().get(
            f"{BASE_URL}/v2/users/timestamp", timeout=TIMEOUT)
        r.raise_for_status()
        body = r.json()
        self._client_ip = body.get("ip_address", self._client_ip)
        return body["time"]

    def _make_md5(self, ts: int, include_shared=False) -> str:
        src = f"{API_KEY}{self._device_uuid}{ts}"
        if include_shared:
            src += SHARED_KEY
        return hashlib.md5(src.encode()).hexdigest()

    def _auth_headers(self, ts: int) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token_pair.access_token}",
            "X-Timestamp": str(ts),
            "X-Client-Ip": self._client_ip or "",
        }

    def _get_session_ip(self, session: requests.Session) -> str:
        """セッションのIPアドレスを取得"""
        try:
            # IPアドレス確認用のサービスを使用
            response = session.get("https://httpbin.org/ip", timeout=TIMEOUT)
            response.raise_for_status()
            ip_data = response.json()
            return ip_data.get("origin", "不明")
        except Exception as e:
            logging.warning(f"IPアドレス取得失敗: {e}")
            return "取得失敗"

    # --------------- 高レベル API ラッパ ------------------
    def create_user(self) -> TokenPair:
        ts = self._get_timestamp()
        signed = self._make_md5(ts, include_shared=False)
        data = {
            "gender": -1,
            "app_version": "8.4.2",
            "app": "himitsutalk",
            "nickname": "dadada",
            "signed_version": SIGNED_VERSION,
            "uuid": self._device_uuid,
            "timestamp": ts,
            "api_key": API_KEY,
            "signed_info": signed
        }

        json_body = json.dumps(data, separators=(',', ':'))  # ←改行や空白を除去
        headers = {
            "X-Timestamp": str(ts),
            "X-Device-Info": "himitsutalk 8.4.2 iOS 18.5 (iPhone16,1 3x 393x852)",
            "X-Device-Uuid": self._device_uuid,
            "X-Connection-Type": "wifi",
            "X-Connection-Speed": "-1.000",
            "User-Agent": "himitsutalk 8.4.2 iOS 18.5 (iPhone16,1 3x 393x852)",
            "Content-Type": "application/json"
        }

        session = self._create_session()
        session_ip = self._get_session_ip(session)
        logging.info(f"🌐 create_user セッションIP: {session_ip}")

        r = session.post(f"{BASE_URL}/api/v3/users",
                         headers=headers,
                         data=json_body.encode('utf-8'),
                         timeout=TIMEOUT)

        print("== リクエストデバッグ ==")
        print("ステータスコード:", r.status_code)
        print("レスポンスヘッダー:", dict(r.headers))
        print("レスポンス本文:", r.text)
        print("API_KEY:", API_KEY)
        print("UUID:", DEVICE_UUID)
        print("SIGNED_VERSION:", SIGNED_VERSION)
        print("セッションIP:", session_ip)
        r.raise_for_status()
        body = r.json()
        self._token_pair = TokenPair(body["access_token"], body["user_id"])
        logging.info("✅ ユーザー作成 OK user_id=%s", body["user_id"])
        return self._token_pair

    def create_room(self, with_user_id: int) -> int:
        ts = self._get_timestamp()
        headers = {
            **self._auth_headers(ts),
            "matching_id": "199558734",
            "hima_chat": "true",
        }
        data = {"with_user_id": str(with_user_id)}

        session = self._create_session()
        session_ip = self._get_session_ip(session)
        logging.info(f"🌐 create_room セッションIP: {session_ip}")

        r = session.post(f"{BASE_URL}/v1/chat_rooms/new",
                         headers=headers, data=data, timeout=TIMEOUT)
        r.raise_for_status()
        room_id = r.json()["room_id"]
        logging.info("✅ ルーム作成 OK room_id=%s", room_id)
        return room_id

    def send_message(self, room_id: int, text: str) -> None:
        ts = self._get_timestamp()
        signed = self._make_md5(ts, include_shared=True)
        headers = self._auth_headers(
            ts) | {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "message_type": "text",
            "text": text,
            "uuid": self._device_uuid,
            "timestamp": ts,
            "api_key": API_KEY,
            "signed_info": signed,
        }

        session = self._create_session()
        session_ip = self._get_session_ip(session)
        logging.info(f"🌐 send_message セッションIP: {session_ip}")

        r = session.post(f"{BASE_URL}/v3/chat_rooms/{room_id}/messages/new",
                         headers=headers, data=data, timeout=TIMEOUT)
        r.raise_for_status()
        logging.info("✅ メッセージ送信 OK")


# ------------------------- CLI ---------------------------
if __name__ == "__main__":
    client = MarinChatClient()
    tk = client.create_user()
    room = client.create_room(with_user_id=32809621)
    client.send_message(room, "こんにちは！")
