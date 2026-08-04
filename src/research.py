"""ネタのリサーチ：RSS と Google ニュースを巡回して候補を集める。

死んでいるフィードがあっても止まらない。warn を出して次へ進む。
note のハッシュタグRSSは個人の日記が大量に流れてくるため、
sources.yaml の strict:true と config.yaml の relevance_keywords で絞り込む。
"""
from __future__ import annotations

import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from common import load_config, load_sources

UA = "Mozilla/5.0 (compatible; chikatabi-ig-bot/1.0)"
JST = timezone(timedelta(hours=9))


def _gnews_url(query: str) -> str:
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _entry_dt(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc).astimezone(JST)
    return None


def _title_key(title: str) -> str:
    """同じ話題が複数ソースから流れてくるのを潰すための正規化キー。

    Google ニュースは「見出し - 媒体名」形式なので媒体名を落とし、
    記号・空白・全角半角ゆれを除いた先頭30文字で比較する。
    """
    t = re.split(r"\s+[-–—|]\s+", title)[0]
    t = re.sub(r"[\s　【】\[\]（）()「」『』、。,.!！?？〜~・:：/]", "", t)
    return t[:30]


def _score(item: dict, keywords: list[str]) -> int:
    """タイトル＋要約に含まれるキーワード数。多いほど「お得な旅」らしい。"""
    blob = f"{item['title']} {item['summary']}"
    return sum(1 for kw in keywords if kw in blob)


def fetch_source(src: dict, cutoff: datetime, keywords: list[str]) -> list[dict]:
    url = src["url"] if src["type"] == "rss" else _gnews_url(src["query"])
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": UA})
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001 — どのフィードが落ちても全体は続行する
        print(f"  warn: {src['name']} を取得できませんでした ({e})", file=sys.stderr)
        return []

    feed = feedparser.parse(resp.content)
    out = []
    for entry in feed.entries:
        dt = _entry_dt(entry)
        if dt and dt < cutoff:
            continue
        title = _clean(entry.get("title", ""))
        if not title:
            continue
        item = {
            "source": src["name"],
            "title": title,
            "url": entry.get("link", ""),
            "summary": _clean(entry.get("summary", ""))[:400],
            "published": dt.isoformat() if dt else "",
        }
        item["score"] = _score(item, keywords)
        if src.get("strict") and item["score"] == 0:
            continue
        out.append(item)

    # スコアの高い順 → 新しい順。そのうえでソースごとの上限で切る。
    out.sort(key=lambda x: (x["score"], x["published"]), reverse=True)
    out = out[: src.get("limit", 10)]
    print(f"  {src['name']}: {len(out)}件")
    return out


def collect() -> list[dict]:
    cfg = load_config()
    keywords = cfg.get("relevance_keywords", [])
    cutoff = datetime.now(JST) - timedelta(days=cfg["lookback_days"])
    print(f"リサーチ開始（{cutoff:%Y-%m-%d} 以降の記事）")

    items: list[dict] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for src in load_sources():
        for item in fetch_source(src, cutoff, keywords):
            if item["url"] and item["url"] in seen_urls:
                continue
            key = _title_key(item["title"])
            if key in seen_titles:
                continue  # 同じ話題が別ソースから来ている
            seen_urls.add(item["url"])
            seen_titles.add(key)
            items.append(item)

    items.sort(key=lambda x: (x["score"], x["published"]), reverse=True)
    items = items[: cfg["max_candidates"]]
    print(f"候補 {len(items)}件")
    return items


if __name__ == "__main__":
    for it in collect():
        print(f"  [{it['score']}] [{it['source']}] {it['title']}")
