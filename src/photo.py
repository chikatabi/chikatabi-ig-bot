"""背景写真を取ってくる。取得元は2つ。

1. Pexels  … PEXELS_API_KEY があれば優先。写真の質が最も高い
2. Wikimedia Commons … キー不要。アカウント登録なしで今すぐ動く

Commons は パブリックドメイン / CC0 のものだけ使う。CC BY-SA は
「文字を乗せた投稿画像」も同じライセンスで公開する義務が生じるおそれがあり、
商用のブランドアカウントでは扱いが面倒なため、最初から除外する。
PD/CC0 ならクレジット表記も不要で、投稿画像に何も足さなくてよい。

AI画像生成は使わない。実在するキャンペーンや制度変更の話に実在しない絵を
添えると、情報の正確さで信用を取りにいくアカウントの足を引っ張るため。

写真が取れなくても投稿は止めない。失敗したら None を返し、render 側が
単色背景にフォールバックする（毎朝のバッチを写真1枚で落とさないため）。
"""
from __future__ import annotations

import hashlib
import io
import os

import requests
from PIL import Image

PEXELS_URL = "https://api.pexels.com/v1/search"
COMMONS_URL = "https://commons.wikimedia.org/w/api.php"
# Wikimedia は素性の分かる User-Agent を要求する。無いと弾かれることがある。
UA = "chikatabi-ig-bot/1.0 (https://github.com/chikatabi/chikatabi-ig-bot)"
FREE_LICENSES = ("public domain", "cc0")
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


def _download(url: str, size: int) -> Image.Image:
    blob = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    blob.raise_for_status()
    return _cover(Image.open(io.BytesIO(blob.content)).convert("RGB"), size)


def _from_pexels(query: str, seed: str, size: int, key: str) -> Image.Image | None:
    r = requests.get(
        PEXELS_URL,
        headers={"Authorization": key},
        params={"query": query, "orientation": "square", "per_page": 15},
        timeout=TIMEOUT,
    )
    if not r.ok:
        print(f"  Pexels検索に失敗（{r.status_code}）")
        return None

    photos = r.json().get("photos", [])
    if not photos:
        return None

    chosen = _pick(photos, seed)
    img = _download(chosen["src"].get("large2x") or chosen["src"]["large"], size)
    print(f"  写真[Pexels]: {query} → {chosen.get('photographer', '?')}")
    return img


def _from_commons(query: str, seed: str, size: int) -> Image.Image | None:
    r = requests.get(
        COMMONS_URL,
        headers={"User-Agent": UA},
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            # bitmap に限定しないと図表・地図・SVGが大量に混ざる
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrnamespace": 6,          # 6 = ファイル名前空間
            "gsrlimit": 50,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": 1600,
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()

    free = []
    for p in r.json().get("query", {}).get("pages", {}).values():
        info = p.get("imageinfo", [{}])[0]
        lic = (info.get("extmetadata", {}).get("LicenseShortName", {}).get("value") or "").lower()
        if any(f in lic for f in FREE_LICENSES) and info.get("thumburl"):
            free.append((p.get("title", ""), info["thumburl"]))

    if not free:
        print(f"  『{query}』に PD/CC0 の写真がありません")
        return None

    title, url = _pick(free, seed)
    img = _download(url, size)
    print(f"  写真[Commons]: {query} → {title[5:60]}")
    return img


def fetch(query: str, seed: str, size: int) -> Image.Image | None:
    if not query:
        return None

    key = os.environ.get("PEXELS_API_KEY", "").strip()
    sources = [("Pexels", lambda: _from_pexels(query, seed, size, key))] if key else []
    sources.append(("Commons", lambda: _from_commons(query, seed, size)))

    for name, get in sources:
        try:
            img = get()
            if img is not None:
                return img
        except Exception as e:  # noqa: BLE001 — 写真が無くても投稿は作る
            print(f"  {name} の取得に失敗（{type(e).__name__}）")

    print("  写真が取れなかったので単色背景にします")
    return None
