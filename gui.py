import flet as ft
import random
import unicodedata
import threading
from DM import TokenPair, himitsutalkClient as DM, generate_ios_user_agent
from database import Database
import logging
import time
import uuid
from typing import Optional, List, Dict
from faker import Faker
from faker.providers import user_agent
# Fakerの初期化
fake = Faker()
fake.add_provider(user_agent)

dm_templates = {
    "男性用": "こんにちは！男性用テンプレートです。",
    "女性用": "こんにちは！女性用テンプレートです。"
}

# himitsutalkClientとDatabaseのインスタンスを保持
client: Optional[DM] = None
db: Optional[Database] = None
# プロキシ設定の状態を保持
proxy_settings = {
    "use_proxy": False
}

# 画像選択の状態管理用の変数を追加
current_gender_selection = None


def get_timestamp() -> int:
    return int(time.time())


def initialize_services():
    global client, db
    if client is None:
        client = DM()
    if db is None:
        db = Database()


def to_halfwidth(s):
    return unicodedata.normalize("NFKC", s)

# ================== アカウント作成タブ ==================


def account_tab_content(page):
    initialize_services()

    error_msg = ft.Text("", color="red", size=13)
    age_method = ft.RadioGroup(
        content=ft.Row([
            ft.Radio(label="固定", value="fixed"),
            ft.Radio(label="ランダム", value="random"),
        ]),
        value="fixed"
    )
    age_fixed = ft.TextField(
        label="固定年齢（例:18）", value="18", width=120, disabled=False)
    age_min = ft.TextField(label="下限（例:18）", value="18",
                           width=80, disabled=True)
    age_max = ft.TextField(label="上限（例:22）", value="22",
                           width=80, disabled=True)

    def on_age_method_change(e):
        if age_method.value == "fixed":
            age_fixed.disabled = False
            age_min.disabled = True
            age_max.disabled = True
        else:
            age_fixed.disabled = True
            age_min.disabled = False
            age_max.disabled = False
        error_msg.value = ""
        page.update()
    age_method.on_change = on_age_method_change

    gender = ft.RadioGroup(
        content=ft.Row([
            ft.Radio(label="未設定", value="-1"),
            ft.Radio(label="女性", value="1")
        ]),
        value="-1"
    )
    count = ft.TextField(label="作成アカウント数", value="10", width=100)

    # メール登録オプションを追加
    email_register_checkbox = ft.Checkbox(
        label="アカウント作成後にメールアドレスを登録する",
        value=False
    )

    run_btn = ft.ElevatedButton("アカウント作成開始", width=200)
    log_box = ft.TextField(label="ログ", multiline=True,
                           min_lines=3, max_lines=8, read_only=True, width=420)

    def is_valid_age(s):
        s = to_halfwidth(s)
        return s.isdigit() and 10 <= int(s) <= 99

    def create_accounts_thread():
        try:
            total = int(to_halfwidth(count.value))
            created = 0
            email_registered = 0
            log_box.value = "[アカウント作成開始]\n"

            # メール登録オプションの確認
            register_email = email_register_checkbox.value
            if register_email:
                log_box.value += "メールアドレス登録: 有効\n"
            else:
                log_box.value += "メールアドレス登録: 無効\n"

            page.update()

            # プロキシ設定の取得
            proxy_info = None
            if proxy_settings["use_proxy"]:
                proxy = db.get_next_proxy()
                if proxy:
                    proxy_info = {
                        "host": proxy["host"],
                        "port": proxy["port"],
                        "username": proxy["username"],
                        "password": proxy["password"]
                    }
                    log_box.value += f"プロキシを使用: {proxy['host']}:{proxy['port']}\n"
                    page.update()

            for _ in range(total):
                try:
                    # プロキシ設定
                    client.set_proxy(proxy_info)

                    # ランダムなユーザーエージェントとUUIDを生成
                    device_uuid = str(uuid.uuid4()).upper()
                    user_agent = generate_ios_user_agent()
                    client.set_user_agent(user_agent, device_uuid)

                    # 年齢の決定
                    if age_method.value == "fixed":
                        age = to_halfwidth(age_fixed.value)
                    else:
                        min_val = int(to_halfwidth(age_min.value))
                        max_val = int(to_halfwidth(age_max.value))
                        if min_val > max_val:
                            min_val, max_val = max_val, min_val
                        age = str(random.randint(min_val, max_val))

                    # アカウント作成
                    token_pair = client.create_user(
                        age=age, gender=gender.value)

                    if db.add_account(token_pair.user_id, token_pair.access_token, gender.value, age, device_uuid):
                        created += 1
                        log_box.value += f"✅ アカウント作成成功 ({created}/{total}) ID: {token_pair.user_id}\n"

                        # メール登録処理
                        if register_email:
                            try:
                                # メールアドレスを自動取得・登録
                                if client.register_email_for_account():
                                    email_registered += 1
                                    log_box.value += f"📧 メール登録成功 ID: {token_pair.user_id}\n"
                                else:
                                    log_box.value += f"⚠️ メール登録失敗 ID: {token_pair.user_id}\n"
                            except Exception as email_error:
                                log_box.value += f"❌ メール登録エラー ID: {token_pair.user_id} - {str(email_error)}\n"

                    else:
                        log_box.value += f"⚠️ アカウント作成は成功しましたが、DBへの保存に失敗しました ID: {token_pair.user_id}\n"

                    page.update()

                    # API制限を避けるため少し待機
                    if register_email:
                        time.sleep(2)

                except Exception as e:
                    if "403" in str(e):
                        log_box.value += f"❌ IP BANされました。リトライします。\n"
                        # IP BANの場合は少し長めに待機してIPの切り替えを待つ
                    else:
                        log_box.value += f"❌ アカウント作成失敗: {str(e)}\n"
                    page.update()

            # 完了メッセージ
            completion_msg = f"\n作成完了！ 成功: {created}/{total}\n"
            if register_email:
                completion_msg += f"メール登録成功: {email_registered}/{created}\n"
            log_box.value += completion_msg

            run_btn.disabled = False
            page.update()

        except Exception as e:
            log_box.value += f"\n❌ エラーが発生しました: {str(e)}\n"
            run_btn.disabled = False
            page.update()

    def on_account_run(e):
        error_msg.value = ""
        # 入力値チェック
        if age_method.value == "fixed":
            age_val = to_halfwidth(age_fixed.value)
            if not is_valid_age(age_val):
                error_msg.value = "固定年齢は半角数字（10〜99）で入力してください。"
                page.update()
                return
        else:
            min_val = to_halfwidth(age_min.value)
            max_val = to_halfwidth(age_max.value)
            if not (is_valid_age(min_val) and is_valid_age(max_val)):
                error_msg.value = "年齢下限・上限は半角数字（10〜99）で入力してください。"
                page.update()
                return

        count_val = to_halfwidth(count.value)
        if not count_val.isdigit() or int(count_val) <= 0:
            error_msg.value = "作成アカウント数は1以上の半角数字で入力してください。"
            page.update()
            return

        # 実行ボタンを無効化
        run_btn.disabled = True
        page.update()

        # 別スレッドでアカウント作成を実行
        thread = threading.Thread(target=create_accounts_thread)
        thread.daemon = True
        thread.start()

    run_btn.on_click = on_account_run

    return ft.Column([
        ft.Text("アカウント作成設定", size=20, weight="bold"),
        ft.Text("年齢の指定方法："),
        age_method,
        ft.Row([age_fixed, age_min, age_max]),
        gender,
        ft.Row([ft.Text("アカウント数:"), count]),
        email_register_checkbox,
        run_btn,
        error_msg,
        log_box
    ])

