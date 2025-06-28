import hashlib
import os
import time
import logging
import requests
import json
from dataclasses import dataclass
from typing import Optional, List
import uuid
import random
import secrets
from collections import OrderedDict
import urllib3

# SSL警告を無効化
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 設定値 ──────────────────────────────────────────────
API_KEY = "0326307d87bf8b33d2c2e3a254625554553623bee54e9568683265d17ef240f0"
SHARED_KEY = "marinchatZ1"
APP_VERSION = "8.4.2"
BASE_URL = "https://himitsutalk-039.himahimatalk.com"
TIMEOUT = 100
LOG_LEVEL = logging.INFO
# ───────────────────────────────────────────────────────

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

current_gender_selection = None


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
    def __init__(self) -> None:
        self._device_uuid = str(uuid.uuid4()).upper()
        self._token_pair: Optional[TokenPair] = None
        self._proxy: Optional[dict] = None
        self._user_agent: Optional[str] = None
        self._client_ip = ""

    def set_user_agent(self, user_agent: str, device_uuid: str):
        """ユーザーエージェントとデバイスUUIDを設定"""
        self._user_agent = user_agent
        self._device_uuid = device_uuid

    def _default_headers(self) -> OrderedDict:
        # MacとWindowsで統一されたUser-Agentを使用
        ua = generate_ios_user_agent()
        # ヘッダーの順序を明示的に指定してプラットフォーム間の一貫性を確保
        headers = OrderedDict()
        headers["User-Agent"] = "himitsutalk 8.4.2 iOS 18.5 (iPhone16,1 3x 393x852)"
        headers["Accept-Language"] = "ja"
        headers["X-Device-Info"] = ua
        headers["X-Device-Uuid"] = self._device_uuid
        headers["X-Connection-Type"] = "cellular"
        headers["X-Connection-Speed"] = ""
        return headers

    def set_proxy(self, proxy_info: Optional[dict] = None):
        """プロキシを設定
        Args:
            proxy_info (dict, optional): {
                "host": "gw.dataimpulse.com",
                "port": "823",
                "username": "blaa31bc096601743de9",
                "password": "c31ea60151896df8"
            }
        """
        self._proxy = proxy_info
        if proxy_info:
            logging.info(
                f"🌐 プロキシを設定: {proxy_info['host']}:{proxy_info['port']}")
        else:
            logging.info("プロキシ設定を解除しました")

    def _get_proxies(self) -> Optional[dict]:
        if not self._proxy:
            return None
        proxy_url = f"http://{self._proxy['username']}:{self._proxy['password']}@{self._proxy['host']}:{self._proxy['port']}"
        return {
            "http": proxy_url,
            "https": proxy_url
        }

    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """共通のリクエスト処理
        全てのリクエストはこのメソッドを通して行う
        """
        max_retries = 3
        retry_delay = 1  # 初期遅延時間（秒）

        for attempt in range(max_retries):
            try:
                # プロキシ設定の確認と出力
                if self._proxy:
                    logging.info(
                        f"🌐 プロキシ使用中: {self._proxy['host']}:{self._proxy['port']}")
                    kwargs['proxies'] = self._get_proxies()

                # リクエストの詳細をデバッグ出力
                logging.debug(f"📤 {method} リクエスト: {url}")
                if "headers" in kwargs:
                    logging.debug("📤 リクエストヘッダー: %s", kwargs["headers"])
                if "data" in kwargs:
                    logging.debug("📤 リクエストボディ: %s", kwargs["data"])
                if "params" in kwargs:
                    logging.debug("📤 リクエストパラメータ: %s", kwargs["params"])

                # keep-aliveを無効化
                if "headers" not in kwargs:
                    kwargs["headers"] = {}
                kwargs["headers"]["Connection"] = "close"

                kwargs.setdefault("verify", False)

                # 新しいセッションを作成して即座に閉じる
                with requests.Session() as session:
                    # セッションレベルでもConnection: closeを設定
                    session.headers.update({"Connection": "close"})

                    # 接続プールの設定
                    adapter = requests.adapters.HTTPAdapter(
                        max_retries=0,  # セッションレベルでのリトライは無効化
                        pool_connections=1,  # 接続プールサイズを最小に
                        pool_maxsize=1,      # 最大接続数を1に制限
                    )
                    session.mount('http://', adapter)
                    session.mount('https://', adapter)

                    # timeoutが既にkwargsにある場合はそれを使用、なければTIMEOUTを使用
                    timeout_value = kwargs.pop('timeout', TIMEOUT)
                    response = session.request(
                        method, url, timeout=timeout_value, **kwargs)

                    # レスポンスの詳細をデバッグ出力
                    logging.info(f"📥 レスポンスステータス: {response.status_code}")
                    logging.debug("📥 レスポンスヘッダー: %s", dict(response.headers))
                    logging.debug("📥 レスポンスボディ: %s", response.text)

                    return response

            except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
                error_str = str(e)
                if attempt < max_retries - 1:
                    logging.warning(
                        f"⚠️ 接続エラー（試行 {attempt + 1}/{max_retries}）: {error_str}")
                    logging.info(f"🔄 {retry_delay}秒後にリトライします...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数バックオフ
                    continue
                else:
                    logging.error(f"❌ 接続エラー（最大試行回数に到達）: {error_str}")
                    raise

            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    logging.warning(
                        f"⚠️ タイムアウトエラー（試行 {attempt + 1}/{max_retries}）: {str(e)}")
                    logging.info(f"🔄 {retry_delay}秒後にリトライします...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    logging.error(f"❌ タイムアウトエラー（最大試行回数に到達）: {str(e)}")
                    raise

            except Exception as e:
                # その他のエラーは即座に再発生
                logging.error(f"❌ リクエストエラー: {str(e)}")
                raise

        # ここには到達しないはず
        raise Exception("予期しないエラー: リトライループを抜けました")

    def _get_timestamp(self) -> int:
        return int(time.time())

    def _make_md5(self, ts: int, include_shared=False) -> str:
        src = f"{API_KEY}{self._device_uuid}{ts}"
        if include_shared:
            src += SHARED_KEY
        # プラットフォーム間で同じハッシュを生成するため、UTF-8エンコーディングを明示
        return hashlib.md5(src.encode('utf-8')).hexdigest()

    def _auth_headers(self, ts: int) -> OrderedDict:
        headers = OrderedDict()
        headers["Authorization"] = f"Bearer {self._token_pair.access_token}"
        headers["X-Timestamp"] = str(ts)
        headers["X-Client-Ip"] = self._client_ip
        return headers

    def create_user(self, age: str = "18", gender: str = "-1", nickname: str = None) -> TokenPair:
        """ユーザーを作成する
        Args:
            age (str): ユーザーの年齢（デフォルト: "18"）
            gender (str): 性別（"-1": 未設定, "1": 女性）（デフォルト: "-1"）
            nickname (str, optional): ニックネーム（指定がない場合は自動生成）
        Returns:
            TokenPair: アクセストークンとユーザーIDのペア
        """
        max_retries = 2

        for attempt in range(max_retries):
            try:
                ts = self._get_timestamp()
                signed = self._make_md5(ts, include_shared=False)

                # 署名計算の詳細をログ出力
                # logging.info(f"🔍 署名計算詳細:")
                # logging.info(f"   Timestamp: {ts}")
                # logging.info(f"   Device UUID: {self._device_uuid}")
                # logging.info(f"   MD5 Hash: {signed}")

                if not nickname:
                    nickname = f"user{ts % 10000:04d}"

                # ヘッダーを明確な順序で構築（プラットフォーム間の一貫性確保）
                headers = OrderedDict()
                # 基本ヘッダーを追加
                base_headers = self._default_headers()
                for key, value in base_headers.items():
                    headers[key] = value
                # API固有ヘッダーを追加（順序を統一）
                headers["X-Timestamp"] = str(ts)
                headers["X-Client-Ip"] = ""
                headers["Accept"] = "application/json"
                headers["Content-Type"] = "application/x-www-form-urlencoded"

                # リクエスト概要をログ出力
                logging.info(
                    f"🔍 ユーザー作成リクエスト: nickname={nickname}, gender={gender}, age={age}")
                # logging.info(f"📤 Headers順序: {list(headers.keys())}")

                # データも順序を統一（プラットフォーム間の一貫性確保）
                data = OrderedDict()
                data["timestamp"] = str(ts)  # 文字列として統一
                data["api_key"] = str(API_KEY)
                data["uuid"] = str(self._device_uuid)
                data["signed_info"] = str(signed)
                data["app"] = "himitsutalk"
                data["app_version"] = "8.4.2"  # 元の値に戻す
                data["signed_version"] = "4SHhGIDSlMR9PH7oOfEMWHIHpd6zeC4+DVQgpkxv6gQ="
                data["nickname"] = str(nickname)  # 明示的に文字列に変換
                data["gender"] = str(gender)
                data["age"] = str(age)
                data["place"] = ""
                data["biography"] = ""

                logging.info(f"📤 Data順序: {list(data.keys())}")

                # form-dataとして送信（APIの期待する形式）
                r = self._make_request("POST", f"{BASE_URL}/api/v3/users",
                                       headers=headers,
                                       data=data)  # form-dataとして送信
                r.raise_for_status()
                body = r.json()
                self._token_pair = TokenPair(
                    body["access_token"], body["user_id"])
                logging.info("✅ ユーザー作成 OK user_id=%s age=%s gender=%s nickname=%s",
                             body["user_id"], age, gender, nickname)
                return self._token_pair

            except requests.exceptions.HTTPError as e:
                # レスポンスの詳細をログ出力
                status_code = e.response.status_code
                try:
                    response_text = e.response.text
                    logging.error(f"📥 ユーザー作成レスポンス: ステータス={status_code}")
                    logging.error(f"📄 レスポンス内容: {response_text}")
                except:
                    logging.error(
                        f"📥 ユーザー作成レスポンス: ステータス={status_code} (レスポンス内容取得失敗)")

                if status_code in [403, 502] and attempt < max_retries - 1:
                    logging.warning(
                        f"エラー {status_code}。リトライします。(試行 {attempt + 1}/{max_retries})")
                    continue
                logging.error("❌ ユーザー作成失敗: %s", str(e))
                raise
            except Exception as e:
                logging.error("❌ ユーザー作成失敗: %s", str(e))
                raise

    def create_room(self, with_user_id: int) -> int:
        ts = self._get_timestamp()
        headers = {
            **self._auth_headers(ts),
            "matching_id": str(random.randint(100000000, 999999999)),
            "hima_chat": "true",
        }
        data = {"with_user_id": str(with_user_id)}
        r = self._make_request("POST", f"{BASE_URL}/v1/chat_rooms/new",
                               headers=headers, data=data)

        # エラーレスポンスの詳細を表示
        if not r.ok:
            try:
                error_data = r.json()
                error_code = error_data.get("error_code")
                error_message = error_data.get("message", "")

                logging.error(
                    f"❌ ルーム作成失敗 (ステータス: {r.status_code}): {r.text}")

                # 各エラーコードに応じた適切なメッセージを表示
                if error_code == -313:
                    raise Exception(
                        f"相互フォローユーザー限定: このユーザーは相互フォローしているユーザーとのみチャットを受け付けています (user_id: {with_user_id})")
                elif "Captcha required" in r.text or error_code == -29:
                    raise Exception(f"Captcha required: {r.text}")
                else:
                    # その他のエラーの場合は汎用メッセージ
                    raise Exception(
                        f"ルーム作成エラー (コード: {error_code}): {error_message}")

            except Exception as json_error:
                if "相互フォローユーザー限定" in str(json_error):
                    raise json_error
                elif "Captcha required" not in str(json_error):
                    logging.error(
                        f"❌ ルーム作成失敗 (ステータス: {r.status_code}): {r.text}")

                # Captcha requiredエラーの場合は専用の例外を発生
                if "Captcha required" in r.text:
                    raise Exception(f"Captcha required: {r.text}")

                raise json_error

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
        r = self._make_request("POST", f"{BASE_URL}/v3/chat_rooms/{room_id}/messages/new",
                               headers=headers, data=data)

        # エラーレスポンスの詳細を表示
        if not r.ok:
            try:
                error_data = r.json()
                error_code = error_data.get("error_code")
                error_message = error_data.get("message", "")

                logging.error(
                    f"❌ メッセージ送信失敗 (ステータス: {r.status_code}): {error_data}")

                # 各エラーコードに応じた適切なメッセージを表示
                if error_code == -313:
                    raise Exception(
                        f"相互フォローユーザー限定: このユーザーは相互フォローしているユーザーとのみチャットを受け付けています")
                elif "Captcha required" in r.text or error_code == -29:
                    raise Exception(f"Captcha required: {r.text}")
                else:
                    # その他のエラーの場合は汎用メッセージ
                    raise Exception(
                        f"メッセージ送信エラー (コード: {error_code}): {error_message}")

            except Exception as json_error:
                if "相互フォローユーザー限定" in str(json_error):
                    raise json_error
                elif "Captcha required" not in str(json_error):
                    logging.error(
                        f"❌ メッセージ送信失敗 (ステータス: {r.status_code}): {r.text}")

                # Captcha requiredエラーの場合は専用の例外を発生
                if "Captcha required" in r.text:
                    raise Exception(f"Captcha required: {r.text}")

                raise json_error

            r.raise_for_status()

        logging.info("✅ メッセージ送信 OK")

    def get_new_users(self, page: int = 0) -> List[dict]:
        """新規ユーザーリストを取得する"""
        ts = self._get_timestamp()
        headers = {
            "X-Timestamp": str(ts),
            "X-Client-Ip": "",
            "X-Connection-Type": "wifi",
            "Accept-Language": "ja"
        }

        params = {"page": page}
        r = self._make_request("GET", f"{BASE_URL}/v1/users/search",
                               headers=headers,
                               params=params)
        r.raise_for_status()

        response = r.json()
        if response.get("result") == "success":
            users = response.get("users", [])
            logging.info("✅ 新規ユーザー取得 OK: %d件", len(users))
            return users
        return []

    def filter_target_users(self, users: List[dict], gender: Optional[str] = None) -> List[dict]:
        """送信対象のユーザーをフィルタリング"""
        filtered = []

        # 送信者の性別を文字列で表示
        sender_gender_name = "女性" if gender == "1" else "未設定（男性として扱う）" if gender == "-1" else "不明"
        logging.info(
            f"🔍 フィルタリング開始: 送信者={sender_gender_name} (gender={gender}), 対象ユーザー数={len(users)}")

        for user in users:
            try:
                # 性別フィルター（0: 未設定, 1: 女性）
                user_gender = user.get("gender", 0)  # デフォルト値を0（未設定）に
                user_id = user.get("id", "不明")

                # 相手の性別を文字列で表示
                target_gender_name = "女性" if user_gender == 1 else "未設定（男性）" if user_gender == 0 else "不明"

                if gender == "1":  # 女性アカウントは男性（未設定）のみに送信
                    if user_gender != 0:  # 相手が女性の場合はスキップ
                        logging.info(
                            f"⚠️ スキップ: 女性アカウント→{target_gender_name}(ID:{user_id}) - 女性は男性にのみ送信可能")
                        continue
                    else:
                        logging.info(
                            f"✅ 送信対象: 女性アカウント→{target_gender_name}(ID:{user_id}) - 送信します")
                elif gender == "-1":  # 未設定アカウントは女性/未設定に送信
                    if user_gender == 0:  # 相手が未設定（男性）の場合はスキップ
                        logging.info(
                            f"⚠️ スキップ: 未設定アカウント→{target_gender_name}(ID:{user_id}) - 未設定は女性にのみ送信可能")
                        continue
                    else:
                        logging.info(
                            f"✅ 送信対象: 未設定アカウント→{target_gender_name}(ID:{user_id}) - 送信します")

                # その他の条件（必要に応じて追加）
                if user.get("is_private", False):  # 非公開アカウントは除外
                    logging.info(
                        f"⚠️ スキップ: {target_gender_name}(ID:{user_id}) - 非公開アカウントのため除外")
                    continue

                filtered.append(user)
            except Exception as e:
                logging.error(f"ユーザーフィルタリングエラー: {str(e)}, user={user}")
                continue

        logging.info(f"🎯 フィルタリング完了: {len(filtered)}/{len(users)}件が送信対象")
        return filtered

    def delete_account(self) -> bool:
        """アカウントを削除する
        Returns:
            bool: 削除に成功したかどうか
        """
        try:
            ts = self._get_timestamp()
            headers = {
                **self._default_headers(),
                **self._auth_headers(ts),
                "Content-Type": "application/x-www-form-urlencoded"
            }
            r = self._make_request("POST", f"{BASE_URL}/v1/users/destroy",
                                   headers=headers)

            # レスポンスの詳細をログ出力
            logging.info(f"📥 アカウント削除レスポンス: ステータス={r.status_code}")

            # JSONパースを安全に実行
            try:
                data = r.json()
                logging.info(f"📄 レスポンス内容: {data}")

                if "error_code" in data and data["error_code"] == -26:
                    logging.warning(
                        f"アカウント削除失敗: アカウント作成から3日以上経過していないと削除できません (user_id={self._token_pair.user_id})")
                    return False
            except ValueError:
                # JSONパースに失敗した場合はレスポンステキストをログ出力
                logging.warning(f"⚠️ JSONパースに失敗、レスポンステキスト: {r.text[:200]}")
                logging.info(
                    f"📄 レスポンス詳細: Status={r.status_code}, Headers={dict(r.headers)}")

            r.raise_for_status()
            logging.info(f"✅ アカウント削除成功: user_id={self._token_pair.user_id}")
            return True

        except Exception as e:
            logging.error(f"アカウント削除時にエラーが発生: {str(e)}")
            return False

    def generate_random_filename(self, ext="jpg") -> str:
        """ランダムなファイル名を生成"""
        random_str = secrets.token_urlsafe(16)
        return f"user_avatar/{random_str}.{ext}"

    def get_presigned_url(self, filename: str) -> str:
        """S3の署名付きURLを取得"""
        try:
            ts = self._get_timestamp()
            headers = self._auth_headers(ts)
            params = {"file_names[]": filename}
            url = f"{BASE_URL}/v1/buckets/presigned_urls"

            r = self._make_request("GET", url, headers=headers, params=params)

            # エラーレスポンスのチェック
            if not r.ok:
                try:
                    response_data = r.json()
                    if "Captcha required" in r.text or response_data.get("error_code") == -29:
                        logging.error(
                            f"🔐 署名付きURL取得でCaptchaが必要です: {response_data}")
                        raise Exception(f"Captcha required: {r.text}")
                except ValueError:
                    if "Captcha required" in r.text:
                        raise Exception(f"Captcha required: {r.text}")

            r.raise_for_status()
            return r.json()["presigned_urls"][0]["url"]
        except Exception as e:
            # Captchaエラーの場合は再発生
            if "Captcha required" in str(e):
                raise
            logging.error(f"❌ 署名付きURL取得エラー: {str(e)}")
            raise

    def upload_to_presigned_url(self, presigned_url: str, image_path: str) -> bool:
        """署名付きURLに画像をアップロード"""
        max_retries = 3
        retry_delay = 2  # 秒

        for attempt in range(max_retries):
            try:
                with open(image_path, "rb") as f:
                    # _make_requestを使用してリトライ機能を活用
                    resp = self._make_request(
                        "PUT",
                        presigned_url,
                        data=f,
                        headers={"Content-Type": "image/jpeg"}
                    )
                    logging.info(f"📥 画像アップロードレスポンス: ステータス={resp.status_code}")

                    # レスポンス内容をログ出力
                    if resp.text:
                        logging.info(f"📄 アップロードレスポンス内容: {resp.text[:200]}")

                    resp.raise_for_status()
                    logging.info(f"✅ 画像アップロード成功")
                    return True

            except requests.exceptions.HTTPError as e:
                logging.error(
                    f"❌ 画像アップロードHTTPエラー: ステータス={resp.status_code}, レスポンス={resp.text[:200]}")
                return False

            except FileNotFoundError:
                logging.error(f"❌ 画像ファイルが見つかりません: {image_path}")
                return False

            except Exception as e:
                if attempt < max_retries - 1:
                    logging.warning(
                        f"⚠️ 画像アップロード予期しないエラー（試行 {attempt + 1}/{max_retries}）: {str(e)}")
                    logging.info(f"🔄 {retry_delay}秒後にリトライします...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    logging.error(f"❌ 画像アップロードエラー（最大試行回数に到達）: {str(e)}")
                    return False

        return False

    def update_profile_metadata(self, nickname: str, gender: str, age: str, filename: str) -> bool:
        """プロフィールメタデータを更新"""
        try:
            ts = self._get_timestamp()
            signed = self._make_md5(ts, include_shared=True)
            data = {
                "nickname": str(nickname),  # 明示的に文字列に変換
                "gender": str(gender),
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

            # multipart/form-dataとして送信
            files = {k: (None, v) for k, v in data.items()}

            # _make_requestを使用してリトライ機能を活用
            resp = self._make_request(
                "PUT",
                f"{BASE_URL}/v3/users/edit",
                headers=headers,
                files=files
            )
            logging.info(f"📥 プロフィール更新レスポンス: ステータス={resp.status_code}")

            # レスポンス内容をログ出力
            try:
                response_data = resp.json()
                logging.info(f"📄 レスポンス内容: {response_data}")
            except:
                logging.info(f"📄 レスポンス内容（テキスト）: {resp.text[:200]}")

            resp.raise_for_status()
            logging.info(f"✅ プロフィール更新成功: {nickname}")
            return True
        except requests.exceptions.HTTPError as e:
            # Captchaエラーのチェック
            try:
                response_data = resp.json()
                if "Captcha required" in resp.text or response_data.get("error_code") == -29:
                    logging.error(f"🔐 プロフィール更新でCaptchaが必要です: {response_data}")
                    raise Exception(f"Captcha required: {resp.text}")
            except ValueError:
                # JSONパースに失敗した場合でもCaptchaチェック
                if "Captcha required" in resp.text:
                    raise Exception(f"Captcha required: {resp.text}")

            logging.error(
                f"❌ プロフィール更新HTTPエラー: ステータス={resp.status_code}, レスポンス={resp.text[:200]}")
            return False
        except Exception as e:
            # Captchaエラーの場合は再発生
            if "Captcha required" in str(e):
                raise
            logging.error(f"❌ プロフィール更新エラー: {str(e)}")
            return False

    def set_user_photo(self, filename: str) -> bool:
        """ユーザー写真を設定"""
        try:
            ts = self._get_timestamp()
            headers = {
                **self._auth_headers(ts),
                "Content-Type": "application/json; charset=UTF-8"
            }
            payload = {
                "user_photos": [
                    {"main": True, "photo_filename": filename, "position": 1}
                ]
            }

            r = self._make_request("POST", f"{BASE_URL}/v1/users/user_photos",
                                   headers=headers, json=payload)
            logging.info(f"📥 ユーザー写真設定レスポンス: ステータス={r.status_code}")

            # レスポンス内容をログ出力
            try:
                response_data = r.json()
                logging.info(f"📄 ユーザー写真設定レスポンス内容: {response_data}")

                # Captchaエラーのチェック
                if not r.ok and ("Captcha required" in r.text or response_data.get("error_code") == -29):
                    logging.error(f"🔐 ユーザー写真設定でCaptchaが必要です: {response_data}")
                    raise Exception(f"Captcha required: {r.text}")
            except ValueError:
                logging.info(f"📄 ユーザー写真設定レスポンス内容（テキスト）: {r.text[:200]}")
                # JSONパースに失敗した場合でもCaptchaチェック
                if not r.ok and "Captcha required" in r.text:
                    raise Exception(f"Captcha required: {r.text}")

            r.raise_for_status()
            logging.info(f"✅ ユーザー写真設定成功: {filename}")
            return True

        except Exception as e:
            # Captchaエラーの場合は再発生
            if "Captcha required" in str(e):
                raise
            logging.error(f"❌ ユーザー写真設定エラー: {str(e)}")
            return False

    def update_profile(self, nickname: str, gender: str, age: str, image_path: str) -> bool:
        """プロフィールを完全に更新（画像 + メタデータ）"""
        try:
            logging.info(
                f"🚀 プロフィール完全更新開始: ニックネーム={nickname}, 性別={gender}, 年齢={age}")

            # 1. ランダムなファイル名を生成
            filename = self.generate_random_filename()
            logging.info(f"📝 ファイル名生成: {filename}")

            # 2. 署名付きURLを取得
            logging.info(f"🔗 署名付きURL取得開始")
            presigned_url = self.get_presigned_url(filename)
            logging.info(f"✅ 署名付きURL取得成功")

            # 3. 画像をアップロード
            logging.info(f"📤 画像アップロード開始: {image_path}")
            if not self.upload_to_presigned_url(presigned_url, image_path):
                logging.error(f"❌ 画像アップロード失敗")
                return False

            # 4. プロフィールメタデータを更新
            logging.info(f"📝 プロフィールメタデータ更新開始")
            if not self.update_profile_metadata(nickname, gender, age, filename):
                logging.error(f"❌ プロフィールメタデータ更新失敗")
                return False

            # 5. ユーザー写真を設定
            logging.info(f"🖼️ ユーザー写真設定開始")
            if not self.set_user_photo(filename):
                logging.error(f"❌ ユーザー写真設定失敗")
                return False

            logging.info(f"✅ プロフィール完全更新成功: {nickname}")
            return True
        except Exception as e:
            # Captchaエラーの場合は再発生
            if "Captcha required" in str(e):
                logging.error(f"🔐 プロフィール更新でCaptchaエラーが発生しました: {str(e)}")
                raise
            logging.error(f"❌ プロフィール完全更新エラー: {str(e)}")
            return False

    def get_email_from_api(self) -> Optional[dict]:
        """メールAPIからメールアドレスを取得する（プロキシを使用しない）"""
        try:
            # API URLは固定
            url = "https://api.firstmail.ltd/v1/market/buy/mail?type=3"

            # データベースからAPIキーのみ取得
            from database import Database
            db = Database()
            mail_setting = db.get_mail_api_setting()

            if not mail_setting:
                logging.error("メールAPI設定が見つかりません")
                return None

            api_key = mail_setting["api_key"]

            headers = {
                "accept": "application/json",
                "X-API-KEY": api_key,
                "Connection": "close"
            }

            # _make_requestを使用してリトライ機能を活用（プロキシは使用しない）
            # 一時的にプロキシ設定を無効化
            original_proxy = self._proxy
            self._proxy = None

            try:
                response = self._make_request(
                    "GET", url, headers=headers, timeout=30)
            finally:
                # プロキシ設定を復元
                self._proxy = original_proxy

            data = response.json()
            if not data.get("error", True):
                login_info = data.get("login", "")
                if ":" in login_info:
                    email, password = login_info.split(":", 1)
                    logging.info(f"✅ メールアドレス取得成功: {email}")
                    return {
                        "email": email,
                        "password": password,
                        "left": data.get("left", 0)
                    }

            logging.error(f"メールアドレス取得失敗: {data}")
            return None

        except Exception as e:
            logging.error(f"メールアドレス取得エラー: {str(e)}")
            return None

    def register_email(self, email: str, password: str) -> bool:
        """アカウントにメールアドレスを登録する"""
        try:
            if not self._token_pair:
                logging.error("トークンが設定されていません")
                return False

            ts = self._get_timestamp()

            # requests に multipart/form-data を組み立てさせる
            files = {
                "email": (None, email),
                "password": (None, password),
            }

            headers = {
                **self._default_headers(),
                **self._auth_headers(ts),
            }

            response = self._make_request(
                "POST",
                f"{BASE_URL}/v2/users/login_update",
                headers=headers,
                files=files,
            )

            response.raise_for_status()
            logging.info(f"✅ メール登録成功: {email}")
            return True

        except Exception as e:
            logging.error(f"メール登録エラー: {str(e)}")
            return False

    def register_email_for_account(self) -> bool:
        """アカウントにメールアドレスを自動取得・登録する"""
        try:
            # メールアドレスを取得
            email_data = self.get_email_from_api()
            if not email_data:
                logging.error("メールアドレスの取得に失敗しました")
                return False

            # メールアドレスを登録
            success = self.register_email(
                email_data["email"], email_data["password"])
            if success:
                # データベースにメール情報を保存
                try:
                    from database import Database
                    db = Database()
                    db_success = db.update_account_email_password(
                        self._token_pair.user_id,
                        email_data["email"],
                        email_data["password"]
                    )
                    if db_success:
                        logging.info(
                            f"✅ アカウントにメール登録完了（DB更新済み）: {email_data['email']}")
                    else:
                        logging.warning(
                            f"⚠️ メール登録成功したがDB更新失敗: {email_data['email']}")
                except Exception as db_error:
                    logging.error(f"❌ データベース更新エラー: {str(db_error)}")

            return success

        except Exception as e:
            logging.error(f"メール登録処理エラー: {str(e)}")
            return False

    def is_banned(self) -> bool:
        """アカウントがBANされているか確認する"""
        try:
            ts = self._get_timestamp()
            headers = {
                **self._default_headers(),
                **self._auth_headers(ts),
            }
            r = self._make_request("GET", f"{BASE_URL}/v1/users/block_ids",
                                   headers=headers)

            # 404エラーでuser not foundの場合はBANされている
            if r.status_code == 404:
                try:
                    data = r.json()
                    if data.get("error_code") == -5 and "user not found" in data.get("message", ""):
                        logging.warning(
                            f"🚫 アカウントがBANされています (user_id={self._token_pair.user_id})")
                        return True
                except:
                    pass

            return False

        except Exception as e:
            logging.error(f"BAN確認エラー: {str(e)}")
            return False

    def verify_captcha(self, token: str) -> bool:
        """reCAPTCHAトークンを検証する
        Args:
            token (str): reCAPTCHAトークン
        Returns:
            bool: 検証に成功したかどうか
        """
        retry_count = 0

        while True:  # 無限リトライ
            try:
                retry_count += 1
                ts = self._get_timestamp()
                headers = {
                    **self._default_headers(),
                    **self._auth_headers(ts),
                    "Content-Type": "application/json",
                    "X-Client-Ip": self._client_ip if self._client_ip else ""
                }

                # リクエストボディ
                data = {
                    "token": token,
                    "device_type": "ios"
                }

                logging.info(f"🔍 reCAPTCHA検証開始（試行 {retry_count}回目）")

                r = self._make_request("POST", f"{BASE_URL}/v1/users/verify_captcha",
                                       headers=headers, json=data)

                # レスポンスの詳細をログ出力
                logging.info(f"📥 reCAPTCHA検証レスポンス: ステータス={r.status_code}")

                # エラーレスポンスの確認
                if not r.ok:
                    try:
                        error_data = r.json()
                        error_message = error_data.get("message", "")

                        # IP BANエラーの場合は即座にリトライ（ルーティングプロキシ使用）
                        if "IP banned" in error_message or "ip ban" in error_message.lower():
                            logging.warning(f"⚠️ IP BANエラー検出。即座にリトライします...")
                            continue
                        else:
                            logging.error(f"❌ reCAPTCHA検証エラー: {error_data}")
                            return False
                    except:
                        logging.error(f"❌ reCAPTCHA検証エラー: {r.text[:200]}")
                        return False

                # 成功レスポンスの処理
                try:
                    response_data = r.json()
                    logging.info(f"📄 reCAPTCHA検証成功: {response_data}")
                    return True
                except:
                    # JSONパースに失敗してもステータスコードが200なら成功とみなす
                    if r.status_code == 200:
                        logging.info(f"✅ reCAPTCHA検証成功")
                        return True
                    else:
                        logging.error(f"❌ レスポンスパースエラー: {r.text[:200]}")
                        return False

            except Exception as e:
                logging.error(f"❌ reCAPTCHA検証中にエラー: {str(e)}")
                # ネットワークエラー等の場合も即座にリトライ
                logging.info(f"🔄 即座にリトライします...")
                continue

    def get_captcha_token_from_bot(self) -> Optional[str]:
        """bot.pyからreCAPTCHAトークンを取得する"""
        try:
            # bot.pyのget_recaptcha_token関数をインポートして実行
            from bot import get_recaptcha_token
            token = get_recaptcha_token()
            logging.info(f"✅ reCAPTCHAトークン取得成功")
            return token
        except Exception as e:
            logging.error(f"❌ reCAPTCHAトークン取得エラー: {str(e)}")
            return None


# ------------------------- CLI ---------------------------
if __name__ == "__main__":
    client = himitsutalkClient()
    tk = client.create_user()
    room = client.create_room(with_user_id=32630775)
    client.send_message(room, "こんにちは！")
