from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sentinel_shared.auth import Role, create_access_token, decode_token
from sentinel_shared.config import CommonSettings, get_common_settings
from sentinel_shared.logging import get_logger, get_request_id
from sentinel_shared.schemas.feedback import FeedbackLabel
from sentinel_shared.utils.fastapi import build_app

logger = get_logger(__name__)
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
app = build_app(get_common_settings())


def _token_from_cookie(request: Request) -> str | None:
    return request.cookies.get("sentinel_token")


async def _claims_or_none(request: Request) -> dict | None:
    token = _token_from_cookie(request)
    if not token:
        return None
    try:
        claims = decode_token(token, get_common_settings())
    except HTTPException:
        return None
    return claims.model_dump()


async def _api_get(path: str, token: str, base_url: str) -> dict | list:
    request_id = get_request_id()
    headers = {"Authorization": f"Bearer {token}"}
    if request_id:
        headers["X-Request-ID"] = request_id
    async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
        response = await client.get(path, headers=headers)
        response.raise_for_status()
        return response.json()


async def _api_post(path: str, token: str, base_url: str, payload: dict) -> dict:
    request_id = get_request_id()
    headers = {"Authorization": f"Bearer {token}"}
    if request_id:
        headers["X-Request-ID"] = request_id
    async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
        response = await client.post(
            path,
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()


@app.get("/", response_class=HTMLResponse, response_model=None)
async def home(request: Request) -> HTMLResponse | RedirectResponse:
    claims = await _claims_or_none(request)
    if claims is None:
        return RedirectResponse(url="/login", status_code=302)
    token = _token_from_cookie(request)
    decisions = await _api_get(
        "/v1/decisions?limit=25", token, get_common_settings().decision_service_url
    )
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "claims": claims,
            "decisions": decisions,
            "labels": [label.value for label in FeedbackLabel],
            "generated_at": datetime.now(tz=UTC),
        },
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse, response_model=None)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
) -> HTMLResponse | RedirectResponse:
    settings: CommonSettings = get_common_settings()
    if password != settings.analyst_console_password:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid credentials"},
        )
    selected_role = Role.ADMIN if role == Role.ADMIN else Role.ANALYST
    token = create_access_token(username, selected_role, settings)
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie("sentinel_token", token, httponly=True, samesite="lax")
    return response


@app.post("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("sentinel_token")
    return response


@app.get("/decisions/{decision_id}", response_class=HTMLResponse, response_model=None)
async def decision_detail(request: Request, decision_id: str) -> HTMLResponse | RedirectResponse:
    claims = await _claims_or_none(request)
    if claims is None:
        return RedirectResponse(url="/login", status_code=302)
    token = _token_from_cookie(request)
    settings = get_common_settings()
    decision = await _api_get(f"/v1/decisions/{decision_id}", token, settings.decision_service_url)
    feedback = await _api_get(
        f"/v1/feedback/decisions/{decision_id}", token, settings.feedback_service_url
    )
    return templates.TemplateResponse(
        "decision_detail.html",
        {
            "request": request,
            "claims": claims,
            "decision": decision,
            "feedback": feedback,
            "labels": [label.value for label in FeedbackLabel],
        },
    )


@app.post("/decisions/{decision_id}/feedback")
async def submit_feedback(
    request: Request,
    decision_id: str,
    label: str = Form(...),
    notes: str = Form(""),
) -> RedirectResponse:
    claims = await _claims_or_none(request)
    if claims is None:
        return RedirectResponse(url="/login", status_code=302)
    token = _token_from_cookie(request)
    await _api_post(
        "/v1/feedback",
        token,
        get_common_settings().feedback_service_url,
        {
            "decision_id": decision_id,
            "label": label,
            "notes": notes or None,
        },
    )
    logger.info(
        "console_feedback_submitted", decision_id=decision_id, actor=claims["sub"], label=label
    )
    return RedirectResponse(url=f"/decisions/{decision_id}", status_code=302)