# ================== DM一斉送信タブ ==================


def dm_tab_content(page):
    initialize_services()
    global current_gender_selection

    # 処理の状態管理
    is_running = False

    # ファイル選択の状態管理
    selected_files = {
        "unset": None,
        "female": None
    }

    def pick_files_result(e: ft.FilePickerResultEvent):
        if e.files:
            # グローバル変数から性別を取得
            gender = current_gender_selection
            if gender:
                selected_files[gender] = e.files[0].path
                # ログに選択したファイルを表示
                log_box.value = f"{gender}用の画像を選択: {e.files[0].path}\n" + \
                    log_box.value
                page.update()

    # FilePickerの設定
    pick_files_dialog = ft.FilePicker(on_result=pick_files_result)
    page.overlay.append(pick_files_dialog)

    def pick_unset_image(_):
        global current_gender_selection
        current_gender_selection = "unset"
        pick_files_dialog.pick_files(
            allow_multiple=False,
            file_type=ft.FilePickerFileType.IMAGE,
            allowed_extensions=["jpg", "jpeg", "png"],
            dialog_title="未設定用画像を選択"
        )

    def pick_female_image(_):
        global current_gender_selection
        current_gender_selection = "female"
        pick_files_dialog.pick_files(
            allow_multiple=False,
            file_type=ft.FilePickerFileType.IMAGE,
            allowed_extensions=["jpg", "jpeg", "png"],
            dialog_title="女性用画像を選択"
        )

    # 画像選択ボタン
    unset_image_btn = ft.ElevatedButton(
        "未設定用画像を選択",
        icon=ft.Icons.FILE_OPEN,
        on_click=pick_unset_image,
        disabled=True
    )

    female_image_btn = ft.ElevatedButton(
        "女性用画像を選択",
        icon=ft.Icons.FILE_OPEN,
        on_click=pick_female_image,
        disabled=True
    )

    send_count = ft.TextField(label="1アカウントあたりのDM数", value="5", width=180)
    account_total = ft.TextField(
        label="トータルで使用するアカウント数", value="10", width=220)
    exclude_used_chk = ft.Checkbox(
        label="使用済みアカウントを除外する", value=False
    )
    resend_days = ft.TextField(label="再送信解禁日数（デフォルト3日）", value="3", width=180)

    # ニックネーム入力フィールド
    unset_nickname = ft.TextField(
        label="未設定用", width=150, value="", disabled=True)
    female_nickname = ft.TextField(
        label="女性用", width=150, value="", disabled=True)

    # 自己紹介入力フィールド
    unset_biography = ft.TextField(
        label="未設定用", width=150, value="", disabled=True, multiline=True, min_lines=2, max_lines=3, max_length=50)
    female_biography = ft.TextField(
        label="女性用", width=150, value="", disabled=True, multiline=True, min_lines=2, max_lines=3, max_length=50)

    def on_profile_settings_change(e):
        # チェックボックスの状態に応じて各コントロールの有効/無効を切り替え
        is_enabled = e.control.value
        unset_image_btn.disabled = not is_enabled
        female_image_btn.disabled = not is_enabled
        unset_nickname.disabled = not is_enabled
        female_nickname.disabled = not is_enabled
        unset_biography.disabled = not is_enabled
        female_biography.disabled = not is_enabled
        page.update()

    # プロフィール設定オプション
    profile_settings = ft.Container(
        content=ft.Column([
            ft.Text("プロフィール設定", size=15, weight="bold"),
            ft.Checkbox(
                label="DM送信前にプロフィールを設定する",
                value=False,
                on_change=on_profile_settings_change
            ),
            ft.Row([
                ft.Text("画像:"),
                unset_image_btn,
                female_image_btn,
            ]),
            ft.Row([
                ft.Text("ニックネーム:"),
                unset_nickname,
                female_nickname,
            ]),
            ft.Row([
                ft.Text("自己紹介:"),
                unset_biography,
                female_biography,
            ]),
        ]),
        padding=10,
        border=ft.border.all(1, ft.Colors.GREY_400),
        border_radius=10,
        margin=ft.margin.only(top=10, bottom=10),
    )

    run_btn = ft.ElevatedButton("DM一斉送信開始", width=200)
    stop_btn = ft.ElevatedButton("停止", width=100, disabled=True, color="red")
    log_box = ft.TextField(label="ログ", multiline=True,
                           min_lines=4, max_lines=10, read_only=True, width=420)
    error_msg = ft.Text("", color="red", size=13)
    rule_text = ("【送信対象の割り振りルール】\n"
                 "・女性設定アカウント → 男性アカウントへ送信（男性用テンプレ使用）\n"
                 "・未設定アカウント → 女性アカウント／未設定アカウントへ送信（女性用テンプレ使用）\n"
                 "（※未設定は女性として扱う）\n"
                 "・送信済みユーザーは重複送信しません（最終送信から指定日数経過で再送信）")

    def is_valid_num(s):
        s = unicodedata.normalize("NFKC", s)
        return s.isdigit() and int(s) > 0

    def send_dm_thread(profile_data=None):
        nonlocal is_running
        is_running = True
        run_btn.disabled = True
        stop_btn.disabled = False
        page.update()

        try:
            # 送信対象アカウント数の取得
            total_accounts = int(to_halfwidth(account_total.value))
            if total_accounts <= 0:
                log_box.value = "❌ 送信数は1以上を指定してください。\n"
                run_btn.disabled = False
                page.update()
                return

            # まず在庫数をチェック（効率的にCOUNTクエリで取得）
            actual_stock = db.get_available_accounts_count(
                exclude_used=exclude_used_chk.value)

            if actual_stock == 0:
                log_box.value += "❌ 利用可能なアカウントがありません。\n"
                page.update()
                return

            # 実際の在庫数をログ出力
            log_box.value += f"📊 実際の在庫数: {actual_stock}個\n"

            # 在庫数チェック - 不足している場合はエラーで停止
            if actual_stock < total_accounts:
                log_box.value += f"❌ エラー: 設定されたアカウント数({total_accounts}個)に対して在庫が不足しています！\n"
                log_box.value += f"🛑 処理を停止します。十分なアカウントを作成してから再実行してください。\n"
                # ボタンの状態を戻す
                run_btn.disabled = False
                stop_btn.disabled = True
                is_running = False
                page.update()
                return

            # 必要な分だけアカウントを取得（在庫数チェック済みなので安全）
            available_accounts = db.get_available_accounts(
                limit=total_accounts,  # 必要な分だけ取得
                exclude_used=exclude_used_chk.value)

            # トータルで使用するアカウント数に制限
            if len(available_accounts) > total_accounts:
                available_accounts = available_accounts[:total_accounts]
                log_box.value += f"🔧 使用アカウントを{total_accounts}個に制限しました\n"

            page.update()

            total_dms = total_accounts * int(to_halfwidth(send_count.value))
            sent_dms = 0
            log_box.value = "[DM送信開始]\n"
            log_box.value += f"📋 設定確認:\n"
            log_box.value += f"  ・1アカウントあたりのDM数: {send_count.value}件\n"
            log_box.value += f"  ・使用するアカウント数: {total_accounts}個\n"
            log_box.value += f"  ・総送信予定DM数: {total_dms}件\n"
            log_box.value += f"  ・使用済みアカウント除外: {'有効' if exclude_used_chk.value else '無効'}\n"
            log_box.value += f"  ・再送信解禁日数: {resend_days.value}日\n\n"
            page.update()

            # プロキシ設定の取得
            proxy_info = None
            if proxy_settings["use_proxy"]:
                proxy = db.get_next_proxy()
                if proxy:
                    proxy_info = {
                        "host": proxy["host"],
                        "port": proxy["port"],
                        "username": proxy["username"],
                        "password": proxy["password"]
                    }
                    log_box.value += f"プロキシを使用: {proxy['host']}:{proxy['port']}\n"
                    page.update()

            # 🔥 プロフィール設定の一括適用（DM送信前）
            if profile_data:
                log_box.value += f"\n📝 全アカウントのプロフィール更新を開始...\n"

                for i, account in enumerate(available_accounts):
                    # トータルアカウント数でストップ
                    if i >= total_accounts:
                        break

                    try:
                        # アカウントのトークン情報をclientに設定
                        client._token_pair = TokenPair(
                            account["access_token"], account["user_id"])

                        # プロキシ設定
                        client.set_proxy(proxy_info)

                        # BAN状態確認
                        if client.is_banned():
                            # BANされている場合はDBから削除
                            if db.delete_account_by_user_id(account["user_id"]):
                                log_box.value = f"⚠️ BANアカウントを削除: user_id={account['user_id']}\n" + log_box.value
                            else:
                                log_box.value = f"❌ BANアカウントの削除に失敗: user_id={account['user_id']}\n" + \
                                    log_box.value
                            page.update()
                            continue

                        # アカウントの性別に応じてプロフィール設定を選択
                        if account["gender"] == "-1":  # 未設定（男性として扱う）
                            profile_config = profile_data["unset"]
                            gender_for_api = "-1"
                            gender_name = "未設定用"
                        else:  # 女性
                            profile_config = profile_data["female"]
                            gender_for_api = "1"
                            gender_name = "女性用"

                        # プロフィール更新を実行（再試行ループ）
                        profile_update_success = False
                        max_retries = 2
                        retry_count = 0

                        while not profile_update_success and retry_count < max_retries:
                            try:
                                retry_count += 1

                                # プロフィール更新を実行
                                # log_box.value = f"🔄 プロフィール更新中... ID: {account['user_id']} ({gender_name})\n" + log_box.value
                                page.update()

                                if client.update_profile(
                                    nickname=profile_config["nickname"],
                                    gender=gender_for_api,
                                    age=account.get("age", "20"),
                                    image_path=profile_config["image"],
                                    biography=profile_config["biography"]
                                ):
                                    # 成功処理
                                    log_box.value = f"✅ プロフィール更新成功 ID: {account['user_id']} ニックネーム: {profile_config['nickname']} ({gender_name})\n" + \
                                        log_box.value
                                    profile_update_success = True
                                else:
                                    log_box.value = f"⚠️ プロフィール更新失敗 ID: {account['user_id']} ({gender_name})\n" + \
                                        log_box.value
                                page.update()

                            except Exception as profile_error:
                                profile_error_str = str(profile_error)

                                # Captcha requiredエラーの場合はreCAPTCHA検証を実行
                                if "Captcha required" in profile_error_str or "error_code\":-29" in profile_error_str:
                                    log_box.value = f"🔐 Captchaが必要です（プロフィール更新時）。reCAPTCHA検証を開始します... (ID: {account['user_id']})\n" + \
                                        log_box.value
                                    page.update()

                                    # reCAPTCHA検証を実行
                                    try:
                                        # reCAPTCHAトークンを取得
                                        token = client.get_captcha_token_from_bot()
                                        if token:
                                            # トークンを検証（IP BANの場合は自動リトライ）
                                            if client.verify_captcha(token):
                                                log_box.value = f"✅ reCAPTCHA検証成功！プロフィール更新を再試行します (ID: {account['user_id']})\n" + \
                                                    log_box.value
                                                page.update()
                                                # 検証成功後、ループを継続して再試行
                                                continue
                                            else:
                                                log_box.value = f"❌ reCAPTCHA検証失敗 (ID: {account['user_id']})\n" + \
                                                    log_box.value
                                                page.update()
                                                break
                                        else:
                                            log_box.value = f"❌ reCAPTCHAトークンの取得に失敗 (ID: {account['user_id']})\n" + \
                                                log_box.value
                                            page.update()
                                            break
                                    except Exception as captcha_error:
                                        log_box.value = f"❌ reCAPTCHA検証エラー: {str(captcha_error)} (ID: {account['user_id']})\n" + \
                                            log_box.value
                                        page.update()
                                        break
                                else:
                                    log_box.value = f"❌ プロフィール更新エラー ID: {account['user_id']} - {str(profile_error)}\n" + \
                                        log_box.value
                                    page.update()
                                    break

                        # 最大リトライ回数に達した場合
                        if not profile_update_success and retry_count >= max_retries:
                            log_box.value = f"⚠️ プロフィール更新の最大リトライ回数に達しました ID: {account['user_id']}\n" + \
                                log_box.value
                            page.update()

                    except Exception as profile_error:
                        log_box.value = f"❌ プロフィール更新エラー ID: {account['user_id']} - {str(profile_error)}\n" + \
                            log_box.value
                        page.update()

                log_box.value += f"🚀 DM送信処理を開始します...\n\n"
                page.update()

            # 送信対象ユーザーをリアルタイムで監視・取得
            users = []
            page_num = 0
            last_check_time = get_timestamp()
            check_interval = 300  # 5分ごとにチェック(300)

            def update_user_list_if_needed():
                """必要に応じてユーザーリストを更新する"""
                nonlocal page_num, last_check_time
                current_time = get_timestamp()

                # 5分経過したかチェック
                if current_time - last_check_time >= check_interval:
                    # 残りのDM送信数を計算
                    remaining_dms = total_dms - sent_dms

                    # 現在のユーザーリストをクリア
                    users.clear()
                    log_box.value = f"⏰ 5分経過したので一度ターゲットリストをクリアします\n" + log_box.value
                    page.update()

                    # 必要なユーザー数に達するまで新しいユーザーを取得
                    while len(users) < remaining_dms and is_running:
                        try:
                            # プロキシが設定されていることを確認
                            if not hasattr(client, '_proxy') or client._proxy != proxy_info:
                                client.set_proxy(proxy_info)
                            new_users = client.get_new_users(page=page_num)
                            if new_users:
                                # 5分以内にログインしたユーザーのみをフィルタリング
                                recent_users = []
                                for user in new_users:
                                    last_login = user.get(
                                        "last_loggedin_at", 0)
                                    if current_time - last_login <= check_interval:
                                        # DBで送信履歴をチェック
                                        if not db.is_dm_sent_recently(user["id"], int(to_halfwidth(resend_days.value))):
                                            recent_users.append(user)

                                # ユーザーリストに追加
                                users.extend(recent_users)

                                # 検索状況をログに表示
                                log_box.value = f"✅ 新着ユーザー追加: {len(recent_users)}件 (現在: {len(users)}件, 残りDM: {remaining_dms}件)\n" + log_box.value
                                page.update()

                            # 次のページへ
                            page_num = (page_num + 1) % 10  # 0-9でループ

                        except Exception as e:
                            if "403" in str(e):
                                log_box.value = f"❌ IP BANされました。リトライします...\n" + log_box.value
                                page.update()
                                time.sleep(3)  # 30秒待機してリトライ
                            else:
                                log_box.value = f"❌ ユーザー取得失敗: {str(e)}\n" + \
                                    log_box.value
                                page.update()
                                time.sleep(3)  # エラー時は1分待機

                    last_check_time = current_time

                    # ユーザーリストの更新が完了したことを通知
                    log_box.value = f"🔄 ユーザーリストの更新が完了しました\n" + log_box.value
                    page.update()

            # 最初に必要な数のユーザーを取得
            log_box.value += f"🔍 初回ユーザー取得を開始します...\n"
            page.update()

            # get_new_users呼び出し前にプロキシを設定
            client.set_proxy(proxy_info)

            while is_running and len(users) < total_dms:
                try:
                    new_users = client.get_new_users(page=page_num)
                    if new_users:
                        # 5分以内にログインしたユーザーのみをフィルタリング
                        current_time = get_timestamp()
                        recent_users = []
                        for user in new_users:
                            last_login = user.get("last_loggedin_at", 0)
                            if current_time - last_login <= check_interval:
                                # DBで送信履歴をチェック
                                if not db.is_dm_sent_recently(user["id"], int(to_halfwidth(resend_days.value))):
                                    recent_users.append(user)

                        # ユーザーリストに追加
                        users.extend(recent_users)

                        # 検索状況をログに表示
                        log_box.value = f"検索回数: {page_num + 1}回目\n" + \
                            f"現在の対象ユーザー数: {len(users)}人\n" + \
                            f"最後の検索ページ: {page_num}\n" + \
                            "...\n" + \
                            log_box.value[log_box.value.find("\n", 100):]
                        page.update()

                    # 次のページへ
                    page_num = (page_num + 1) % 10  # 0-9でループ

                except Exception as e:
                    if "403" in str(e):
                        log_box.value = f"❌ IP BANされました。リトライします...\n" + log_box.value
                        page.update()
                        time.sleep(3)  # 3秒待機してリトライ
                    else:
                        log_box.value = f"❌ ユーザー取得失敗: {str(e)}\n" + \
                            log_box.value
                        page.update()
                        time.sleep(3)  # 3秒待機してリトライ

            log_box.value += f"✅ 初回ユーザー取得完了: {len(users)}人のターゲットを確保しました\n"
            page.update()

            # アカウントごとのDM送信処理
            processed_accounts = 0
            for account in available_accounts:
                # トータルアカウント数でストップ
                if processed_accounts >= total_accounts:
                    break

                if not is_running:
                    log_box.value += "\n処理を停止しました。\n"
                    break

                try:
                    # アカウントの設定
                    client._token_pair = TokenPair(
                        account["access_token"], account["user_id"])

                    # プロキシ設定
                    client.set_proxy(proxy_info)

                    if client.is_banned():
                        # BANされている場合はDBから削除
                        if db.delete_account_by_user_id(account["user_id"]):
                            log_box.value = f"⚠️ BANアカウントを削除: user_id={account['user_id']}\n" + log_box.value
                        else:
                            log_box.value = f"❌ BANアカウントの削除に失敗: user_id={account['user_id']}\n" + log_box.value
                        page.update()
                        continue
                    else:
                        log_box.value = f"✅ BAN状態チェック完了（アクティブ）: user_id={account['user_id']}\n" + log_box.value
                        page.update()

                    # このアカウントの送信対象をフィルタリング
                    account_users = client.filter_target_users(
                        users.copy(), gender=account["gender"])

                    # 女性アカウントの場合、男性アカウントがない場合はスキップ
                    if account["gender"] == "1" and len(account_users) == 0:
                        log_box.value = f"⚠️ スキップします: 女性アカウント(ID: {account['user_id']})の送信対象となる男性アカウントが見つかりません\n" + \
                            log_box.value
                        page.update()
                        processed_accounts += 1  # スキップしてもカウント
                        continue

                    # 未設定アカウント（男性として扱う）の場合、女性/未設定アカウントがない場合はスキップ
                    if account["gender"] == "-1" and len(account_users) == 0:
                        log_box.value = f"⚠️ スキップします: 未設定アカウント(ID: {account['user_id']})の送信対象となる女性/未設定アカウントが見つかりません\n" + \
                            log_box.value
                        page.update()
                        processed_accounts += 1  # スキップしてもカウント
                        continue

                    account_sent_count = 0

                    # DM送信処理
                    while account_users and account_sent_count < int(to_halfwidth(send_count.value)) and is_running:
                        # 5分ごとのユーザーリスト更新チェック（各DM送信前）
                        update_user_list_if_needed()

                        # ユーザーリストが空の場合、更新を待つ
                        if not users:
                            log_box.value = f"⏳ ユーザーリストの更新を待機中...\n" + log_box.value
                            page.update()
                            time.sleep(10)  # 10秒待機
                            continue

                        user = account_users.pop(0)
                        user_id = user["id"]

                        try:
                            # DM送信
                            template_type = "男性用" if account["gender"] == "-1" else "女性用"
                            template = dm_templates[template_type]

                            # ルーム作成
                            try:
                                room_id = client.create_room(user_id)
                            except Exception as room_error:
                                room_error_str = str(room_error)

                                # Captcha requiredエラーの場合はreCAPTCHA検証を実行
                                if "Captcha required" in room_error_str or "error_code\":-29" in room_error_str:
                                    log_box.value = f"🔐 Captchaが必要です。reCAPTCHA検証を開始します... (ID: {account['user_id']})\n" + \
                                        log_box.value
                                    page.update()

                                    # reCAPTCHA検証を実行
                                    try:
                                        # reCAPTCHAトークンを取得
                                        token = client.get_captcha_token_from_bot()
                                        if token:
                                            # トークンを検証（IP BANの場合は自動リトライ）
                                            if client.verify_captcha(token):
                                                log_box.value = f"✅ reCAPTCHA検証成功！処理を続行します (ID: {account['user_id']})\n" + \
                                                    log_box.value
                                                page.update()
                                                # 検証成功後、再度ルーム作成を試みる
                                                continue
                                            else:
                                                log_box.value = f"❌ reCAPTCHA検証失敗 (ID: {account['user_id']})\n" + \
                                                    log_box.value
                                                page.update()
                                                break
                                        else:
                                            log_box.value = f"❌ reCAPTCHAトークンの取得に失敗 (ID: {account['user_id']})\n" + \
                                                log_box.value
                                            page.update()
                                            break
                                    except Exception as captcha_error:
                                        log_box.value = f"❌ reCAPTCHA検証エラー: {str(captcha_error)} (ID: {account['user_id']})\n" + \
                                            log_box.value
                                        page.update()
                                        break
                                # user bannedエラーの場合はアカウントを削除
                                elif "user banned" in room_error_str:
                                    log_box.value = f"🚫 アカウントBAN検出: アカウント(ID: {account['user_id']})を削除します\n" + \
                                        log_box.value
                                    page.update()

                                    # アカウントをデータベースから削除
                                    try:
                                        db.delete_account_by_user_id(
                                            account["user_id"])
                                        log_box.value = f"🗑️ アカウント削除完了: ID {account['user_id']}\n" + \
                                            log_box.value
                                    except Exception as delete_error:
                                        log_box.value = f"❌ アカウント削除失敗: ID {account['user_id']} - {str(delete_error)}\n" + \
                                            log_box.value
                                    page.update()
                                    break  # このアカウントでの送信を停止
                                # user not foundエラーの場合もBANとして扱う
                                elif "user not found" in room_error_str and "(コード: -5)" in room_error_str:
                                    log_box.value = f"⚠️ BANアカウントを削除: user_id={account['user_id']} (user not foundエラー)\n" + \
                                        log_box.value
                                    page.update()

                                    # アカウントをデータベースから削除
                                    try:
                                        db.delete_account_by_user_id(
                                            account["user_id"])
                                        log_box.value = f"🗑️ アカウント削除完了: ID {account['user_id']}\n" + \
                                            log_box.value
                                    except Exception as delete_error:
                                        log_box.value = f"❌ アカウント削除失敗: ID {account['user_id']} - {str(delete_error)}\n" + \
                                            log_box.value
                                    page.update()
                                    break  # このアカウントでの送信を停止
                                else:
                                    # その他のエラーは再発生させる
                                    raise room_error

                            # メッセージ送信
                            client.send_message(room_id, template)

                            # 送信成功時にアカウントの使用状態を更新
                            db.update_account_usage(account["user_id"])
                            # DM送信履歴を記録
                            db.record_dm_sent(account["user_id"], user_id)
                            sent_dms += 1
                            account_sent_count += 1
                            log_box.value = f"✅ DM送信成功 ({sent_dms}/{total_dms}) From: {account['user_id']} To: {user_id}\n" + \
                                log_box.value
                            page.update()
                        except Exception as e:
                            error_str = str(e)

                            # Captcha requiredエラーの場合はreCAPTCHA検証を実行（メッセージ送信時）
                            if "Captcha required" in error_str or "error_code\":-29" in error_str:
                                log_box.value = f"🔐 Captchaが必要です（メッセージ送信時）。reCAPTCHA検証を開始します... (ID: {account['user_id']})\n" + \
                                    log_box.value
                                page.update()

                                # reCAPTCHA検証を実行
                                try:
                                    # reCAPTCHAトークンを取得
                                    token = client.get_captcha_token_from_bot()
                                    if token:
                                        # トークンを検証（IP BANの場合は自動リトライ）
                                        if client.verify_captcha(token):
                                            log_box.value = f"✅ reCAPTCHA検証成功！処理を続行します (ID: {account['user_id']})\n" + \
                                                log_box.value
                                            page.update()
                                            # 検証成功後は次のユーザーへ
                                            continue
                                        else:
                                            log_box.value = f"❌ reCAPTCHA検証失敗 (ID: {account['user_id']})\n" + \
                                                log_box.value
                                            page.update()
                                            break
                                except Exception as captcha_error:
                                    log_box.value = f"❌ reCAPTCHA検証エラー: {str(captcha_error)} (ID: {account['user_id']})\n" + \
                                        log_box.value
                                    page.update()
                                    break

                            elif "403" in error_str and "Captcha required" not in error_str:
                                log_box.value = f"❌ IP BANされました。このアカウントでの送信を停止します。\n" + \
                                    log_box.value
                                page.update()
                                break  # このアカウントでの送信を停止
                            else:
                                # user not foundエラーの場合は即座にBANアカウントとして削除
                                if "user not found" in error_str and "(コード: -5)" in error_str:
                                    log_box.value = f"⚠️ BANアカウントを削除: user_id={account['user_id']} (user not foundエラー)\n" + \
                                        log_box.value
                                    page.update()

                                    # アカウントをデータベースから削除
                                    try:
                                        db.delete_account_by_user_id(
                                            account["user_id"])
                                        log_box.value = f"🗑️ アカウント削除完了: ID {account['user_id']}\n" + \
                                            log_box.value
                                    except Exception as delete_error:
                                        log_box.value = f"❌ アカウント削除失敗: ID {account['user_id']} - {str(delete_error)}\n" + \
                                            log_box.value
                                    page.update()
                                    break  # このアカウントでの送信を停止
                                else:
                                    log_box.value = f"❌ DM送信失敗 From: {account['user_id']} To: {user_id}: {error_str}\n" + \
                                        log_box.value
                                    page.update()

                    # アカウントの使用日時を更新（ループ終了時）
                    db.update_account_usage(account["user_id"])
                    processed_accounts += 1  # 処理完了時にカウント

                except Exception as e:
                    error_str = str(e)
                    # Captcha requiredエラーの場合はreCAPTCHA検証を実行（アカウント全体の処理）
                    if "Captcha required" in error_str or "error_code\":-29" in error_str:
                        log_box.value = f"🔐 Captchaが必要です（アカウント処理時）。reCAPTCHA検証を開始します... (ID: {account['user_id']})\n" + \
                            log_box.value
                        page.update()

                        # reCAPTCHA検証を実行
                        try:
                            # reCAPTCHAトークンを取得
                            token = client.get_captcha_token_from_bot()
                            if token:
                                # トークンを検証（IP BANの場合は自動リトライ）
                                if client.verify_captcha(token):
                                    log_box.value = f"✅ reCAPTCHA検証成功！処理を続行します (ID: {account['user_id']})\n" + \
                                        log_box.value
                                    page.update()
                                    # 検証成功後は次のアカウントへ
                                    processed_accounts += 1
                                    continue
                                else:
                                    log_box.value = f"❌ reCAPTCHA検証失敗 (ID: {account['user_id']})\n" + \
                                        log_box.value
                                    page.update()
                            else:
                                log_box.value = f"❌ reCAPTCHAトークンの取得に失敗 (ID: {account['user_id']})\n" + \
                                    log_box.value
                                page.update()
                        except Exception as captcha_error:
                            log_box.value = f"❌ reCAPTCHA検証エラー: {str(captcha_error)} (ID: {account['user_id']})\n" + \
                                log_box.value
                            page.update()
                    elif "403" in error_str and "Captcha required" not in error_str:
                        log_box.value += f"❌ IP BANされました。次のアカウントで処理を継続します。\n"
                        page.update()
                    else:
                        log_box.value += f"❌ アカウント処理失敗 ID: {account['user_id']}: {error_str}\n"
                        page.update()

                    processed_accounts += 1  # エラー時もカウント

            # 統計情報の表示
            stats = db.get_dm_stats(1)  # 直近24時間の統計
            log_box.value += f"\n【送信完了】\n"
            log_box.value += f"今回の送信: 成功 {sent_dms}/{total_dms}\n"
            log_box.value += f"24時間の統計: 成功 {stats['success']}/{stats['total']} (失敗: {stats['failed']})\n"

        except Exception as e:
            log_box.value += f"\n❌ エラーが発生しました: {str(e)}\n"

        finally:
            run_btn.disabled = False
            stop_btn.disabled = True
            is_running = False
            page.update()

    def on_dm_run(e):
        error_msg.value = ""
        send_num = unicodedata.normalize("NFKC", send_count.value)
        acc_num = unicodedata.normalize("NFKC", account_total.value)
        resend_num = unicodedata.normalize("NFKC", resend_days.value)

        if not (is_valid_num(send_num) and is_valid_num(acc_num) and is_valid_num(resend_num)):
            error_msg.value = "全て半角数字かつ1以上で入力してください。"
            page.update()
            return

        # プロフィール設定の取得
        profile_data = None
        if profile_settings.content.controls[1].value:
            profile_data = {
                "unset": {
                    "image": selected_files["unset"],
                    "nickname": unset_nickname.value.strip(),
                    "biography": unset_biography.value.strip(),
                    "gender": "unset"
                },
                "female": {
                    "image": selected_files["female"],
                    "nickname": female_nickname.value.strip(),
                    "biography": female_biography.value.strip(),
                    "gender": "female"
                }
            }
            # プロフィール設定の入力チェック
            if not profile_data["unset"]["nickname"] or not profile_data["female"]["nickname"]:
                error_msg.value = "ニックネームを入力してください。"
                page.update()
                return
            if not profile_data["unset"]["image"] or not profile_data["female"]["image"]:
                error_msg.value = "プロフィール画像を選択してください。"
                page.update()
                return

        # 別スレッドでDM送信を実行
        thread = threading.Thread(target=send_dm_thread, args=(profile_data,))
        thread.daemon = True
        thread.start()

    def on_stop(e):
        nonlocal is_running
        is_running = False
        stop_btn.disabled = True
        page.update()

    run_btn.on_click = on_dm_run
    stop_btn.on_click = on_stop

    return ft.Column([
        ft.Text("DM一斉送信設定", size=20, weight="bold"),
        ft.Text(rule_text, size=13),
        ft.Row([send_count, account_total]),
        exclude_used_chk,
        ft.Row([resend_days, ft.Text("日以上で再送信許可", size=13)]),
        profile_settings,
        ft.Row([run_btn, stop_btn]),
        error_msg,
        log_box
    ])

