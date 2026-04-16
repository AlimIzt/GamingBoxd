# Gaming Letterboxd

A small Letterboxd-style diary for games built with FastAPI, Jinja2, SQLAlchemy, and SQLite.

## Features

- Log games with title, platform, genre, status, rating, review, and played date
- Import owned games from Steam with a profile URL, vanity name, or `SteamID64`
- Edit and delete diary entries
- Filter by play status and sort by title, rating, or date
- Profile-style dashboard with quick stats
- Deduplicate repeated Steam imports while preserving handwritten reviews and ratings
- Dark, poster-inspired UI for screenshots and portfolio use

## Stack

- `FastAPI`
- `SQLAlchemy`
- `SQLite`
- `Jinja2`
- Plain CSS

## Run locally

1. Create a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Configure Steam import:

```powershell
Copy-Item .env.example .env
$env:STEAM_API_KEY="your-steam-web-api-key"
```

If you prefer, you can also set `STEAM_API_KEY` permanently in your shell or system environment. The Steam library must be visible enough for the Web API to return owned games.

Accepted Steam inputs:
- `https://steamcommunity.com/id/yourname`
- `https://steamcommunity.com/profiles/7656119...`
- `7656119...`
- `your-vanity-name`

4. Start the dev server:

```powershell
uvicorn app.main:app --reload
```

5. Open [http://127.0.0.1:8000](http://127.0.0.1:8000)

## MVP Notes

- Uses a seeded demo profile called `Player One`
- Stores data locally in `games.db`
- Supports Steam-powered backlog importing without overwriting your manual notes
- Designed to be easy to extend with auth, custom lists, and richer metadata later

## Deploy On Render

This project is prepared for [Render](https://render.com/) with `render.yaml`.

Important deployment note:
- Do not use local SQLite on Render for production-like hosting
- Set `DATABASE_URL` to a managed Postgres database
- Set `STEAM_API_KEY` in the Render dashboard before using Steam imports

Recommended Render setup:
1. Create a new Web Service from this GitHub repo.
2. Let Render detect `render.yaml`.
3. Add a Postgres database and copy its connection string into `DATABASE_URL`.
4. Add `STEAM_API_KEY` as an environment variable.
5. Deploy and open the generated Render URL.

The app automatically:
- uses `DATABASE_URL` when present
- falls back to local `games.db` for local development
- normalizes Render-style Postgres URLs for SQLAlchemy

## Tests

Run the focused import tests with:

```powershell
python -m unittest discover -s tests -v
```

## Screenshot Ideas

- Dashboard with stats and filters visible
- Steam import card filled with a profile URL and success state visible
- Add-game form filled out with a sample review
- Mixed library showing backlog, playing, and completed states
