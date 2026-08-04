"""共通のパス・設定読み込み。他のモジュールはここから import する。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
DATA = ROOT / "data"
QUEUE = DATA / "queue"
DRAFTS = ROOT / "drafts"
POSTED = DATA / "posted.tsv"
FONT = ASSETS / "fonts" / "NotoSansJP-VF.ttf"

for d in (DATA, QUEUE, DRAFTS, ASSETS / "img"):
    d.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sources() -> list[dict]:
    with open(ROOT / "sources.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def env(name: str, required: bool = True) -> str:
    """GitHub Secrets から渡ってくる値を読む。"""
    v = os.environ.get(name, "").strip()
    if required and not v:
        raise SystemExit(
            f"環境変数 {name} が設定されていません。"
            f"GitHub の Settings → Secrets and variables → Actions を確認してください。"
        )
    return v


def read_queue(date: str) -> dict | None:
    p = QUEUE / f"{date}.json"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_queue(date: str, payload: dict) -> Path:
    p = QUEUE / f"{date}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return p