# ================== DMテンプレ編集タブ ==================


def dm_template_tab_content(page):
    initialize_services()

    # データベースからテンプレートを読み込み
    dm_templates.clear()
    dm_templates.update(db.get_dm_templates())

    selected_template = ft.Dropdown(
        label="編集するテンプレート",
        options=[ft.dropdown.Option(key) for key in dm_templates.keys()],
        value=list(dm_templates.keys())[0] if dm_templates else None,
        width=180
    )
    template_field = ft.TextField(
        label="テンプレート内容",
        value=dm_templates.get(selected_template.value, ""),
        multiline=True,
        min_lines=6,
        max_lines=10,
        width=400
    )
    save_btn = ft.ElevatedButton("保存", width=120)
    info = ft.Text("")

    def on_template_select(e):
        template_field.value = dm_templates.get(selected_template.value, "")
        info.value = ""
        page.update()

    def on_save(e):
        if db.update_dm_template(selected_template.value, template_field.value):
            dm_templates[selected_template.value] = template_field.value
            info.value = f"{selected_template.value} テンプレートを保存しました。"
            info.color = "green"
        else:
            info.value = "テンプレートの保存に失敗しました。"
            info.color = "red"
        page.update()

    selected_template.on_change = on_template_select
    save_btn.on_click = on_save

    return ft.Column([
        ft.Text("DMテンプレート編集", size=20, weight="bold"),
        selected_template,
        template_field,
        save_btn,
        info,
    ])

