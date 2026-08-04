"""テンプレート組版：headline / subline から正方形JPEGを作る。

AI画像生成は使わない。文字が主役なので、決まった枠に流し込むほうが
毎回読みやすく、トーンもブレない。
"""
from __future__ import annotations

import hashlib
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from common import ASSETS, FONT, load_config


def _font(size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT), size)
    try:
        # Noto Sans JP は可変フォント。太さを名前で指定する。
        f.set_variation_by_name(weight)
    except Exception:  # noqa: BLE001 — 可変軸が無いビルドでも通常太さで描ける
        pass
    return f


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    """日本語は単語境界が無いので1文字ずつ詰めて折り返す。"""
    lines, cur = [], ""
    for ch in text:
        trial = cur + ch
        if draw.textlength(trial, font=font) <= max_width and ch != "\n":
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = "" if ch == "\n" else ch
    if cur:
        lines.append(cur)
    return lines


def _theme_for(key: str, themes: list[dict]) -> dict:
    """同じ日の2投稿が同じ配色にならないよう、キーから決定的に選ぶ。"""
    h = int(hashlib.md5(key.encode()).hexdigest(), 16)
    return themes[h % len(themes)]


def render(post: dict, out_path: Path) -> Path:
    cfg = load_config()
    S = cfg["image"]["size"]
    theme = _theme_for(post["topic_key"], cfg["image"]["themes"])

    img = Image.new("RGB", (S, S), theme["bg"])
    d = ImageDraw.Draw(img)

    margin = int(S * 0.09)
    inner = S - margin * 2

    # 上部のアクセントバー
    d.rectangle([margin, margin, margin + int(inner * 0.18), margin + 10], fill=theme["accent"])

    # 見出し（長さに応じて自動で縮める）
    size = int(S * 0.105)
    while size > int(S * 0.055):
        hf = _font(size, "Bold")
        hlines = _wrap(d, post["headline"], hf, inner)
        if len(hlines) <= 3:
            break
        size -= 6
    head_lh = int(size * 1.38)

    sub_size = int(S * 0.042)
    sf = _font(sub_size, "Medium")
    slines = _wrap(d, post["subline"], sf, inner)
    sub_lh = int(sub_size * 1.5)

    rule_gap = int(S * 0.02)
    rule_to_sub = int(S * 0.045)

    # 先にブロック全体の高さを測ってから、縦方向の中央に置く。
    # そうしないと文字数が少ない日に下半分がまるごと空く。
    block_h = len(hlines) * head_lh + rule_gap + rule_to_sub + len(slines) * sub_lh
    y = (S - block_h) // 2

    for line in hlines:
        d.text((margin, y), line, font=hf, fill=theme["fg"])
        y += head_lh

    # 見出しと本文の間の区切り線
    y += rule_gap
    d.line([margin, y, margin + int(inner * 0.28), y], fill=theme["accent"], width=5)
    y += rule_to_sub

    for line in slines:
        d.text((margin, y), line, font=sf, fill=theme["fg"])
        y += sub_lh

    # 右下にブランド表記
    bf = _font(int(S * 0.030), "Bold")
    brand = cfg["brand"]
    bw = d.textlength(brand, font=bf)
    d.text((S - margin - bw, S - margin - int(S * 0.030)), brand, font=bf, fill=theme["accent"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Instagram は JPEG のみ受け付ける
    img.save(out_path, "JPEG", quality=92, optimize=True)
    return out_path


if __name__ == "__main__":
    # 単体で動かすとサンプル画像を出す
    samples = [
        {
            "topic_key": "ANA国際線タイムセール",
            "headline": "ANA国際線タイムセール開催",
            "subline": "ハワイ往復が燃油込みで11万円台から",
        },
        {
            "topic_key": "モッピーJAL二重どり",
            "headline": "JALマイルの二重どりが今アツい",
            "subline": "ポイントサイト経由で還元率が跳ね上がる",
        },
        {
            "topic_key": "トクたびマイル",
            "headline": "トクたびマイル今週の対象路線",
            "subline": "東京〜札幌が片道7,500マイルで飛べる",
        },
    ]
    for i, s in enumerate(samples, 1):
        p = render(s, ASSETS / "img" / f"sample_{i}.jpg")
        print("wrote", p)
