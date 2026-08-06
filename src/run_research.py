"""毎朝のバッチ：リサーチ → 選定 → 文言生成 → 画像生成 → 承認依頼。

このスクリプトは投稿しない。投稿は publish 側のワークフローが担当する。
"""
from __future__ import annotations

import hashlib
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import compose
import notify
import publish
import render
import research
from common import ASSETS, env, load_config, write_queue

JST = timezone(timedelta(hours=9))


def image_url_for(date: str, idx: int, path: Path) -> str:
    """コミット後に LINE と Instagram が取りに来られる公開URL。

    末尾に中身のハッシュを付ける。ファイル名は日付固定なので、同じ日に
    作り直すとURLが変わらず、LINEが最初に取得した画像をキャッシュしたまま
    差し替わらない（実際に単色版が表示され続けた）。raw.githubusercontent.com
    はクエリを無視して同じ画像を返すので、中身が変わったときだけURLが変わる。
    """
    repo = env("GITHUB_REPOSITORY")  # 例 chika/chikatabi-ig-bot
    branch = env("GITHUB_REF_NAME", required=False) or "main"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    return (
        f"https://raw.githubusercontent.com/{repo}/{branch}"
        f"/assets/img/{date}_{idx}.jpg?v={digest}"
    )


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
        image_urls.append(image_url_for(date, i, path))
        print(f"画像を生成: {path.name}")

    write_queue(date, {"date": date, "posts": posts, "image_urls": image_urls})

    # 承認依頼はここでは送らない。画像をコミットしてから run_notify.py が送る。
    # ここで送ると、LINEが画像を取りに来た時点でまだ公開URLに画像が無い。
    print(f"投稿案 {len(posts)}本をキューに保存しました。承認依頼は画像のコミット後に送ります")


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