# ================== アカウント削除タブ ==================


def account_delete_tab_content(page):
    initialize_services()

    info_text = ft.Text("指定日数より前に作成したアカウントを一括削除できます。", size=15)
    days_field = ft.TextField(label="何日前より前のアカウントを削除", value="30", width=180)
    used_chk = ft.Checkbox(label="使用済みアカウントのみ削除", value=False)
    run_btn = ft.ElevatedButton("該当アカウントを削除", width=240)
    status = ft.Text("", color="red")
    log_box = ft.TextField(
        label="ログ",
        multiline=True,
        min_lines=3,
        max_lines=6,
        read_only=True,
        width=400,
        text_size=13  # テキストサイズを小さくして見やすく
    )

    def on_delete(e):
        days = days_field.value.strip()
        if not days.isdigit() or int(days) <= 0:
            status.value = "日数は半角数字で入力してください"
            page.update()
            return

        try:
            def log_callback(msg):
                # 既存のログの先頭に新しいメッセージを追加
                log_box.value = msg + log_box.value
                page.update()

            log_box.value = ""  # ログをクリア
            deleted = db.delete_old_accounts(
                int(days), used_chk.value, log_callback=log_callback)
            status.value = ""
        except Exception as e:
            status.value = f"削除処理でエラーが発生しました: {str(e)}"
        page.update()

    run_btn.on_click = on_delete

    return ft.Column([
        ft.Text("アカウント削除（作成日ベース）", size=20, weight="bold"),
        info_text,
        ft.Row([days_field, ft.Text("日以前", size=13)]),
        used_chk,
        run_btn,
        status,
        log_box
    ])

