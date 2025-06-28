from dataclasses import dataclass
from typing import List, Dict, Optional
from database import Database
from DM import himitsutalkClient, TokenPair
import logging
import time
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DMManager:
    def __init__(self, db: Database):
        self.db = db
        self.templates = {
            "male": "こんにちは！男性用テンプレートです。",
            "female": "こんにちは！女性用テンプレートです。"
        }

    def set_template(self, target: str, template: str):
        """DMテンプレートを設定"""
        if target not in ["male", "female"]:
            raise ValueError("targetは'male'または'female'である必要があります")
        self.templates[target] = template

    def get_template(self, target: str) -> str:
        """DMテンプレートを取得"""
        return self.templates.get(target, "")

    def send_dm(self, sender_account: Dict, receiver_id: int,
                template_key: str, resend_days: int = 3) -> bool:
        """DMを送信する"""
        try:
            # 送信可能かチェック（指定日数以内に送信済みかどうか）
            if self.db.is_dm_sent_recently(receiver_id, resend_days):
                logger.info(
                    f"送信スキップ: user_id={receiver_id}は{resend_days}日以内に送信済み")
                return False

            # クライアントの初期化
            client = himitsutalkClient()

            # プロキシ設定の取得と設定
            proxy_info = None
            proxy = self.db.get_next_proxy()
            if proxy:
                proxy_info = {
                    "host": proxy["host"],
                    "port": proxy["port"],
                    "username": proxy["username"],
                    "password": proxy["password"]
                }
                client.set_proxy(proxy_info)
                logger.info(f"プロキシを使用: {proxy['host']}:{proxy['port']}")

            client._token_pair = TokenPair(
                sender_account["access_token"],
                sender_account["user_id"]
            )

            # ルーム作成
            room_id = client.create_room(receiver_id)

            # メッセージ送信
            template = self.templates[template_key]
            client.send_message(room_id, template)

            # アカウントの使用状態を更新
            self.db.update_account_usage(sender_account["user_id"])

            # DM送信履歴を記録
            self.db.record_dm_sent(sender_account["user_id"], receiver_id)

            logger.info(
                f"DM送信成功: from={sender_account['user_id']} to={receiver_id}")
            return True

        except Exception as e:
            logger.error(f"DM送信エラー: {str(e)}")
            return False

    def send_multiple_dms(self, sender_accounts: List[Dict],
                          receiver_ids: List[int],
                          dms_per_account: int, resend_days: int = 3) -> Dict:
        """複数のDMを送信する"""
        results = {
            "total_sent": 0,
            "failed": 0,
            "skipped": 0
        }

        # プロキシ設定の取得
        proxy_info = None
        proxy = self.db.get_next_proxy()
        if proxy:
            proxy_info = {
                "host": proxy["host"],
                "port": proxy["port"],
                "username": proxy["username"],
                "password": proxy["password"]
            }
            logger.info(f"プロキシを使用: {proxy['host']}:{proxy['port']}")

        for account in sender_accounts:
            sent_count = 0
            # アカウントの性別に基づいてテンプレートと送信対象を決定
            is_female = account["gender"] == "1"
            template_key = "female" if is_female else "male"

            # 送信対象をシャッフル
            random.shuffle(receiver_ids)

            for receiver_id in receiver_ids:
                if sent_count >= dms_per_account:
                    break

                # クライアントの初期化とプロキシ設定
                client = himitsutalkClient()
                if proxy_info:
                    client.set_proxy(proxy_info)
                client._token_pair = TokenPair(
                    account["access_token"],
                    account["user_id"]
                )

                try:
                    # ルーム作成
                    room_id = client.create_room(receiver_id)

                    # メッセージ送信
                    template = self.templates[template_key]
                    client.send_message(room_id, template)

                    # アカウントの使用状態を更新
                    self.db.update_account_usage(account["user_id"])

                    # DM送信履歴を記録
                    self.db.record_dm_sent(account["user_id"], receiver_id)

                    results["total_sent"] += 1
                    sent_count += 1
                    logger.info(
                        f"DM送信成功: from={account['user_id']} to={receiver_id}")
                except Exception as e:
                    results["failed"] += 1
                    logger.error(f"DM送信エラー: {str(e)}")

            # アカウントを使用済みとしてマーク
            self.db.update_account_usage(account["user_id"])

        return results


# TokenPairクラスはDM.pyからインポートするため削除
