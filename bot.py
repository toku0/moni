from capmonster_python import CapmonsterClient, RecaptchaV2Task
from database import Database


def get_recaptcha_token():
    # データベースからAPIキーを取得
    db = Database()
    capmonster_setting = db.get_capmonster_setting()

    if not capmonster_setting:
        raise Exception("CapMonster API設定が見つかりません")

    api_key = capmonster_setting["api_key"]
    client = CapmonsterClient(api_key=api_key)

    task = RecaptchaV2Task(
        websiteURL="https://himitsutalk-039.himahimatalk.com/",
        websiteKey="6Ld21qgZAAAAAHLiTSxuIi0ruAgNDrLeAOW1K4E2",
        isInvisible=True,
        userAgent="Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
    )
    task_id = client.create_task(task)
    result = client.join_task_result(task_id)
    print(f"生成トークン:{result["gRecaptchaResponse"]}")
    return result["gRecaptchaResponse"]


get_recaptcha_token()