# ================== プロキシ設定タブ ==================


def proxy_tab_content(page):
    initialize_services()

    # プロキシ設定
    use_proxy = ft.Checkbox(label="プロキシを使用する", value=False)
    proxy_string = ft.TextField(
        label="プロキシ文字列（例: http://username:password@host:port）",
        width=400,
        disabled=True
    )
    status_text = ft.Text("", size=13)
    add_btn = ft.ElevatedButton("設定", width=100, disabled=True)
    error_msg = ft.Text("", color="red", size=13)

    def parse_proxy_string(proxy_str: str) -> Optional[dict]:
        """プロキシ文字列をパース
        例: http://username:password@host:port
        """
        try:
            # プロトコルを除去
            if "://" in proxy_str:
                proxy_str = proxy_str.split("://")[1]

            # ユーザー名:パスワード@ホスト:ポート の形式をパース
            auth, address = proxy_str.split("@")
            username, password = auth.split(":")
            host, port = address.split(":")

            return {
                "host": host,
                "port": port,
                "username": username,
                "password": password
            }
        except Exception:
            return None

    def on_use_proxy_change(e):
        """プロキシ使用有無の切り替え"""
        proxy_settings["use_proxy"] = use_proxy.value
        proxy_string.disabled = not use_proxy.value
        add_btn.disabled = not use_proxy.value
        if not use_proxy.value:
            # プロキシを無効化
            db.delete_all_proxies()
            status_text.value = ""
            proxy_string.value = ""  # 入力フィールドをクリア
            error_msg.value = ""
        page.update()

    def on_add_proxy(e):
        """プロキシを設定"""
        if not use_proxy.value:
            error_msg.value = "プロキシを使用するにチェックを入れてください"
            page.update()
            return

        error_msg.value = ""
        status_text.value = ""

        # プロキシ文字列をパース
        proxy_info = parse_proxy_string(proxy_string.value.strip())
        if not proxy_info:
            error_msg.value = "プロキシ文字列の形式が正しくありません"
            page.update()
            return

        # 既存のプロキシを削除
        db.delete_all_proxies()

        # 新しいプロキシを追加
        if db.add_proxy(
            proxy_info["host"],
            int(proxy_info["port"]),
            proxy_info["username"],
            proxy_info["password"]
        ):
            # フォームをクリア
            status_text.value = "✅ プロキシを設定しました"
            status_text.color = "green"
            error_msg.value = ""
        else:
            error_msg.value = "プロキシの設定に失敗しました"
        page.update()

    def on_proxy_string_change(e):
        """プロキシ文字列の入力時の処理"""
        if not use_proxy.value:
            proxy_string.value = ""
            page.update()
            return

    use_proxy.on_change = on_use_proxy_change
    add_btn.on_click = on_add_proxy
    proxy_string.on_change = on_proxy_string_change

    # 初期表示
    current_proxy = db.get_proxies(active_only=True)
    if current_proxy:
        proxy = current_proxy[0]
        proxy_str = f"http://{proxy['username']}:{proxy['password']}@{proxy['host']}:{proxy['port']}"
        proxy_string.value = proxy_str
        use_proxy.value = True
        proxy_settings["use_proxy"] = True
        status_text.value = "✅ プロキシが設定されています"
        status_text.color = "green"
        proxy_string.disabled = False
        add_btn.disabled = False

    return ft.Column([
        ft.Text("プロキシ設定", size=20, weight="bold"),
        ft.Text("※ルーティングプロキシを使用する場合は1つのプロキシのみ設定してください", size=13, color="blue"),
        ft.Text("※プロキシを使用するにチェックを入れてから設定してください", size=13, color="blue"),
        use_proxy,
        proxy_string,
        add_btn,
        error_msg,
        status_text,
    ])

