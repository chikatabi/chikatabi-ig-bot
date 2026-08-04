"""毎朝のバッチ：リサーチ → 選定 → 文言生成 → 画像生成 → 承認依頼。

このスクリプトは投稿しない。投稿は publish 側のワークフローが担当する。
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime, timedelta, timezone

import compose
import notify
import publish
import render
import research
from common import ASSETS, env, load_config, write_queue

JST = timezone(timedelta(hours=9))


def image_url_for(date: str, idx: int) -> str:
    """コミット後に Instagram から取りに来られる公開URL。"""
    repo = env("GITHUB_REPOSITORY")  # 例 chika/chikatabi-ig-bot
    branch = env("GITHUB_REF_NAME", required=False) or "main"
    return f"https://raw.githubusercontent.com/{repo}/{branch}/assets/img/{date}_{idx}.jpg"


def main() -> None:
    cfg = load_config()
    date = datetime.now(JST).strftime("%Y-%m-%d")
    n = cfg["posts_per_day"]

    candidates = research.collect()
    if len(candidates) < n:
        raise SystemExit(f"候補が{len(candidates)}件しかありません。sources.yaml を見直してください。")

    posted_topics = publish.load_posted_topics(cfg["dedupe_window"])
    posts = compose.compose(candidates, posted_topics, n)
    compose.save_draft(date, posts)

    # 数字を含むネタを自動で落とす設定なら、ここで除外する
    if cfg["numeric_policy"] == "block":
        kept = [p for p in posts if not p.get("has_numbers")]
        dropped = len(posts) - len(kept)
        if dropped:
            print(f"数字を含む投稿を{dropped}本、保留にしました（numeric_policy: block）")
        posts = kept
        if not posts:
            notify.send_text(f"【{date}】数字を含むネタしか無かったため、本日の投稿はありません。")
            return

    image_urls = []
    for i, post in enumerate(posts):
        path = ASSETS / "img" / f"{date}_{i}.jpg"
        render.render(post, path)
        image_urls.append(image_url_for(date, i))
        print(f"画像を生成: {path.name}")

    write_queue(date, {"date": date, "posts": posts, "image_urls": image_urls})

    if cfg["approval"] == "line":
        notify.send_approval(date, posts, image_urls)
    else:
        print("approval: auto のため、承認をスキップします（publish ワークフローが投稿します）")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 — 失敗したら黙って死なずにLINEへ知らせる
        traceback.print_exc()
        try:
            notify.send_text(f"【Instagram bot】朝のバッチが失敗しました。\n{traceback.format_exc()[-400:]}")
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)
