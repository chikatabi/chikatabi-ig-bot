"""候補を精査して、その日の投稿（画像の文言＋キャプション）を決める。

Claude に「選ぶ」と「書く」を一度にやらせる。構造化出力を使うので、
返ってくる JSON の形は保証される（パースに失敗しない）。
"""
from __future__ import annotations

import json

import anthropic

from common import DRAFTS, load_config

SYSTEM = """あなたは旅行情報メディア「CHIKATABI」のInstagram運用担当です。
マイル・特典航空券・ホテル・セールなど「お得な旅」の情報を、
旅好きの一般層に向けてわかりやすく届けるのが仕事です。

## 選定基準
- 読者が「今すぐ得をする」情報を優先する（セール、キャンペーン、制度変更）
- 個人の日記・感想文は選ばない
- 特定の地方だけに極端に閉じた話題は避ける
- 過去に投稿済みのテーマ（後述）と実質的に同じ話題は選ばない

## 画像の文言（headline / subline）
- headline: 12〜18文字。スマホで一瞬で読める強さ。体言止め推奨
- subline: 15〜25文字。headline を補う一文
- 誇張しない。「絶対」「必ず」「史上最安」など断定的な煽りは使わない

## キャプション
- 冒頭1行で結論。そのあと詳細を3〜5行
- 最後に一言、行動を促す（保存・プロフィールリンクなど）
- 絵文字は控えめに（1投稿に3個まで）
- 「〜だよね」のような馴れ馴れしい語尾は使わない。丁寧だが硬すぎない文体

## ハッシュタグ
- 10〜15個。日本語中心。#マイル #特典航空券 のような検索されるタグを使う

## 数字の扱い（最重要）
- 元記事に書かれていない数字を絶対に作らない
- 割引率・金額・マイル数・期限は、元記事の記述をそのまま使う
- 少しでも確信が持てない数字は書かない。書かずに済ませる
- has_numbers には、割引率・金額・マイル数・期限のいずれかを含む場合 true を入れる
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "posts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic_key": {
                        "type": "string",
                        "description": "重複判定用の短いテーマ名。例『ANA国際線タイムセール』",
                    },
                    "headline": {"type": "string"},
                    "subline": {"type": "string"},
                    "caption": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "source_url": {"type": "string"},
                    "source_title": {"type": "string"},
                    "has_numbers": {"type": "boolean"},
                    "why": {
                        "type": "string",
                        "description": "この話題を選んだ理由。1文",
                    },
                },
                "required": [
                    "topic_key",
                    "headline",
                    "subline",
                    "caption",
                    "hashtags",
                    "source_url",
                    "source_title",
                    "has_numbers",
                    "why",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["posts"],
    "additionalProperties": False,
}


def compose(candidates: list[dict], posted_topics: list[str], n: int) -> list[dict]:
    cfg = load_config()
    client = anthropic.Anthropic()

    cand_text = "\n".join(
        f"{i}. [{c['source']}] {c['title']}\n   {c['summary'][:200]}\n   {c['url']}"
        for i, c in enumerate(candidates, 1)
    )
    posted_text = "\n".join(f"- {t}" for t in posted_topics) or "（まだありません）"

    user = f"""## 今日の候補ネタ
{cand_text}

## すでに投稿済みのテーマ（これらと同じ話題は選ばない）
{posted_text}

上の候補から{n}本を選び、Instagram投稿を作ってください。
{n}本は互いに違う切り口にしてください（同じ航空会社のセールを2本、などは避ける）。"""

    resp = client.messages.create(
        model=cfg["model"],
        max_tokens=16000,
        system=SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": user}],
    )

    if resp.stop_reason == "refusal":
        raise SystemExit("Claude が生成を拒否しました。候補ネタを確認してください。")

    text = next(b.text for b in resp.content if b.type == "text")
    posts = json.loads(text)["posts"]
    print(f"投稿案 {len(posts)}本を生成しました")
    for p in posts:
        print(f"  ・{p['headline']} — {p['why']}")
    return posts


def save_draft(date: str, posts: list[dict]) -> None:
    with open(DRAFTS / f"{date}.json", "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