# ================== メールAPI設定タブ ==================


def mail_api_tab_content(page):
    initialize_services()

    # メールAPI設定
    api_key = ft.TextField(
        label="APIキー",
        width=400,
        value="2a00e931-ae4f-4fec-a20b-0aa02aa8d007"
    )
    status_text = ft.Text("", size=13)
    save_btn = ft.ElevatedButton("設定を保存", width=120)
    error_msg = ft.Text("", color="red", size=13)

    def on_save_mail_api(e):
        """メールAPI設定を保存"""
        error_msg.value = ""
        status_text.value = ""

        key = api_key.value.strip()

        if not key:
            error_msg.value = "APIキーを入力してください"
            page.update()
            return

        # メールAPI設定を保存
        if db.update_mail_api_setting(key):
            status_text.value = "✅ メールAPI設定を保存しました"
            status_text.color = "green"
            error_msg.value = ""
        else:
            error_msg.value = "メールAPI設定の保存に失敗しました"
        page.update()

    save_btn.on_click = on_save_mail_api

    # 初期表示
    current_setting = db.get_mail_api_setting()
    if current_setting:
        api_key.value = current_setting["api_key"]
        status_text.value = "✅ メールAPI設定が保存されています"
        status_text.color = "green"

    return ft.Column([
        ft.Text("メールAPI設定", size=20, weight="bold"),
        ft.Text("※メールアドレス取得用のAPI設定を行います", size=13, color="blue"),
        ft.Text("※この設定はプロキシを使用せずに直接アクセスされます", size=13, color="blue"),
        api_key,
        save_btn,
        error_msg,
        status_text,
    ])

