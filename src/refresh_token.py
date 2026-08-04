"""Instagram の長期トークンを延長する。

長期トークンは60日で失効する。24時間以上経過していれば延長でき、
延長するたびに「その時点から60日」に戻る。これを月1回まわしておけば
実質無期限で動き続ける。逆にこれを止めると、2ヶ月後に無言で止まる。

新しいトークンは GitHub Secrets に書き戻す（要 GH_PAT）。
"""
from __future__ import annotations

import base64

import requests
from nacl import encoding, public

from common import env
import notify

REFRESH_URL = "https://graph.instagram.com/refresh_access_token"


def refresh(token: str) -> tuple[str, int]:
    r = requests.get(
        REFRESH_URL,
        params={"grant_type": "ig_refresh_token", "access_token": token},
        timeout=30,
    )
    if not r.ok:
        raise SystemExit(f"トークン延長に失敗: {r.status_code} {r.text}")
    data = r.json()
    return data["access_token"], data.get("expires_in", 0)


def update_secret(repo: str, pat: str, name: str, value: str) -> None:
    """GitHub Secrets は公開鍵で暗号化してから送る決まりになっている。"""
    h = {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json"}

    r = requests.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key", headers=h, timeout=30)
    r.raise_for_status()
    key = r.json()

    sealed = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder()))
    encrypted = base64.b64encode(sealed.encrypt(value.encode())).decode()

    r = requests.put(
        f"https://api.github.com/repos/{repo}/actions/secrets/{name}",
        headers=h,
        json={"encrypted_value": encrypted, "key_id": key["key_id"]},
        timeout=30,
    )
    if r.status_code not in (201, 204):
        raise SystemExit(f"Secret の更新に失敗: {r.status_code} {r.text}")
    print(f"Secret {name} を更新しました")


def main() -> None:
    token = env("IG_ACCESS_TOKEN")
    repo = env("GITHUB_REPOSITORY")
    pat = env("GH_PAT")

    new_token, expires_in = refresh(token)
    days = expires_in // 86400
    update_secret(repo, pat, "IG_ACCESS_TOKEN", new_token)
    print(f"あと約{days}日有効なトークンに更新しました")

    # 30日を切っていたら異常。気づけるように知らせる。
    if days < 30:
        notify.send_text(f"【Instagram bot】トークンの残り日数が{days}日です。確認してください。")


if __name__ == "__main__":
    main()
