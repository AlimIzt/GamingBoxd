import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
from urllib.request import urlopen

from dotenv import load_dotenv


STEAM_COMMUNITY_URL = "https://steamcommunity.com"
STEAM_API_URL = "https://api.steampowered.com"
STEAM_ID64_PATTERN = re.compile(r"^\d{17}$")

load_dotenv()


class SteamImportError(Exception):
    pass


@dataclass
class SteamOwnedGame:
    app_id: int
    name: str
    playtime_minutes: int
    icon_url: str | None = None
    logo_url: str | None = None


def get_api_key() -> str:
    api_key = os.getenv("STEAM_API_KEY", "").strip()
    if not api_key:
        raise SteamImportError("Missing STEAM_API_KEY. Add it to your environment before importing.")
    return api_key


def normalize_profile_input(value: str) -> tuple[str, str]:
    cleaned = value.strip().rstrip("/")
    if not cleaned:
        raise SteamImportError("Enter a Steam profile URL, vanity name, or SteamID64.")

    if STEAM_ID64_PATTERN.fullmatch(cleaned):
        return "steamid", cleaned

    profile_match = re.match(r"^https?://steamcommunity\.com/profiles/(\d{17})/?$", cleaned, re.IGNORECASE)
    if profile_match:
        return "steamid", profile_match.group(1)

    vanity_match = re.match(r"^https?://steamcommunity\.com/id/([^/]+)/?$", cleaned, re.IGNORECASE)
    if vanity_match:
        return "vanity", vanity_match.group(1)

    if "/" in cleaned or " " in cleaned:
        raise SteamImportError("Steam profile input was not recognized.")

    return "vanity", cleaned


def load_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_steam_id(profile_input: str, api_key: str | None = None) -> str:
    kind, value = normalize_profile_input(profile_input)
    if kind == "steamid":
        return value

    key = api_key or get_api_key()
    payload = load_json(
        f"{STEAM_API_URL}/ISteamUser/ResolveVanityURL/v1/?key={quote(key)}&vanityurl={quote(value)}"
    )
    response = payload.get("response", {})
    steam_id = response.get("steamid")
    if response.get("success") != 1 or not steam_id:
        raise SteamImportError("Could not resolve that Steam profile. Check the URL or vanity name.")
    return steam_id


def build_asset_url(app_id: int, hash_value: str | None) -> str | None:
    if not hash_value:
        return None
    return f"https://media.steampowered.com/steamcommunity/public/images/apps/{app_id}/{hash_value}.jpg"


def fetch_owned_games(profile_input: str, api_key: str | None = None) -> list[SteamOwnedGame]:
    key = api_key or get_api_key()
    steam_id = resolve_steam_id(profile_input, key)
    payload = load_json(
        f"{STEAM_API_URL}/IPlayerService/GetOwnedGames/v1/?key={quote(key)}"
        f"&steamid={quote(steam_id)}&include_appinfo=1&include_played_free_games=1"
    )
    response = payload.get("response", {})
    games = response.get("games")
    if games is None:
        raise SteamImportError(
            "Steam returned no library data. The profile may be private or the API key may be invalid."
        )

    mapped_games: list[SteamOwnedGame] = []
    for game in games:
        app_id = int(game["appid"])
        mapped_games.append(
            SteamOwnedGame(
                app_id=app_id,
                name=game.get("name", f"Steam App {app_id}"),
                playtime_minutes=int(game.get("playtime_forever", 0)),
                icon_url=build_asset_url(app_id, game.get("img_icon_url")),
                logo_url=build_asset_url(app_id, game.get("img_logo_url")),
            )
        )
    return mapped_games
