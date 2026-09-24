"""FastAPI alkalmazás – élő szavazó webapp.

Route-ok:
- Résztvevő: /, /api/state, /api/vote, /events/participant
- Admin (localhost-only): /admin, /admin/api/*, /events/admin
- Élő frissítés: SSE state_version mintával (0,5 mp poll, 15 mp keepalive).
"""

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Literal

import qrcode
import qrcode.image.svg
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from ifaddr import get_adapters
from pydantic import BaseModel, Field

import db

BASE_DIR = Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# LAN IP felderítés (ifaddr)
# --------------------------------------------------------------------------

_EXCLUDED_NAME_PARTS = (
    "utun", "tun", "tap", "wg", "tailscale", "zerotier", "docker",
    "br-", "veth", "vEthernet", "virtualbox", "vmware", "hyper-v", "bridge",
)


def _score(addr: str) -> int:
    if addr.startswith("192.168."):
        return 0
    if addr.startswith("10."):
        return 1
    parts = addr.split(".")
    if len(parts) > 1 and parts[0] == "172" and 16 <= int(parts[1]) <= 31:
        return 2
    return 3


def discover_lan_ip() -> tuple[str | None, list[tuple[str, str]]]:
    candidates: list[tuple[str, str]] = []
    try:
        adapters = get_adapters()
    except Exception:
        return None, []
    for adapter in adapters:
        name = adapter.name or ""
        if any(part in name.lower() for part in _EXCLUDED_NAME_PARTS):
            continue
        for ip in adapter.ips:
            if not ip.is_IPv4:
                continue
            addr = ip.ip
            if addr.startswith("127.") or addr.startswith("169.254."):
                continue
            candidates.append((addr, name))
    if not candidates:
        return None, []
    candidates.sort(key=lambda c: _score(c[0]))
    return candidates[0][0], candidates


def get_lan_ip() -> tuple[str, list[tuple[str, str]]]:
    override = os.environ.get("HOST_IP")
    if override:
        return override, []
    lan_ip, candidates = discover_lan_ip()
    return lan_ip, candidates


LAN_IP, IP_CANDIDATES = get_lan_ip()
LAN_IP = LAN_IP or "127.0.0.1"
VOTER_URL = f"http://{LAN_IP}:8000/"
ADMIN_URL = "http://localhost:8000/admin"

# --------------------------------------------------------------------------
# Alkalmazás, sablonok, statikus fájlok
# --------------------------------------------------------------------------

app = FastAPI(title="Élő szavazás")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

db.init_db()

# --------------------------------------------------------------------------
# Élő frissítés: state_version mintája
# --------------------------------------------------------------------------

state_version = 0
_state_lock = asyncio.Lock()


def bump_state() -> None:
    global state_version
    state_version += 1


# --------------------------------------------------------------------------
# Admin localhost-gárd + voter_id cookie
# --------------------------------------------------------------------------

_LOCALHOSTS = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}
VOTER_COOKIE = "voter_id"
VOTER_COOKIE_MAX_AGE = 30 * 24 * 3600  # ~30 nap


