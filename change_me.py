from dataclasses import dataclass
import os
import requests
import secrets
import hashlib
import time
import uuid
import random
import urllib3

# SSL警告を無効化
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_KEY = "0326307d87bf8b33d2c2e3a254625554553623bee54e9568683265d17ef240f0"
SHARED_KEY = "marinchatZ1"
APP_VERSION = "8.4.2"
BASE_URL = "https://himitsutalk-039.himahimatalk.com"
TIMEOUT = 10

IOS_VERSIONS = ["17.0", "17.5", "18.0", "18.5"]
IOS_DEVICES = [
    "iPhone15,2",  # iPhone 14 Pro
    "iPhone15,3",  # iPhone 14 Pro Max
    "iPhone16,1",  # iPhone 15 Pro
    "iPhone16,2",  # iPhone 15 Pro Max
]
SCREEN_RESOLUTIONS_IOS = [
    "1179x2556",  # iPhone 14 Pro
    "1290x2796",  # iPhone 14 Pro Max
    "1179x2556",  # iPhone 15 Pro
    "1290x2796",  # iPhone 15 Pro Max
    "393x852",    # smaller size (from your sample)
]


def generate_ios_user_agent():
    ios_version = random.choice(IOS_VERSIONS)
    device = random.choice(IOS_DEVICES)
    resolution = random.choice(SCREEN_RESOLUTIONS_IOS)
    scale = "3x" if "Pro" in device or "16" in device else "2x"

    return f"himitsutalk 8.4.2 iOS {ios_version} ({device} {scale} {resolution})"


@dataclass
class TokenPair:
    access_token: str
    user_id: int


class himitsutalkClient:
    def __init__(self, token, user_id, proxy=None):
        self._device_uuid = str(uuid.uuid4()).upper()  # ランダムUUID生成
        self._token_pair = TokenPair(token, user_id)
        self._proxy = proxy
        self.proxies = {
            'http': proxy,
            'https': proxy
        } if proxy else None

    def _auth_headers(self, ts: int) -> dict:
        # ヘッダーはすべて半角英数字のみ

        device_info = generate_ios_user_agent()
        return {
            "Authorization": f"Bearer {self._token_pair.access_token}",
            "X-Timestamp": str(ts),
            "X-Device-Info": device_info,
            "X-Device-Uuid": "himitsutalk 8.4.2 iOS 18.5 (iPhone16,1 3x 393x852)",
            "X-Connection-Type": "wifi",
            "User-Agent": "himitsutalk 8.4.2 iOS 18.5 (iPhone16,1 3x 393x852)"
        }

    def generate_random_filename(self, ext="jpg") -> str:
        random_str = secrets.token_urlsafe(16)
        return f"user_avatar/{random_str}.{ext}"

    def _get_timestamp(self) -> int:
        return int(time.time())

    def _make_md5(self, ts: int, include_shared=False) -> str:
        src = f"{API_KEY}{self._device_uuid}{ts}"
        if include_shared:
            src += SHARED_KEY
        return hashlib.md5(src.encode()).hexdigest()

    def get_presigned_url(self, filename) -> str:
        ts = self._get_timestamp()
        headers = self._auth_headers(ts)
        headers["Connection"] = "close"
        params = {"file_names[]": filename}
        url = f"{BASE_URL}/v1/buckets/presigned_urls"
        # proxy_test.pyと同じシンプルなリクエスト
        r = requests.get(url, headers=headers,
                         params=params, proxies=self.proxies, verify=False)
        r.raise_for_status()
        return r.json()["presigned_urls"][0]["url"]

    def upload_to_presigned_url(self, presigned_url: str, image_path: str):
        print("アップロードする画像サイズ:", os.path.getsize(image_path))
        with open(image_path, "rb") as f:
            # proxy_test.pyと同じシンプルなリクエスト
            r = requests.put(
                presigned_url,
                data=f,
                headers={"Content-Type": "image/jpeg", "Connection": "close"},
                proxies=self.proxies,
                verify=False
            )
            print("PUTレスポンス:", r.status_code, r.content)
        r.raise_for_status()
        return True

    def update_profile_metadata(self, nickname, gender, age, filename):
        ts = self._get_timestamp()
        signed = self._make_md5(ts, include_shared=True)
        data = {
            "nickname": nickname,
            "gender": gender,
            "age": str(age),
            "place": "",
            "biography": "",
            "profile_icon_filename": filename,
            "uuid": self._device_uuid,
            "timestamp": ts,
            "api_key": API_KEY,
            "signed_info": signed,
        }
        headers = self._auth_headers(ts)
        headers["Connection"] = "close"
        # proxy_test.pyと同じシンプルなリクエスト
        resp = requests.put(
            f"{BASE_URL}/v3/users/edit",
            headers=headers,
            files={k: (None, v) for k, v in data.items()},
            proxies=self.proxies,
            verify=False
        )
        print("プロフィール編集APIレスポンス:", resp.status_code, resp.text)
        resp.raise_for_status()
        return resp.json()

    def set_user_photo(self, filename):
        ts = self._get_timestamp()
        headers = self._auth_headers(ts)
        headers["Content-Type"] = "application/json; charset=UTF-8"
        headers["Connection"] = "close"
        payload = {
            "user_photos": [
                {"main": True, "photo_filename": filename, "position": 1}
            ]
        }
        # proxy_test.pyと同じシンプルなリクエスト
        resp = requests.post(
            f"{BASE_URL}/v1/users/user_photos",
            headers=headers,
            json=payload,
            proxies=self.proxies,
            verify=False
        )
        print("user_photos登録APIレスポンス:", resp.status_code, resp.text)
        resp.raise_for_status()
        return resp.json()


# --- 実行例 ---
if __name__ == "__main__":
    # 必ず半角英数字だけの有効なトークンを使ってください
    token = "cbb5a6a9bfa34b97e4c02fc8eda1f7e4a64f61236b9e815d27f2881a9e3da9c7"
    user_id = 32650541
    proxy = "http://b1aa31bc096601743de9:c31ea60151896df8@gw.dataimpulse.com:823"

    client = himitsutalkClient(token, user_id, proxy)

    filename = client.generate_random_filename()
    presigned_url = client.get_presigned_url(filename)
    print("presigned_url:", presigned_url)
    print("アップロードファイル名:", filename)

    client.upload_to_presigned_url(presigned_url, "./images.jpg")
    print(f"画像アップロードOK: {filename}")

    client.update_profile_metadata("konna", "-1", 18, filename)
    client.set_user_photo(filename)

    print("すべての処理が完了しました。アプリでプロフィール画像が反映されているか確認してください。")
