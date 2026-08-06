"""キューを読んで LINE に承認依頼を送る。

**画像をコミットした後に実行すること。** 順序が逆だと、LINEが画像を取りに
来た時点で raw.githubusercontent.com にまだ画像が無く、404 を返す。
LINEアプリは取得失敗をキャッシュするので、あとからURLが有効になっても
承認画面に画像が出ないままになる。

もともとは run_research.py の最後で送っていたが、コミットより前に走って
いたため分離した。
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

import requests

import notify
from common import QUEUE, load_config

JST = timezone(timedelta(hours=9))
WAIT_SECONDS = 40


def wait_until_public(url: str) -> bool:
    """画像が公開URLで取れるようになるまで待つ。

    push した直後は raw.githubusercontent.com に反映されるまで数秒かかる。
    ここで待たずに送ると、LINEが404を掴む。
    """
    deadline = time.time() + WAIT_SECONDS
    while time.time() < deadline:
        try:
            if requests.head(url, timeout=10).status_code == 200:
                return True
        except Exception:  # noqa: BLE001 — 通信エラーは単にリトライする
            pass
        time.sleep(3)
    return False


def main() -> None:
    cfg = load_config()
    date = datetime.now(JST).strftime("%Y-%m-%d")

    path = QUEUE / f"{date}.json"
    if not path.exists():
        print(f"キューがありません（{date}）。送信をスキップします")
        return

    q = json.loads(path.read_text(encoding="utf-8"))
    posts, image_urls = q.get("posts", []), q.get("image_urls", [])

    if not posts:
        print("投稿案が0件です。送信をスキップします")
        return

    if cfg["approval"] != "line":
        print("approval: auto のため、承認をスキップします（publish ワークフローが投稿します）")
        return

    if image_urls and not wait_until_public(image_urls[0]):
        # 画像が出ないだけで承認自体はできるので、送信は続ける
        print(f"警告: {WAIT_SECONDS}秒待っても画像が公開URLで取れませんでした。"
              f"承認画面で画像が表示されないかもしれません")

    notify.send_approval(date, posts, image_urls)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 — 失敗したら黙って死なずにLINEへ知らせる
        traceback.print_exc()
        try:
            notify.send_text(f"【Instagram bot】承認依頼の送信に失敗しました。\n{traceback.format_exc()[-400:]}")
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)