def require_localhost(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in _LOCALHOSTS:
        raise HTTPException(status_code=403, detail="Az admin felület csak a host gépről (localhost) érhető el.")


def get_voter_id(request: Request) -> str:
    vid = request.cookies.get(VOTER_COOKIE)
    return vid or str(uuid.uuid4())


def _set_voter_cookie(response: Response, voter_id: str) -> None:
    response.set_cookie(
        VOTER_COOKIE,
        voter_id,
        max_age=VOTER_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


def make_qr_svg(url: str) -> str:
    qr = qrcode.QRCode(border=2, box_size=12)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    return img.to_string().decode()


# --------------------------------------------------------------------------
# Request modellek (validálás backend)
# --------------------------------------------------------------------------

class QuestionIn(BaseModel):
    text: str
    type: Literal["single", "multi"]
    options: list[str]


class VoteIn(BaseModel):
    option_ids: list[int] = Field(min_length=1)


def validate_question(payload: QuestionIn) -> tuple[str, str, list[str]]:
    text = payload.text.strip()
    if not 1 <= len(text) <= 300:
        raise HTTPException(400, "A kérdés szövege 1–300 karakter lehet.")
    options = [o.strip() for o in payload.options]
    options = [o for o in options if o]
    if not 2 <= len(options) <= 8:
        raise HTTPException(400, "2–8 válaszlehetőséget adj meg.")
    for o in options:
        if len(o) > 300:
            raise HTTPException(400, "Egy válaszlehetőség legfeljebb 300 karakter lehet.")
    if len(set(options)) != len(options):
        raise HTTPException(400, "A válaszlehetőségek nem ismétlődhetnek.")
    return text, payload.type, options


# --------------------------------------------------------------------------
# Résztvevői route-ok
# --------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def voter_page(request: Request) -> HTMLResponse:
    """Résztvevői oldal; beállítja a voter_id cookie-t, ha még nincs."""
    voter_id = get_voter_id(request)
    resp = templates.TemplateResponse(request, "voter.html", {})
    _set_voter_cookie(resp, voter_id)
    return resp


@app.get("/api/state")
def voter_state(request: Request) -> JSONResponse:
    """Aktív kérdés + opciók + szavazott-e már ez a voter."""
    voter_id = get_voter_id(request)
    active = db.get_active_question()
    voted = db.has_voted(active["id"], voter_id) if active else False
    resp = JSONResponse(
        {"version": state_version, "active_question": active, "voted": voted}
    )
    _set_voter_cookie(resp, voter_id)
    return resp


@app.post("/api/vote")
def vote(request: Request, payload: VoteIn) -> JSONResponse:
    """Szavazat beküldése; duplikátum -> 409, egyéb hiba -> 4xx."""
    voter_id = get_voter_id(request)
    active = db.get_active_question()
    if active is None:
        raise HTTPException(400, "Jelenleg nincs aktív kérdés, nem lehet szavazni.")
    try:
        db.submit_vote(active["id"], voter_id, payload.option_ids)
    except db.AlreadyVotedError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except db.InvalidVoteError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    bump_state()
    resp = JSONResponse({"ok": True, "question_id": active["id"], "voted": True})
    _set_voter_cookie(resp, voter_id)
    return resp


# --------------------------------------------------------------------------
# Admin route-ok (localhost-only)
# --------------------------------------------------------------------------

@app.get("/admin", response_class=HTMLResponse, dependencies=[Depends(require_localhost)])
def admin_page(request: Request) -> HTMLResponse:
    qr_svg = make_qr_svg(VOTER_URL)
    return templates.TemplateResponse(
        request,
        "admin.html",
        {"voter_url": VOTER_URL, "qr_svg": qr_svg, "admin_url": ADMIN_URL},
    )


@app.get("/admin/api/questions", dependencies=[Depends(require_localhost)])
def admin_questions() -> dict:
    return {"version": state_version, "questions": db.list_questions()}


@app.post("/admin/api/questions", status_code=201, dependencies=[Depends(require_localhost)])
def admin_create_question(payload: QuestionIn) -> dict:
    text, qtype, options = validate_question(payload)
    qid = db.create_question(text, qtype, options)
    bump_state()
    return {"id": qid}


@app.post("/admin/api/questions/{question_id}/publish", dependencies=[Depends(require_localhost)])
def admin_publish(question_id: int) -> dict:
    if not db.publish_question(question_id):
        raise HTTPException(404, "Nincs ilyen kérdés.")
    bump_state()
    return {"ok": True, "active_question_id": question_id}


@app.post("/admin/api/reset", dependencies=[Depends(require_localhost)])
def admin_reset() -> dict:
    db.reset_all()
    bump_state()
    return {"ok": True}


# --------------------------------------------------------------------------
# SSE stream-ek
# --------------------------------------------------------------------------

async def _event_stream(request: Request, is_admin: bool, voter_id: str | None):
    """Polling a state_version-számlálón: 0,5 mp-ként, 15 mp-enként keepalive."""
    last: int = -1
    elapsed = 0.0
    while True:
        if await request.is_disconnected():
            break
        await asyncio.sleep(0.5)
        elapsed += 0.5
        if state_version != last:
            last = state_version
            if is_admin:
                data = {"version": last, "questions": db.list_questions()}
            else:
                active = db.get_active_question()
                voted = db.has_voted(active["id"], voter_id) if active and voter_id else False
                data = {"version": last, "active_question": active, "voted": voted}
            yield f"event: state\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            elapsed = 0.0
        elif elapsed >= 15.0:
            yield ": ping\n\n"
            elapsed = 0.0


def _sse_headers() -> dict[str, str]:
    return {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@app.get("/events/admin", dependencies=[Depends(require_localhost)])
async def admin_events(request: Request) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(request, is_admin=True, voter_id=None),
        media_type="text/event-stream",
        headers=_sse_headers(),
    )


@app.get("/events/participant")
async def participant_events(request: Request) -> StreamingResponse:
    voter_id = get_voter_id(request)
    resp = StreamingResponse(
        _event_stream(request, is_admin=False, voter_id=voter_id),
        media_type="text/event-stream",
        headers=_sse_headers(),
    )
    _set_voter_cookie(resp, voter_id)
    return resp