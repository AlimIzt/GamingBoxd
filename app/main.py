from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session, joinedload

from app.db import Base, engine, get_db
from app.models import Game, GameStatus, User, UserGame
from app.steam import SteamImportError, SteamOwnedGame, fetch_owned_games


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Gaming Letterboxd")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def seed_demo_user(db: Session) -> User:
    user = db.query(User).filter(User.username == "player-one").first()
    if user:
        return user

    user = User(
        username="player-one",
        display_name="Player One",
        bio="Cataloguing comfort games, giant boss fights, and the backlog that never ends.",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_current_user(db: Session) -> User:
    return seed_demo_user(db)


def ensure_legacy_schema() -> None:
    inspector = inspect(engine)
    game_columns = {column["name"] for column in inspector.get_columns("games")}
    user_game_columns = {column["name"] for column in inspector.get_columns("user_games")}

    statements: list[str] = []
    if "steam_app_id" not in game_columns:
        statements.append("ALTER TABLE games ADD COLUMN steam_app_id INTEGER")
    if "steam_icon_url" not in game_columns:
        statements.append("ALTER TABLE games ADD COLUMN steam_icon_url VARCHAR(255)")
    if "steam_logo_url" not in game_columns:
        statements.append("ALTER TABLE games ADD COLUMN steam_logo_url VARCHAR(255)")
    if "import_source" not in user_game_columns:
        statements.append("ALTER TABLE user_games ADD COLUMN import_source VARCHAR(50)")
    if "steam_playtime_minutes" not in user_game_columns:
        statements.append("ALTER TABLE user_games ADD COLUMN steam_playtime_minutes INTEGER")

    if statements:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_legacy_schema()
    with Session(engine) as db:
        seed_demo_user(db)


def normalize_rating(raw_rating: str | None) -> float | None:
    if not raw_rating:
        return None

    try:
        rating = float(raw_rating)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Rating must be a number.") from exc

    if rating < 0 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 0 and 5.")
    return rating


def parse_played_on(raw_date: str | None):
    if not raw_date:
        return None
    try:
        return datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Played date must use YYYY-MM-DD.") from exc


def parse_optional_played_on(raw_date: str | None) -> date | None:
    return parse_played_on(raw_date)


def parse_status(raw_status: str) -> GameStatus:
    try:
        return GameStatus(raw_status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid game status.") from exc


def get_dashboard_stats(db: Session, user: User) -> dict[str, float | int]:
    total_logged = db.query(func.count(UserGame.id)).filter(UserGame.user_id == user.id).scalar() or 0
    completed_count = (
        db.query(func.count(UserGame.id))
        .filter(UserGame.user_id == user.id, UserGame.status == GameStatus.COMPLETED)
        .scalar()
        or 0
    )
    backlog_count = (
        db.query(func.count(UserGame.id))
        .filter(UserGame.user_id == user.id, UserGame.status == GameStatus.BACKLOG)
        .scalar()
        or 0
    )
    average_rating = (
        db.query(func.avg(UserGame.rating))
        .filter(UserGame.user_id == user.id, UserGame.rating.isnot(None))
        .scalar()
    )
    return {
        "total_logged": total_logged,
        "completed_count": completed_count,
        "backlog_count": backlog_count,
        "average_rating": round(float(average_rating), 1) if average_rating is not None else 0,
    }


def get_existing_game(db: Session, title: str, platform: str, steam_app_id: int | None) -> Game | None:
    if steam_app_id is not None:
        game = db.query(Game).filter(Game.steam_app_id == steam_app_id).first()
        if game:
            return game

    return (
        db.query(Game)
        .filter(
            func.lower(Game.title) == title.lower(),
            func.lower(Game.platform) == platform.lower(),
            Game.steam_app_id.is_(None),
        )
        .first()
    )


def upsert_game_log(
    db: Session,
    user: User,
    *,
    title: str,
    platform: str,
    genre: str | None = None,
    status_value: GameStatus,
    rating: float | None = None,
    review: str | None = None,
    played_on: date | None = None,
    steam_app_id: int | None = None,
    steam_icon_url: str | None = None,
    steam_logo_url: str | None = None,
    import_source: str | None = None,
    steam_playtime_minutes: int | None = None,
) -> tuple[UserGame, bool]:
    game = get_existing_game(db, title=title, platform=platform, steam_app_id=steam_app_id)
    if not game:
        game = Game(
            title=title,
            platform=platform,
            genre=genre,
            steam_app_id=steam_app_id,
            steam_icon_url=steam_icon_url,
            steam_logo_url=steam_logo_url,
        )
        db.add(game)
        db.flush()
    else:
        game.title = title
        game.platform = platform
        game.genre = genre
        game.steam_app_id = steam_app_id
        game.steam_icon_url = steam_icon_url or game.steam_icon_url
        game.steam_logo_url = steam_logo_url or game.steam_logo_url

    existing_log = (
        db.query(UserGame)
        .filter(UserGame.user_id == user.id, UserGame.game_id == game.id)
        .first()
    )
    if existing_log:
        if steam_playtime_minutes is not None:
            existing_log.steam_playtime_minutes = steam_playtime_minutes
        if import_source and not existing_log.import_source:
            existing_log.import_source = import_source
        return existing_log, False

    log = UserGame(
        user_id=user.id,
        game_id=game.id,
        status=status_value,
        rating=rating,
        review=review,
        played_on=played_on,
        import_source=import_source,
        steam_playtime_minutes=steam_playtime_minutes,
    )
    db.add(log)
    db.flush()
    return log, True


def get_sorted_logs(
    db: Session,
    user: User,
    status_filter: str | None,
    sort: str,
) -> list[UserGame]:
    query = (
        db.query(UserGame)
        .options(joinedload(UserGame.game))
        .filter(UserGame.user_id == user.id)
    )

    if status_filter:
        query = query.filter(UserGame.status == parse_status(status_filter))

    sort_options = {
        "recent": UserGame.updated_at.desc(),
        "title": Game.title.asc(),
        "rating": UserGame.rating.desc().nullslast(),
        "played_on": UserGame.played_on.desc().nullslast(),
    }
    sort_column = sort_options.get(sort, UserGame.updated_at.desc())

    if sort == "title":
        query = query.join(UserGame.game)

    return query.order_by(sort_column).all()


def get_log_or_404(db: Session, log_id: int, user: User) -> UserGame:
    log = (
        db.query(UserGame)
        .options(joinedload(UserGame.game))
        .filter(UserGame.id == log_id, UserGame.user_id == user.id)
        .first()
    )
    if not log:
        raise HTTPException(status_code=404, detail="Game log not found.")
    return log


@app.get("/")
def home(
    request: Request,
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    sort: str = Query(default="recent"),
    flash_message: str | None = Query(default=None, alias="message"),
    flash_kind: str = Query(default="success", alias="kind"),
):
    user = get_current_user(db)
    logs = get_sorted_logs(db, user, status_filter, sort)
    stats = get_dashboard_stats(db, user)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "logs": logs,
            "stats": stats,
            "current_status": status_filter,
            "current_sort": sort,
            "statuses": list(GameStatus),
            "flash_message": flash_message,
            "flash_kind": flash_kind,
        },
    )


