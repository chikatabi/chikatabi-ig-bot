"""テンプレート組版：headline / subline から正方形JPEGを作る。

背景は Pexels の実写。単色背景に文字だけだと、フィード上で他の投稿に
埋もれてスクロールが止まらない。写真が取れなかった日だけ単色に落ちる。

AI画像生成は使わない（理由は photo.py の冒頭に書いた）。
"""
from __future__ import annotations

import hashlib
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageStat

import photo
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


TEXT_TOP = 0.4      # 文字が乗り始めるおおよその高さ（画像の上からの割合）
SCRIM_TOP_RATIO = 0.42   # 上端の濃さは下端の何倍か
SCRIM_CURVE = 1.15       # 1より大きいほど、濃くなるのが下に寄る


def _curve(t: float) -> float:
    """下端を1としたときの、高さ t における暗幕の濃さ。"""
    return SCRIM_TOP_RATIO + (1 - SCRIM_TOP_RATIO) * (t**SCRIM_CURVE)


# 文字が乗る範囲では、暗幕は下端の値より薄い。その平均比をあらかじめ出しておき、
# 必要な濃さを逆算するときに割り戻す。これが無いと明るい写真で暗さが足りない。
_N = 400
_AVG_RATIO = sum(_curve(TEXT_TOP + (1 - TEXT_TOP) * i / (_N - 1)) for i in range(_N)) / _N


def _auto_alpha(img: Image.Image, S: int, target: int) -> int:
    """文字が乗る下半分の明るさを測って、必要なぶんだけ暗幕を掛ける。

    固定値だと、明るい雪景色では文字が消え、元から暗い写真では真っ黒に
    潰れて何が写っているか分からなくなる。実際その両方が起きた。
    """
    lower = img.convert("L").crop((0, int(S * TEXT_TOP), S, S))
    mean = ImageStat.Stat(lower).mean[0]
    if mean <= target:
        # 元から十分暗い。これ以上重ねると写真が消える
        return 70
    return int(min(245, max(70, 255 * (1 - target / mean) / _AVG_RATIO)))


def _scrim(img: Image.Image, S: int, bottom: int) -> Image.Image:
    """写真の上に黒のグラデーションを重ねて、白文字が乗る面を作る。

    上は薄く、下を濃く。文字は下寄せなので、写真は上半分で見せる。
    """
    col = Image.new("L", (1, S))
    for y in range(S):
        col.putpixel((0, y), int(bottom * _curve(y / (S - 1))))
    return Image.composite(Image.new("RGB", (S, S), "#000000"), img, col.resize((S, S)))


def render(post: dict, out_path: Path) -> Path:
    cfg = load_config()
    S = cfg["image"]["size"]
    theme = _theme_for(post["topic_key"], cfg["image"]["themes"])
    ph = cfg["image"].get("photo", {})

    bg, credit = None, ""
    if ph.get("enabled", True):
        got = photo.fetch(post.get("image_query", ""), post["topic_key"], S)
        if got is not None:
            bg, credit = got

    if bg is not None:
        img = _scrim(bg, S, _auto_alpha(bg, S, ph.get("target_luminance", 78)))
        fg, accent = "#FFFFFF", theme["accent"]
    else:
        img = Image.new("RGB", (S, S), theme["bg"])
        fg, accent = theme["fg"], theme["accent"]

    d = ImageDraw.Draw(img)

    margin = int(S * 0.09)
    inner = S - margin * 2

    # 単色のときだけ上部にアクセントバーを置く。
    # 写真のときは文字のすぐ上に引くので、ここでは描かない。
    if bg is None:
        d.rectangle([margin, margin, margin + int(inner * 0.18), margin + 10], fill=accent)

    # 見出し（長さに応じて自動で縮める）
    size = int(S * 0.105)
    while size > int(S * 0.055):
        hf = _font(size, "Bold")
        hlines = _wrap(d, post["headline"], hf, inner)
        # 3行になると最終行に1〜2文字だけ残って見た目が悪い。
        # headline は12〜18文字なので、少し縮めれば2行に収まる。
        if len(hlines) <= 2:
            break
        size -= 6
    head_lh = int(size * 1.38)

    # サブラインも1行に収まるまで縮める。2行になると最終行に1〜2文字だけ残る。
    sub_size = int(S * 0.042)
    while sub_size > int(S * 0.030):
        sf = _font(sub_size, "Medium")
        slines = _wrap(d, post["subline"], sf, inner)
        if len(slines) <= 1:
            break
        sub_size -= 2
    sub_lh = int(sub_size * 1.5)

    rule_gap = int(S * 0.02)
    rule_to_sub = int(S * 0.045)

    block_h = len(hlines) * head_lh + rule_gap + rule_to_sub + len(slines) * sub_lh

    if bg is None:
        # 単色のときは中央。そうしないと文字数が少ない日に下半分がまるごと空く。
        y = (S - block_h) // 2
    else:
        # 写真のときは下寄せ。スクリムが濃いのは下側だし、
        # 中央に置くと写真の主題（山・機体・建物）に文字が重なって両方死ぬ。
        bar_h = int(S * 0.012)
        # 下端はブランド表記のぶん空ける。詰めるとサブラインと重なる。
        y = S - int(S * 0.19) - block_h
        d.rectangle(
            [margin, y - int(S * 0.045), margin + int(inner * 0.18), y - int(S * 0.045) + bar_h],
            fill=accent,
        )

    for line in hlines:
        d.text((margin, y), line, font=hf, fill=fg)
        y += head_lh

    # 見出しと本文の間の区切り線
    y += rule_gap
    d.line([margin, y, margin + int(inner * 0.28), y], fill=accent, width=5)
    y += rule_to_sub

    for line in slines:
        d.text((margin, y), line, font=sf, fill=fg)
        y += sub_lh

    # 右下にブランド表記
    bf = _font(int(S * 0.030), "Bold")
    brand = cfg["brand"]
    bw = d.textlength(brand, font=bf)
    d.text((S - margin - bw, S - margin - int(S * 0.030)), brand, font=bf, fill=accent)

    # 左下に撮影者クレジット。Unsplash は規約で表記が必須。
    # 主役ではないので小さく、白を落として目立たせない。
    if credit:
        cf = _font(int(S * 0.019), "Medium")
        d.text((margin, S - margin - int(S * 0.026)), credit, font=cf, fill="#B8B8B8")

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
            "image_query": "hawaii beach sunset palm",
        },
        {
            "topic_key": "モッピーJAL二重どり",
            "headline": "JALマイルの二重どりが今アツい",
            "subline": "ポイントサイト経由で還元率が跳ね上がる",
            "image_query": "airplane window clouds sunset",
        },
        {
            "topic_key": "トクたびマイル",
            "headline": "トクたびマイル今週の対象路線",
            "subline": "東京〜札幌が片道7,500マイルで飛べる",
            "image_query": "sapporo snow city japan",
        },
    ]
    for i, s in enumerate(samples, 1):
        p = render(s, ASSETS / "img" / f"sample_{i}.jpg")
        print("wrote", p)
