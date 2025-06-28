import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import logging
from DM import TokenPair, himitsutalkClient as DM


class Database:
    def __init__(self, db_path: str = "himitsutalk.db"):
        """データベースの初期化
        Args:
            db_path (str): データベースファイルのパス
        """
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """データベースとテーブルの初期化"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 既存データベースのマイグレーション（email, passwordカラム追加）
            self._migrate_accounts_table(cursor)

            # アカウントテーブルの作成
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    user_id INTEGER PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    age TEXT NOT NULL,
                    nickname TEXT,
                    device_uuid TEXT NOT NULL,
                    email TEXT,
                    password TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    has_sent_dm BOOLEAN DEFAULT 0,
                    last_dm_sent_at TIMESTAMP
                )
            """)

            # DM送信履歴テーブルの作成
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dm_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user_id INTEGER NOT NULL,
                    to_user_id INTEGER NOT NULL,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (from_user_id) REFERENCES accounts (user_id)
                )
            """)

            # DMテンプレートテーブル
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dm_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # プロキシテーブル
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS proxies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    username TEXT,
                    password TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    last_used_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # メールAPI設定テーブル
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mail_api_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_url TEXT NOT NULL,
                    api_key TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # CapMonster API設定テーブル
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS capmonster_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_key TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # デフォルトテンプレートの挿入
            cursor.execute("SELECT COUNT(*) FROM dm_templates")
            if cursor.fetchone()[0] == 0:
                default_templates = [
                    ("男性用", "こんにちは！男性用テンプレートです。"),
                    ("女性用", "こんにちは！女性用テンプレートです。")
                ]
                cursor.executemany(
                    "INSERT INTO dm_templates (name, content) VALUES (?, ?)",
                    default_templates
                )

            # デフォルトメールAPI設定の挿入
            cursor.execute("SELECT COUNT(*) FROM mail_api_settings")
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    "INSERT INTO mail_api_settings (api_url, api_key) VALUES (?, ?)",
                    ("https://api.firstmail.ltd/v1/market/buy/mail?type=3",
                     "2a00e931-ae4f-4fec-a20b-0aa02aa8d007")
                )

            # デフォルトCapMonster API設定の挿入
            cursor.execute("SELECT COUNT(*) FROM capmonster_settings")
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    "INSERT INTO capmonster_settings (api_key) VALUES (?)",
                    ("305e4f56e80739a00ad6491940175bd2",)
                )

            conn.commit()

    def _migrate_accounts_table(self, cursor):
        """accountsテーブルのマイグレーション（email, passwordカラム追加）"""
        try:
            # テーブル情報を取得
            cursor.execute("PRAGMA table_info(accounts)")
            columns = [column[1] for column in cursor.fetchall()]

            # emailカラムが存在しない場合は追加
            if 'email' not in columns:
                cursor.execute("ALTER TABLE accounts ADD COLUMN email TEXT")
                logging.info("accountsテーブルにemailカラムを追加しました")

            # passwordカラムが存在しない場合は追加
            if 'password' not in columns:
                cursor.execute("ALTER TABLE accounts ADD COLUMN password TEXT")
                logging.info("accountsテーブルにpasswordカラムを追加しました")

        except Exception as e:
            logging.error(f"テーブルマイグレーションエラー: {str(e)}")

    def add_account(self, user_id: int, access_token: str, gender: str, age: str, device_uuid: str, nickname: Optional[str] = None) -> bool:
        """新規アカウントの追加
        Args:
            user_id (int): ユーザーID
            access_token (str): アクセストークン
            gender (str): 性別 ("-1": 未設定, "1": 女性)
            age (str): 年齢
            device_uuid (str): デバイスUUID
            nickname (str, optional): ニックネーム
        Returns:
            bool: 追加成功ならTrue
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO accounts (user_id, access_token, gender, age, device_uuid, nickname) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, access_token, gender, age, device_uuid, nickname)
                )
                conn.commit()
                logging.info(f"アカウント追加: user_id={user_id}")
                return True
        except sqlite3.IntegrityError:
            logging.warning(f"アカウント追加失敗（重複）: user_id={user_id}")
            return False
        except Exception as e:
            logging.error(f"アカウント追加エラー: {str(e)}")
            return False

    def get_available_accounts(self, gender: Optional[str] = None, limit: int = 10, exclude_used: bool = False) -> List[Dict]:
        """利用可能なアカウントの取得
        Args:
            gender (str, optional): 性別でフィルタ
            limit (int): 取得上限数
            exclude_used (bool): 使用済みアカウントを除外するかどうか
        Returns:
            List[Dict]: アカウント情報のリスト
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                query = """
                    SELECT * FROM accounts
                    WHERE 1=1
                """
                params = []

                if gender is not None:
                    query += " AND gender = ?"
                    params.append(gender)

                if exclude_used:
                    query += " AND has_sent_dm = 0"

                query += " ORDER BY last_used_at ASC NULLS FIRST LIMIT ?"
                params.append(limit)

                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"アカウント取得エラー: {str(e)}")
            return []

    def get_available_accounts_count(self, gender: Optional[str] = None, exclude_used: bool = False) -> int:
        """利用可能なアカウント数の取得（効率的）
        Args:
            gender (str, optional): 性別でフィルタ
            exclude_used (bool): 使用済みアカウントを除外するかどうか
        Returns:
            int: アカウント数
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                query = """
                    SELECT COUNT(*) FROM accounts
                    WHERE 1=1
                """
                params = []

                if gender is not None:
                    query += " AND gender = ?"
                    params.append(gender)

                if exclude_used:
                    query += " AND has_sent_dm = 0"

                cursor.execute(query, params)
                return cursor.fetchone()[0]
        except Exception as e:
            logging.error(f"アカウント数取得エラー: {str(e)}")
            return 0

    def update_account_usage(self, user_id: int):
        """アカウントの最終使用日時を更新し、送信済みフラグを設定"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE accounts
                    SET last_used_at = CURRENT_TIMESTAMP,
                        has_sent_dm = 1,
                        last_dm_sent_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                    """,
                    (user_id,)
                )
                conn.commit()
        except Exception as e:
            logging.error(f"アカウント更新エラー: {str(e)}")

    def update_account_email_password(self, user_id: int, email: str, password: str) -> bool:
        """アカウントのメールアドレスとパスワードを更新
        Args:
            user_id (int): ユーザーID
            email (str): メールアドレス
            password (str): パスワード
        Returns:
            bool: 更新成功ならTrue
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE accounts
                    SET email = ?, password = ?
                    WHERE user_id = ?
                    """,
                    (email, password, user_id)
                )
                conn.commit()
                logging.info(
                    f"アカウントのメール情報更新: user_id={user_id}, email={email}")
                return True
        except Exception as e:
            logging.error(f"アカウントメール情報更新エラー: {str(e)}")
            return False

    def is_dm_sent_recently(self, to_user_id: int, days: int = 3) -> bool:
        """指定ユーザーへの最近のDM送信有無を確認
        Args:
            to_user_id (int): 送信先ユーザーID
            days (int): 確認する日数
        Returns:
            bool: 期間内に送信済みならTrue
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM dm_history
                    WHERE to_user_id = ?
                    AND sent_at > datetime('now', ?)
                    """,
                    (to_user_id, f'-{days} days')
                )
                count = cursor.fetchone()[0]
                return count > 0
        except Exception as e:
            logging.error(f"DM履歴確認エラー: {str(e)}")
            return False

    def record_dm_sent(self, from_user_id: int, to_user_id: int):
        """DM送信履歴を記録
        Args:
            from_user_id (int): 送信元ユーザーID
            to_user_id (int): 送信先ユーザーID
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO dm_history (from_user_id, to_user_id)
                    VALUES (?, ?)
                    """,
                    (from_user_id, to_user_id)
                )
                conn.commit()
                logging.info(f"DM送信履歴記録: from={from_user_id} to={to_user_id}")
        except Exception as e:
            logging.error(f"DM送信履歴記録エラー: {str(e)}")

    def delete_old_accounts(self, days: int, used_only: bool = False, log_callback=None) -> int:
        """古いアカウントの削除
        Args:
            days (int): 何日前より古いアカウントを削除するか
            used_only (bool): 使用済みアカウントのみ削除するか
            log_callback (callable, optional): GUIにログを表示するためのコールバック関数
        Returns:
            int: 削除したアカウント数
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # デバッグ用：現在のタイムスタンプを確認（日本時間で表示）
                cursor.execute("SELECT datetime('now', 'localtime')")
                current_time_jst = cursor.fetchone()[0]
                cursor.execute(
                    f"SELECT datetime('now', '-{days} days', 'localtime')")
                target_time_jst = cursor.fetchone()[0]
                log_msg = f"削除基準日時の確認（日本時間） - 現在: {current_time_jst}, {days}日前: {target_time_jst}"
                logging.info(log_msg)
                if log_callback:
                    log_callback(log_msg + "\n")

                # 現在のアクティブなアカウント数を確認
                cursor.execute(
                    "SELECT COUNT(*) FROM accounts WHERE is_active = 1")
                before_count = cursor.fetchone()[0]

                # 削除対象となるアカウントを取得
                check_query = f"""
                    SELECT user_id, access_token FROM accounts
                    WHERE is_active = 1
                    AND created_at < datetime('now', '-{days} days')
                """
                if used_only:
                    check_query += " AND has_sent_dm = 1"
                cursor.execute(check_query)
                accounts = cursor.fetchall()
                will_delete = len(accounts)
                log_msg = f"削除対象アカウント数: {will_delete}件"
                logging.info(log_msg)
                if log_callback:
                    log_callback(log_msg + "\n")

                # APIを通じてアカウントを削除
                deleted_user_ids = []
                deletion_stats = {
                    "total_targets": len(accounts),
                    "deleted": 0,
                    "not_ready": 0,  # 3日経過していないアカウント
                    "error": 0       # その他のエラー
                }

                for user_id, access_token in accounts:
                    try:
                        client = DM()
                        client._token_pair = TokenPair(access_token, user_id)
                        result = client.delete_account()
                        if result:
                            deleted_user_ids.append(user_id)
                            # APIでの削除が成功したらDBからも削除
                            cursor.execute(
                                "DELETE FROM accounts WHERE user_id = ?", (user_id,))
                            deletion_stats["deleted"] += 1
                            log_msg = f"✅ アカウントをDBから削除: user_id={user_id}"
                            logging.info(log_msg)
                            if log_callback:
                                log_callback(log_msg + "\n")
                        else:
                            # delete_accountがFalseを返した場合（3日未満のアカウント）
                            deletion_stats["not_ready"] += 1
                            log_msg = f"⚠️ アカウント作成から3日以上経過していないと削除できません (user_id={user_id})"
                            logging.warning(log_msg)
                            if log_callback:
                                log_callback(log_msg + "\n")
                    except Exception as e:
                        deletion_stats["error"] += 1
                        log_msg = f"❌ APIでのアカウント削除エラー (user_id={user_id}): {str(e)}"
                        logging.error(log_msg)
                        if log_callback:
                            log_callback(log_msg + "\n")

                # 削除後のアクティブなアカウント数を確認
                cursor.execute(
                    "SELECT COUNT(*) FROM accounts WHERE is_active = 1")
                after_count = cursor.fetchone()[0]

                # 実際に削除されたアカウント数を計算
                deleted = before_count - after_count

                conn.commit()
                summary = (
                    f"\n📊 削除結果サマリー:\n"
                    f"- 削除対象: {deletion_stats['total_targets']}件\n"
                    f"- 削除成功: {deletion_stats['deleted']}件\n"
                    f"- 削除待機（3日未満）: {deletion_stats['not_ready']}件\n"
                    f"- エラー: {deletion_stats['error']}件\n"
                    f"- 現在のアカウント数: {after_count}件"
                )
                logging.info(summary)
                if log_callback:
                    log_callback(summary + "\n")
                return deleted

        except Exception as e:
            log_msg = f"アカウント削除エラー: {str(e)}"
            logging.error(log_msg)
            if log_callback:
                log_callback("❌ " + log_msg + "\n")
            return 0

    def get_dm_stats(self, days: int = 7) -> Dict:
        """DM送信の統計情報を取得
        Args:
            days (int): 集計する日数
        Returns:
            Dict: 統計情報
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # dm_historyテーブルから送信成功数を取得
                cursor.execute(
                    """
                    SELECT COUNT(*) as total
                    FROM dm_history 
                    WHERE sent_at > datetime('now', ?)
                    """,
                    (f'-{days} days',)
                )
                total_sent = cursor.fetchone()[0] or 0

                return {
                    "total": total_sent,
                    "success": total_sent,  # dm_historyに記録されているのは成功したもののみ
                    "failed": 0  # 失敗数は別途管理が必要な場合は追加実装
                }
        except Exception as e:
            logging.error(f"統計情報取得エラー: {str(e)}")
            return {"total": 0, "success": 0, "failed": 0}

    def get_dm_templates(self) -> Dict[str, str]:
        """DMテンプレート一覧を取得
        Returns:
            Dict[str, str]: テンプレート名をキー、内容を値とする辞書
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name, content FROM dm_templates")
                return dict(cursor.fetchall())
        except Exception as e:
            logging.error(f"テンプレート取得エラー: {str(e)}")
            return {}

    def update_dm_template(self, name: str, content: str) -> bool:
        """DMテンプレートを更新
        Args:
            name (str): テンプレート名
            content (str): テンプレート内容
        Returns:
            bool: 更新成功ならTrue
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE dm_templates 
                    SET content = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE name = ?
                    """,
                    (content, name)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"テンプレート更新エラー: {str(e)}")
            return False

    def add_proxy(self, host: str, port: int, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        """プロキシを追加
        Args:
            host (str): ホスト名
            port (int): ポート番号
            username (str, optional): ユーザー名
            password (str, optional): パスワード
        Returns:
            bool: 追加成功ならTrue
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO proxies (host, port, username, password) VALUES (?, ?, ?, ?)",
                    (host, port, username, password)
                )
                conn.commit()
                logging.info(f"プロキシ追加: {host}:{port}")
                return True
        except Exception as e:
            logging.error(f"プロキシ追加エラー: {str(e)}")
            return False

    def get_proxies(self, active_only: bool = True) -> List[Dict]:
        """プロキシ一覧を取得
        Args:
            active_only (bool): アクティブなプロキシのみ取得
        Returns:
            List[Dict]: プロキシ情報のリスト
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                query = "SELECT * FROM proxies"
                if active_only:
                    query += " WHERE is_active = 1"
                cursor.execute(query)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"プロキシ取得エラー: {str(e)}")
            return []

    def update_proxy_status(self, proxy_id: int, is_active: bool) -> bool:
        """プロキシの有効/無効を切り替え"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE proxies SET is_active = ? WHERE id = ?",
                    (is_active, proxy_id)
                )
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"プロキシステータス更新エラー: {str(e)}")
            return False

    def delete_proxy(self, proxy_id: int) -> bool:
        """プロキシを削除"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM proxies WHERE id = ?", (proxy_id,))
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"プロキシ削除エラー: {str(e)}")
            return False

    def get_next_proxy(self) -> Optional[Dict]:
        """次に使用するプロキシを取得（ラウンドロビン方式）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT * FROM proxies 
                    WHERE is_active = 1 
                    ORDER BY last_used_at ASC NULLS FIRST 
                    LIMIT 1
                    """
                )
                row = cursor.fetchone()
                if row:
                    proxy = dict(row)
                    cursor.execute(
                        "UPDATE proxies SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (proxy["id"],)
                    )
                    conn.commit()
                    return proxy
                return None
        except Exception as e:
            logging.error(f"次のプロキシ取得エラー: {str(e)}")
            return None

    def delete_all_proxies(self) -> bool:
        """全てのプロキシを削除"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM proxies")
                conn.commit()
                logging.info("全てのプロキシを削除しました")
                return True
        except Exception as e:
            logging.error(f"プロキシ一括削除エラー: {str(e)}")
            return False

    def delete_account(self, user_id: str) -> bool:
        """アカウントを削除（非アクティブ化）
        Args:
            user_id (str): 削除するユーザーID
        Returns:
            bool: 削除に成功したかどうか
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE accounts SET is_active = 0 WHERE user_id = ?",
                    (user_id,)
                )
                conn.commit()
                logging.info(f"アカウントを非アクティブ化: user_id={user_id}")
                return True
        except Exception as e:
            logging.error(f"アカウント削除エラー: {str(e)}")
            return False

    def delete_account_by_user_id(self, user_id: int) -> bool:
        """user_idでアカウントを完全削除
        Args:
            user_id (int): 削除するユーザーID
        Returns:
            bool: 削除に成功したかどうか
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 関連するDM履歴も削除
                cursor.execute(
                    "DELETE FROM dm_history WHERE from_user_id = ? OR to_user_id = ?",
                    (user_id, user_id)
                )

                # アカウントを削除
                cursor.execute(
                    "DELETE FROM accounts WHERE user_id = ?",
                    (user_id,)
                )

                conn.commit()
                logging.info(f"アカウントを完全削除: user_id={user_id}")
                return True
        except Exception as e:
            logging.error(f"アカウント削除エラー: {str(e)}")
            return False

    def add_mail_api_setting(self, api_url: str, api_key: str) -> bool:
        """メールAPI設定を追加
        Args:
            api_url (str): API URL
            api_key (str): APIキー
        Returns:
            bool: 追加成功ならTrue
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 既存の設定を無効化
                cursor.execute("UPDATE mail_api_settings SET is_active = 0")
                # 新しい設定を追加
                cursor.execute(
                    "INSERT INTO mail_api_settings (api_url, api_key) VALUES (?, ?)",
                    (api_url, api_key)
                )
                conn.commit()
                logging.info("メールAPI設定を追加しました")
                return True
        except Exception as e:
            logging.error(f"メールAPI設定追加エラー: {str(e)}")
            return False

    def get_mail_api_setting(self) -> Optional[Dict]:
        """アクティブなメールAPI設定を取得
        Returns:
            Dict: メールAPI設定情報、なければNone
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM mail_api_settings WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logging.error(f"メールAPI設定取得エラー: {str(e)}")
            return None

    def update_mail_api_setting(self, api_key: str) -> bool:
        """メールAPI設定を更新
        Args:
            api_key (str): APIキー
        Returns:
            bool: 更新成功ならTrue
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 既存の設定を無効化
                cursor.execute("UPDATE mail_api_settings SET is_active = 0")
                # 新しい設定を追加（URLは固定）
                cursor.execute(
                    "INSERT INTO mail_api_settings (api_url, api_key) VALUES (?, ?)",
                    ("https://api.firstmail.ltd/v1/market/buy/mail?type=3", api_key)
                )
                conn.commit()
                logging.info("メールAPI設定を更新しました")
                return True
        except Exception as e:
            logging.error(f"メールAPI設定更新エラー: {str(e)}")
            return False

    def delete_all_mail_api_settings(self) -> bool:
        """全てのメールAPI設定を削除
        Returns:
            bool: 削除成功ならTrue
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE mail_api_settings SET is_active = 0")
                conn.commit()
                logging.info("全てのメールAPI設定を無効化しました")
                return True
        except Exception as e:
            logging.error(f"メールAPI設定削除エラー: {str(e)}")
            return False

    def get_capmonster_setting(self) -> Optional[Dict]:
        """CapMonster API設定を取得
        Returns:
            Dict: 設定情報（api_key）、設定がない場合はNone
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM capmonster_settings WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
                )
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logging.error(f"CapMonster設定取得エラー: {str(e)}")
            return None

    def update_capmonster_setting(self, api_key: str) -> bool:
        """CapMonster API設定を更新（存在しない場合は作成）
        Args:
            api_key (str): APIキー
        Returns:
            bool: 更新成功ならTrue
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 既存の設定を無効化
                cursor.execute("UPDATE capmonster_settings SET is_active = 0")

                # 新しい設定を追加
                cursor.execute(
                    "INSERT INTO capmonster_settings (api_key, is_active) VALUES (?, 1)",
                    (api_key,)
                )

                conn.commit()
                logging.info(f"CapMonster API設定を更新しました")
                return True
        except Exception as e:
            logging.error(f"CapMonster設定更新エラー: {str(e)}")
            return False
