"""Signing out ends the session on the server and clears the cookie (ADR-012)."""

from fastapi.testclient import TestClient

from app.sign_in.session import SESSION_COOKIE

SIGN_OUT = "/api/sign-in/sign-out"


def test_after_signing_out_the_same_cookie_is_refused(client: TestClient) -> None:
    token = client.cookies[SESSION_COOKIE]

    assert client.post(SIGN_OUT).status_code == 204
    client.cookies.set(SESSION_COOKIE, token)

    assert client.get("/api/aspirations").status_code == 401


def test_signing_out_clears_the_cookie(client: TestClient) -> None:
    cookie = client.post(SIGN_OUT).headers["set-cookie"]

    assert cookie.startswith(f'{SESSION_COOKIE}="";')
    for flag in ("Max-Age=0", "Path=/", "Secure", "HttpOnly", "SameSite=lax"):
        assert flag in cookie


def test_signing_out_with_no_session_is_answered_the_same(client: TestClient) -> None:
    client.cookies.clear()

    assert client.post(SIGN_OUT).status_code == 204


def test_signing_out_again_with_the_ended_sessions_cookie_is_answered_the_same(
    client: TestClient,
) -> None:
    token = client.cookies[SESSION_COOKIE]
    client.post(SIGN_OUT)
    client.cookies.set(SESSION_COOKIE, token)

    assert client.post(SIGN_OUT).status_code == 204