# ================== CapMonster API設定タブ ==================


def capmonster_api_tab_content(page):
    initialize_services()

    # CapMonster API設定
    api_key = ft.TextField(
        label="APIキー",
        width=400,
        value="305e4f56e80739a00ad6491940175bd2"
    )
    status_text = ft.Text("", size=13)
    save_btn = ft.ElevatedButton("設定を保存", width=120)
    error_msg = ft.Text("", color="red", size=13)

    def on_save_capmonster_api(e):
        """CapMonster API設定を保存"""
        error_msg.value = ""
        status_text.value = ""

        key = api_key.value.strip()

        if not key:
            error_msg.value = "APIキーを入力してください"
            page.update()
            return

        # CapMonster API設定を保存
        if db.update_capmonster_setting(key):
            status_text.value = "✅ CapMonster API設定を保存しました"
            status_text.color = "green"
            error_msg.value = ""
        else:
            error_msg.value = "CapMonster API設定の保存に失敗しました"
        page.update()

    save_btn.on_click = on_save_capmonster_api

    # 初期表示
    current_setting = db.get_capmonster_setting()
    if current_setting:
        api_key.value = current_setting["api_key"]
        status_text.value = "✅ CapMonster API設定が保存されています"
        status_text.color = "green"

    return ft.Column([
        ft.Text("CapMonster API設定", size=20, weight="bold"),
        ft.Text("※reCAPTCHA自動解決用のAPI設定を行います", size=13, color="blue"),
        ft.Text("※Captchaエラー時に自動的にreCAPTCHAを解決します", size=13, color="blue"),
        api_key,
        save_btn,
        error_msg,
        status_text,
    ])

