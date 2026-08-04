"""承認後の投稿バッチ。

LINE で「投稿する」が押されると Apps Script が GitHub の
repository_dispatch を叩き、このスクリプトが 1本だけ投稿する。
approval: auto の場合は、時刻起動でその日の未投稿分を投稿する。
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timedelta, timezone

import notify
import publish
from common import load_config, read_queue, write_queue

JST = timezone(timedelta(hours=9))


def publish_one(date: str, idx: int) -> None:
    queue = read_queue(date)
    if queue is None:
        raise SystemExit(f"{date} のキューがありません。")
    if idx >= len(queue["posts"]):
        raise SystemExit(f"{date} に {idx} 番の投稿はありません。")

    post = queue["posts"][idx]
    if post.get("published_media_id"):
        print(f"{date}#{idx} は既に投稿済みです。何もしません。")
        return

    caption = post["caption"].rstrip() + "\n\n" + " ".join(
        t if t.startswith("#") else f"#{t}" for t in post["hashtags"]
    )
    media_id = publish.publish(queue["image_urls"][idx], caption)

    post["published_media_id"] = media_id
    write_queue(date, queue)
    publish.record(date, post, media_id)
    notify.send_text(f"投稿しました：{post['headline']}")


def main() -> None:
    cfg = load_config()
    date = os.environ.get("POST_DATE") or datetime.now(JST).strftime("%Y-%m-%d")

    idx_raw = os.environ.get("POST_INDEX", "")
    if idx_raw != "":
        publish_one(date, int(idx_raw))
        return

    # 承認なしモード：その日の未投稿を順に出す
    if cfg["approval"] != "auto":
        raise SystemExit("POST_INDEX が指定されていません（approval: line では必須）。")
    queue = read_queue(date)
    if queue is None:
        raise SystemExit(f"{date} のキューがありません。")
    for i, post in enumerate(queue["posts"]):
        if not post.get("published_media_id"):
            publish_one(date, i)
            return
    print("本日投稿すべきものはありません。")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        try:
            notify.send_text(f"【Instagram bot】投稿に失敗しました。\n{traceback.format_exc()[-400:]}")
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)
