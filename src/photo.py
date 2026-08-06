"""背景写真を Pexels から取ってくる。

AI画像生成は使わない。実在するキャンペーンや制度変更の話に実在しない絵を
添えると、情報の正確さで信用を取りにいくアカウントの足を引っ張るため。
Pexels は商用利用可・帰属表示不要で、1日2枚なら無料枠で足りる。

写真が取れなくても投稿は止めない。失敗したら None を返し、render 側が
単色背景にフォールバックする（毎朝のバッチを写真1枚で落とさないため）。
"""
from __future__ import annotations

import hashlib
import io
import os

import requests
from PIL import Image

SEARCH_URL = "https://api.pexels.com/v1/search"
TIMEOUT = 20


def _pick(photos: list[dict], seed: str) -> dict:
    """同じネタなら毎回同じ写真になるよう、キーから決定的に選ぶ。

    ランダムだと再実行のたびに絵が変わり、承認済みの投稿と実際に出る絵が
    ずれる。同じ日の2投稿で同じ写真になるのも topic_key が違うので防げる。
    """
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    return photos[h % len(photos)]


def _cover(img: Image.Image, size: int) -> Image.Image:
    """正方形に「切り抜いて埋める」。縦横比を崩さない。"""
    w, h = img.size
    scale = max(size / w, size / h)
    nw, nh = int(w * scale + 0.5), int(h * scale + 0.5)
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - size) // 2, (nh - size) // 2
    return img.crop((left, top, left + size, top + size))


def fetch(query: str, seed: str, size: int) -> Image.Image | None:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        print("  PEXELS_API_KEY が無いため単色背景にします")
        return None
    if not query:
        return None

    try:
        r = requests.get(
            SEARCH_URL,
            headers={"Authorization": key},
            params={"query": query, "orientation": "square", "per_page": 15},
            timeout=TIMEOUT,
        )
        if not r.ok:
            print(f"  Pexels検索に失敗（{r.status_code}）。単色背景にします")
            return None

        photos = r.json().get("photos", [])
        if not photos:
            print(f"  『{query}』に合う写真が見つかりません。単色背景にします")
            return None

        chosen = _pick(photos, seed)
        src = chosen["src"].get("large2x") or chosen["src"]["large"]
        blob = requests.get(src, timeout=TIMEOUT)
        blob.raise_for_status()

        img = Image.open(io.BytesIO(blob.content)).convert("RGB")
        print(f"  写真: {query} → {chosen.get('photographer', '?')}")
        return _cover(img, size)

    except Exception as e:  # noqa: BLE001 — 写真が無くても投稿は作る
        print(f"  写真の取得に失敗（{type(e).__name__}）。単色背景にします")
        return None
