"""One-off helper to obtain a Spotify refresh token via the Authorization
Code flow. Not part of the running app -- run this manually, once, to get
the value for SPOTIFY_REFRESH_TOKEN in your .env.

Usage:
    .venv/Scripts/python.exe scripts/spotify_get_refresh_token.py

You'll need a Client ID and Client Secret from
https://developer.spotify.com/dashboard first (create an app there, add
the redirect URI printed below to the app's settings before running this).
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request

REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "user-read-playback-state user-modify-playback-state user-read-currently-playing"


def main() -> None:
    client_id = input("Client ID: ").strip()
    client_secret = input("Client Secret: ").strip()

    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
    })
    print(f"\n1. Adicione este Redirect URI ao seu app no Spotify Dashboard, se ainda não tiver:\n   {REDIRECT_URI}\n")
    print("2. Abra esta URL no navegador, faça login e autorize:\n")
    print(f"   {auth_url}\n")
    print("3. Você será redirecionado para uma URL que começa com "
          f"{REDIRECT_URI}?code=... (a página não vai carregar, e tudo bem --")
    print("   é só copiar o valor de 'code' da barra de endereço.\n")

    redirected = input("Cole aqui a URL completa para a qual você foi redirecionado (ou só o código): ").strip()
    code = redirected
    if "code=" in redirected:
        code = urllib.parse.parse_qs(urllib.parse.urlparse(redirected).query)["code"][0]

    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        }).encode(),
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        print(f"\nFalhou: HTTP {exc.code} -- {exc.read().decode(errors='replace')}")
        return

    print("\nAdicione isto ao seu .env:\n")
    print(f"SPOTIFY_CLIENT_ID={client_id}")
    print(f"SPOTIFY_CLIENT_SECRET={client_secret}")
    print(f"SPOTIFY_REFRESH_TOKEN={data['refresh_token']}")


if __name__ == "__main__":
    main()
