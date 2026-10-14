"""End-to-end smoke check for a running Docker deployment.

Run ``seed`` before restarting the stack and ``verify`` afterwards. The check
uses only a dedicated document/note name and removes its data after verifying
persistence. It never calls an external AI provider.
"""
from __future__ import annotations

import argparse
import io
import os
import zipfile

import httpx
import pypdfium2

from captcha_solver import solve_response


PDF_NAME = "docker-smoke-check.pdf"
DOCX_NAME = "docker-smoke-check.docx"
NOTE_TITLE = "Docker smoke persistence check"
SESSION_COOKIE = "iknowread_session"


def one_page_pdf() -> bytes:
    output = io.BytesIO()
    document = pypdfium2.PdfDocument.new()
    try:
        document.new_page(595, 842)
        document.save(output)
    finally:
        document.close()
    return output.getvalue()


def minimal_docx() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
              <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
              <Default Extension="xml" ContentType="application/xml"/>
              <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
            </Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
            </Relationships>""",
        )
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body><w:p><w:r><w:t>Docker smoke check</w:t></w:r></w:p></w:body>
            </w:document>""",
        )
    return output.getvalue()


def expect(response: httpx.Response, status: int) -> dict:
    if response.status_code != status:
        raise AssertionError(
            f"{response.request.method} {response.request.url}: "
            f"expected {status}, got {response.status_code}: {response.text[:500]}"
        )
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return {}


def login(client: httpx.Client, username: str, password: str) -> None:
    for _ in range(8):
        captcha_id, captcha_code = solve_response(
            expect(client.get("/api/captcha"), 200)
        )
        response = client.post(
            "/api/login",
            json={
                "username": username, "password": password, "role": "admin",
                "captcha_id": captcha_id, "captcha_code": captcha_code,
            },
        )
        if response.status_code == 200:
            break
        if response.status_code != 400 or "验证码" not in response.text:
            expect(response, 200)
    else:
        raise AssertionError("captcha could not be solved after 8 attempts")
    session = next(
        (cookie for cookie in client.cookies.jar if cookie.name == SESSION_COOKIE),
        None,
    )
    assert session is not None, "login did not set a session cookie"
    assert session.secure, "production session cookie is missing Secure"
    assert session.has_nonstandard_attr("HttpOnly"), "session cookie is missing HttpOnly"
    assert str(session.get_nonstandard_attr("SameSite", "")).lower() == "strict"
    expect(client.get("/api/me"), 200)


def check_gateway(client: httpx.Client) -> None:
    page = client.get("/")
    expect(page, 200)
    assert "default-src 'self'" in page.headers.get("content-security-policy", "")
    assert page.headers.get("x-content-type-options") == "nosniff"
    assert page.headers.get("x-frame-options") == "DENY"
    ready = client.get("/api/ready")
    expect(ready, 200)
    request_id = ready.headers.get("x-request-id", "")
    assert len(request_id) == 24 and all(
        character in "0123456789abcdef" for character in request_id
    ), "backend response is missing a safe request ID"
    capabilities = expect(client.get("/api/capabilities"), 200)["data"]
    assert capabilities == {"registration_enabled": False, "ocr_enabled": False}


def check_logout_revocation(client: httpx.Client) -> None:
    token = client.cookies.get(SESSION_COOKIE)
    assert token, "session token is unavailable before logout"
    expect(client.post("/api/logout"), 200)
    replay = client.get(
        "/api/me", headers={"Authorization": f"Bearer {token}"}
    )
    expect(replay, 401)


def cleanup_named_data(client: httpx.Client) -> None:
    documents = expect(
        client.get("/api/document/selectPage", params={"name": "docker-smoke-check", "pageSize": 100}),
        200,
    )["data"]["list"]
    for document in documents:
        expect(client.delete(f"/api/document/delete/{document['id']}"), 200)
    notes = expect(
        client.get("/api/notes", params={"keyword": NOTE_TITLE, "pageSize": 100}), 200
    )["data"]["list"]
    for note in notes:
        if note["title"] == NOTE_TITLE:
            expect(client.delete(f"/api/notes/{note['id']}"), 200)


def seed(client: httpx.Client) -> None:
    cleanup_named_data(client)
    expect(
        client.post(
            "/api/register",
            json={"username": "should-not-register", "password": "password123"},
        ),
        403,
    )
    expect(
        client.post(
            "/api/document/upload",
            files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
        ),
        400,
    )
    pdf = expect(
        client.post(
            "/api/document/upload",
            files={"file": (PDF_NAME, one_page_pdf(), "application/pdf")},
        ),
        200,
    )["data"]
    assert pdf["ocr_status"] == "failed" and pdf["ocr_error"] == "OCR 服务未启用"
    docx = expect(
        client.post(
            "/api/document/upload",
            files={
                "file": (
                    DOCX_NAME,
                    minimal_docx(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        ),
        200,
    )["data"]
    assert docx["ext"] == "docx"
    expect(
        client.post(
            "/api/notes",
            json={
                "document_id": pdf["id"],
                "title": NOTE_TITLE,
                "content": "This record must survive a backend restart.",
            },
        ),
        200,
    )
    check_logout_revocation(client)
    print("docker-smoke seed: PASS")


def verify(client: httpx.Client) -> None:
    documents = expect(
        client.get("/api/document/selectPage", params={"name": "docker-smoke-check", "pageSize": 100}),
        200,
    )["data"]["list"]
    by_name = {document["name"]: document for document in documents}
    assert {PDF_NAME, DOCX_NAME}.issubset(by_name), "documents did not survive restart"
    pdf = by_name[PDF_NAME]
    ranged = client.get(
        f"/api/document/preview/{pdf['id']}", headers={"Range": "bytes=0-31"}
    )
    expect(ranged, 206)
    assert ranged.headers.get("content-range", "").startswith("bytes 0-31/")
    assert ranged.content.startswith(b"%PDF-")
    docx = by_name[DOCX_NAME]
    downloaded = client.get(f"/api/document/download/{docx['id']}")
    expect(downloaded, 200)
    assert downloaded.content.startswith(b"PK")

    notes = expect(
        client.get("/api/notes", params={"keyword": NOTE_TITLE, "pageSize": 100}), 200
    )["data"]["list"]
    assert any(note["title"] == NOTE_TITLE for note in notes), "note did not survive restart"
    cleanup_named_data(client)
    print("docker-smoke verify: PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("seed", "verify"))
    parser.add_argument(
        "--base-url",
        default=os.environ.get("IKNOWREAD_TEST_BASE_URL", "https://localhost:18443"),
    )
    parser.add_argument("--insecure", action="store_true", help="accept a local test certificate")
    args = parser.parse_args()
    username = os.environ.get("IKNOWREAD_TEST_ADMIN", "admin")
    password = os.environ.get("IKNOWREAD_TEST_ADMIN_PASSWORD")
    if not password:
        parser.error("set IKNOWREAD_TEST_ADMIN_PASSWORD")
    with httpx.Client(
        base_url=args.base_url.rstrip("/"),
        verify=not args.insecure,
        timeout=30,
        trust_env=False,
    ) as client:
        check_gateway(client)
        login(client, username, password)
        (seed if args.phase == "seed" else verify)(client)


if __name__ == "__main__":
    main()
