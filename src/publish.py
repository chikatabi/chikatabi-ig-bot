"""Instagram へ実際に投稿する。

Instagram Graph API の 2ステップ方式：
  1. /media        … 画像URLとキャプションを渡してコンテナを作る
  2. /media_publish … コンテナIDを渡して公開する

画像は「公開URLに置かれている」必要がある（バイナリの直接アップロード不可）。
このリポジトリを public にして raw.githubusercontent.com のURLを使う。
"""
from __future__ import annotations

import sys
import time

import requests

from common import POSTED, env

BASE = "https://graph.instagram.com/v23.0"


def _ig_user_id(token: str) -> str:
    r = requests.get(f"{BASE}/me", params={"fields": "id,username", "access_token": token}, timeout=30)
    r.raise_for_status()
    data = r.json()
    print(f"投稿先アカウント: @{data.get('username')} ({data['id']})")
    return data["id"]


def _create_container(ig_id: str, token: str, image_url: str, caption: str) -> str:
    r = requests.post(
        f"{BASE}/{ig_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": token},
        timeout=60,
    )
    if not r.ok:
        raise SystemExit(f"コンテナ作成に失敗: {r.status_code} {r.text}")
    return r.json()["id"]


def _wait_ready(container_id: str, token: str, timeout_s: int = 120) -> None:
    """FINISHED になるまで待つ。Instagram 側が画像を取りに行く時間が要る。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = requests.get(
            f"{BASE}/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=30,
        )
        r.raise_for_status()
        status = r.json().get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise SystemExit(f"コンテナが {status} になりました: {r.json()}")
        time.sleep(5)
    raise SystemExit("コンテナが FINISHED になりませんでした（タイムアウト）")


def publish(image_url: str, caption: str) -> str:
    token = env("IG_ACCESS_TOKEN")
    ig_id = env("IG_USER_ID", required=False) or _ig_user_id(token)

    print(f"画像URL: {image_url}")
    container_id = _create_container(ig_id, token, image_url, caption)
    print(f"コンテナ作成: {container_id}")

    _wait_ready(container_id, token)

    r = requests.post(
        f"{BASE}/{ig_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=60,
    )
    if not r.ok:
        raise SystemExit(f"公開に失敗: {r.status_code} {r.text}")
    media_id = r.json()["id"]
    print(f"投稿完了: {media_id}")
    return media_id


def record(date: str, post: dict, media_id: str) -> None:
    """投稿履歴を残す。次回以降の重複除外はこのファイルを見る。"""
    new = not POSTED.exists()
    with open(POSTED, "a", encoding="utf-8") as f:
        if new:
            f.write("date\ttopic_key\theadline\tsource_url\tmedia_id\n")
        f.write(
            f"{date}\t{post['topic_key']}\t{post['headline']}\t"
            f"{post.get('source_url', '')}\t{media_id}\n"
        )


def load_posted_topics(limit: int) -> list[str]:
    if not POSTED.exists():
        return []
    with open(POSTED, encoding="utf-8") as f:
        rows = [ln.rstrip("\n").split("\t") for ln in f.readlines()[1:]]
    return [r[1] for r in rows if len(r) > 1][-limit:]


if __name__ == "__main__":
    # 手動テスト用: python src/publish.py <画像URL> "<キャプション>"
    publish(sys.argv[1], sys.argv[2])
