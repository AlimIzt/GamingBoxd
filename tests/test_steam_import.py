import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.main import import_steam_library
from app.models import Game, GameStatus, User, UserGame
from app.steam import SteamOwnedGame, build_asset_url, normalize_profile_input


class SteamImportTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db: Session = TestingSessionLocal()
        self.user = User(username="tester", display_name="Tester", bio="bio")
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self) -> None:
        self.db.close()

    def test_normalize_profile_input_accepts_supported_formats(self) -> None:
        self.assertEqual(normalize_profile_input("76561198000000000"), ("steamid", "76561198000000000"))
        self.assertEqual(
            normalize_profile_input("https://steamcommunity.com/profiles/76561198000000000"),
            ("steamid", "76561198000000000"),
        )
        self.assertEqual(
            normalize_profile_input("https://steamcommunity.com/id/sample-user"),
            ("vanity", "sample-user"),
        )
        self.assertEqual(normalize_profile_input("sample-user"), ("vanity", "sample-user"))

    def test_build_asset_url_returns_expected_cdn_path(self) -> None:
        asset_url = build_asset_url(620, "abc123")
        self.assertEqual(
            asset_url,
            "https://media.steampowered.com/steamcommunity/public/images/apps/620/abc123.jpg",
        )

    def test_import_steam_library_dedupes_repeated_imports(self) -> None:
        games = [
            SteamOwnedGame(
                app_id=620,
                name="Portal 2",
                playtime_minutes=420,
                icon_url="https://cdn.example/icon.jpg",
                logo_url="https://cdn.example/logo.jpg",
            )
        ]

        first_import = import_steam_library(self.db, self.user, games)
        self.db.commit()
        second_import = import_steam_library(self.db, self.user, games)
        self.db.commit()

        self.assertEqual(first_import, 1)
        self.assertEqual(second_import, 0)

        game_count = self.db.query(Game).count()
        log_count = self.db.query(UserGame).count()
        log = self.db.query(UserGame).first()

        self.assertEqual(game_count, 1)
        self.assertEqual(log_count, 1)
        self.assertEqual(log.status, GameStatus.BACKLOG)
        self.assertEqual(log.import_source, "steam")
        self.assertEqual(log.steam_playtime_minutes, 420)


if __name__ == "__main__":
    unittest.main()