# ================== メイン関数 ==================


def main(page: ft.Page):
    page.title = "himitsutalk 自動化GUI"
    page.window_width = 580
    page.window_height = 800
    page.window_min_width = 580
    page.window_min_height = 800
    page.padding = 10
    page.scroll = True

    # ログボックスのサイズを調整
    def adjust_log_box_size(log_box):
        log_box.min_lines = 10
        log_box.max_lines = 20
        log_box.width = 560
        return log_box

    # 各タブのログボックスを調整
    account_tab = account_tab_content(page)
    account_log = account_tab.controls[-1]  # 最後の要素（ログボックス）
    adjust_log_box_size(account_log)

    dm_tab = dm_tab_content(page)
    dm_log = dm_tab.controls[-1]  # 最後の要素（ログボックス）
    adjust_log_box_size(dm_log)

    account_delete_tab = account_delete_tab_content(page)
    delete_log = account_delete_tab.controls[-1]  # 最後の要素（ログボックス）
    adjust_log_box_size(delete_log)

    tabs = ft.Tabs(
        selected_index=0,
        animation_duration=200,
        tabs=[
            ft.Tab(
                text="アカウント作成",
                content=account_tab,
            ),
            ft.Tab(
                text="DM一斉送信",
                content=dm_tab,
            ),
            ft.Tab(
                text="DMテンプレート編集",
                content=dm_template_tab_content(page),
            ),
            ft.Tab(
                text="アカウント削除",
                content=account_delete_tab,
            ),
            ft.Tab(
                text="プロキシ設定",
                content=proxy_tab_content(page),
            ),
            ft.Tab(
                text="メールAPI設定",
                content=mail_api_tab_content(page),
            ),
            ft.Tab(
                text="CapMonster API設定",
                content=capmonster_api_tab_content(page),
            ),
        ],
        expand=1,
    )

    page.add(tabs)


ft.app(target=main)
