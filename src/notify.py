"""LINE に承認依頼を送る。

画像つきのカードを人数分（=投稿数分）並べて、それぞれに
「投稿する」「やめる」ボタンを付ける。ボタンを押すと postback が
Apps Script の Webhook に飛び、そこから GitHub Actions を起動する。
"""
from __future__ import annotations

import json

import requests

from common import env

PUSH_URL = "https://api.line.me/v2/bot/message/push"


def _bubble(date: str, idx: int, post: dict, image_url: str) -> dict:
    warn = "⚠️ 数字・期限を含みます。元記事と照合してください" if post.get("has_numbers") else ""
    body_contents = [
        {"type": "text", "text": post["headline"], "weight": "bold", "size": "md", "wrap": True},
        {"type": "text", "text": post["subline"], "size": "sm", "color": "#666666", "wrap": True, "margin": "sm"},
    ]
    if warn:
        body_contents.append(
            {"type": "text", "text": warn, "size": "xs", "color": "#C75B39", "wrap": True, "margin": "md"}
        )
    body_contents.append(
        {"type": "text", "text": post.get("source_title", ""), "size": "xxs",
         "color": "#999999", "wrap": True, "margin": "md"}
    )

    return {
        "type": "bubble",
        "hero": {
            "type": "image",
            "url": image_url,
            "size": "full",
            "aspectRatio": "1:1",
            "aspectMode": "cover",
        },
        "body": {"type": "box", "layout": "vertical", "contents": body_contents},
        "footer": {
            "type": "box",
            "layout": "horizontal",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "height": "sm",
                    "action": {
                        "type": "postback",
                        "label": "投稿する",
                        "data": f"act=approve&date={date}&i={idx}",
                        "displayText": f"「{post['headline']}」を投稿します",
                    },
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "action": {
                        "type": "postback",
                        "label": "やめる",
                        "data": f"act=reject&date={date}&i={idx}",
                        "displayText": f"「{post['headline']}」は見送ります",
                    },
                },
                {
                    "type": "button",
                    "style": "link",
                    "height": "sm",
                    "action": {"type": "uri", "label": "元記事", "uri": post.get("source_url") or "https://www.traicy.com/"},
                },
            ],
        },
    }


def _push(token: str, to: str, messages: list[dict]) -> None:
    """LINEは1リクエスト5メッセージまで。超える分は分けて送る。"""
    for i in range(0, len(messages), 5):
        r = requests.post(
            PUSH_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            data=json.dumps({"to": to, "messages": messages[i : i + 5]}, ensure_ascii=False).encode("utf-8"),
            timeout=30,
        )
        if not r.ok:
            raise SystemExit(f"LINE送信に失敗: {r.status_code} {r.text}")


def _manual_post_messages(posts: list[dict], image_urls: list[str]) -> list[dict]:
    """手動投稿用の素材。キャプションは単独メッセージにする。

    LINEの長押しコピーはメッセージ全体を取るので、見出しや区切り線を
    混ぜるとコピーしたテキストに余計な行が入る。貼ってそのまま使えるよう、
    キャプションとハッシュタグだけのメッセージを独立して送る。
    """
    out: list[dict] = []
    for i, (post, url) in enumerate(zip(posts, image_urls), 1):
        tags = " ".join(post.get("hashtags", []))
        out.append({"type": "text", "text": f"――― {i}本目 手動投稿用 ―――\n画像を保存 → {url}"})
        out.append({"type": "text", "text": f"{post['caption']}\n\n{tags}"})
    return out


def send_approval(date: str, posts: list[dict], image_urls: list[str]) -> None:
    token = env("LINE_CHANNEL_ACCESS_TOKEN")
    to = env("LINE_TO_USER_ID")

    bubbles = [_bubble(date, i, p, u) for i, (p, u) in enumerate(zip(posts, image_urls))]
    _push(token, to, [
        {"type": "text", "text": f"【{date}】本日のInstagram投稿案です。承認をお願いします。"},
        {"type": "flex", "altText": f"{date} の投稿案", "contents": {"type": "carousel", "contents": bubbles}},
    ])
    _push(token, to, _manual_post_messages(posts, image_urls))
    print(f"LINEに承認依頼と手動投稿用の素材を送信しました（{len(bubbles)}件）")


def send_text(text: str) -> None:
    """完了報告・エラー通知用のシンプルなテキスト送信。"""
    token = env("LINE_CHANNEL_ACCESS_TOKEN")
    to = env("LINE_TO_USER_ID")
    requests.post(
        PUSH_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=json.dumps({"to": to, "messages": [{"type": "text", "text": text}]}, ensure_ascii=False).encode("utf-8"),
        timeout=30,
    )