@app.get("/games/new")
def new_game_form(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="game_form.html",
        context={
            "title": "Log a game",
            "submit_label": "Add to diary",
            "statuses": list(GameStatus),
            "game_log": None,
        },
    )


@app.post("/games")
def create_game_log(
    db: Session = Depends(get_db),
    title: str = Form(...),
    platform: str = Form(...),
    genre: str = Form(default=""),
    status_value: str = Form(..., alias="status"),
    rating: str = Form(default=""),
    review: str = Form(default=""),
    played_on: str = Form(default=""),
):
    user = get_current_user(db)
    upsert_game_log(
        db,
        user,
        title=title.strip(),
        platform=platform.strip(),
        genre=genre.strip() or None,
        status=parse_status(status_value),
        rating=normalize_rating(rating),
        review=review.strip() or None,
        played_on=parse_optional_played_on(played_on),
    )
    db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/games/{log_id}/edit")
def edit_game_form(log_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(db)
    game_log = get_log_or_404(db, log_id, user)
    return templates.TemplateResponse(
        request=request,
        name="game_form.html",
        context={
            "title": "Edit entry",
            "submit_label": "Save changes",
            "statuses": list(GameStatus),
            "game_log": game_log,
        },
    )


@app.post("/games/{log_id}/edit")
def update_game_log(
    log_id: int,
    db: Session = Depends(get_db),
    title: str = Form(...),
    platform: str = Form(...),
    genre: str = Form(default=""),
    status_value: str = Form(..., alias="status"),
    rating: str = Form(default=""),
    review: str = Form(default=""),
    played_on: str = Form(default=""),
):
    user = get_current_user(db)
    log = get_log_or_404(db, log_id, user)

    log.game.title = title.strip()
    log.game.platform = platform.strip()
    log.game.genre = genre.strip() or None
    log.status = parse_status(status_value)
    log.rating = normalize_rating(rating)
    log.review = review.strip() or None
    log.played_on = parse_optional_played_on(played_on)

    db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/imports/steam")
def import_steam_games(
    db: Session = Depends(get_db),
    profile_input: str = Form(...),
):
    user = get_current_user(db)
    try:
        steam_games = fetch_owned_games(profile_input)
    except SteamImportError as exc:
        return RedirectResponse(
            url=f"/?kind=error&message={quote_plus(str(exc))}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception:
        return RedirectResponse(
            url="/?kind=error&message=Steam%20import%20failed.%20Try%20again%20in%20a%20moment.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    imported_count = import_steam_library(db, user, steam_games)
    db.commit()
    return RedirectResponse(
        url=f"/?kind=success&message=Imported%20{imported_count}%20new%20games%20from%20Steam.",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def import_steam_library(db: Session, user: User, steam_games: list[SteamOwnedGame]) -> int:
    imported_count = 0
    for steam_game in steam_games:
        _, created = upsert_game_log(
            db,
            user,
            title=steam_game.name,
            platform="Steam",
            status_value=GameStatus.BACKLOG,
            steam_app_id=steam_game.app_id,
            steam_icon_url=steam_game.icon_url,
            steam_logo_url=steam_game.logo_url,
            import_source="steam",
            steam_playtime_minutes=steam_game.playtime_minutes,
        )
        if created:
            imported_count += 1
    return imported_count


@app.post("/games/{log_id}/delete")
def delete_game_log(log_id: int, db: Session = Depends(get_db)):
    user = get_current_user(db)
    log = get_log_or_404(db, log_id, user)
    game_id = log.game_id
    db.delete(log)
    db.flush()
    remaining_logs = db.query(func.count(UserGame.id)).filter(UserGame.game_id == game_id).scalar() or 0
    if remaining_logs == 0:
        game = db.query(Game).filter(Game.id == game_id).first()
        if game:
            db.delete(game)
    db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
