import pytest
import secrets
from unittest.mock import patch
from datetime import date, timedelta
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.config import settings


@pytest.mark.asyncio
async def test_health_check():
    """Verify healthcheck endpoint returns healthy status"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_login_flow():
    """Verify admin login returns JWT access and refresh tokens"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/auth/login", json={
            "login_email": "admin@hrgroup3.com",
            "password": "Password@123"
        })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_qr_card_issue_and_kiosk_scan():
    """Verify issuing a QR card and scanning at Kiosk Web"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        auth_resp = await ac.post("/api/v1/auth/login", json={
            "login_email": "admin@hrgroup3.com",
            "password": "Password@123"
        })
        admin_token = auth_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {admin_token}"}

        card_resp = await ac.post("/api/v1/attendance/employees/3/qr-cards", headers=headers)
        assert card_resp.status_code == 201
        card_data = card_resp.json()
        assert "raw_token" in card_data
        raw_token = card_data["raw_token"]

        kiosk_headers = {"X-Kiosk-Secret": settings.KIOSK_API_SECRET_KEY}
        scan_resp = await ac.post("/api/v1/attendance/scans", json={
            "qr_token": raw_token,
            "event_type": "CHECK_IN",
            "device_id": "KIOSK-GATE-01",
            "idempotency_key": f"TEST-SCAN-{secrets.token_hex(8)}"
        }, headers=kiosk_headers)
        assert scan_resp.status_code == 200
        scan_data = scan_resp.json()
        assert scan_data["status"] == "SUCCESS"
        assert scan_data["event_type"] == "CHECK_IN"


@pytest.mark.asyncio
async def test_leave_request_and_manager_approval():
    """Verify leave request submission and direct manager review"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        staff_auth = await ac.post("/api/v1/auth/login", json={
            "login_email": "employee@hrgroup3.com",
            "password": "Password@123"
        })
        staff_token = staff_auth.json()["access_token"]

        # Use unique future date
        future_date = (date.today() + timedelta(days=secrets.randbelow(500) + 50)).isoformat()

        leave_resp = await ac.post("/api/v1/leave/requests", json={
            "leave_type_id": 1,
            "leave_date": future_date,
            "session": "MORNING",
            "reason": "Khám sức khỏe định kỳ"
        }, headers={"Authorization": f"Bearer {staff_token}"})
        assert leave_resp.status_code == 201
        req_id = leave_resp.json()["leave_request_id"]
        assert leave_resp.json()["status"] == "PENDING"
        assert float(leave_resp.json()["leave_days"]) == 0.5

        mgr_auth = await ac.post("/api/v1/auth/login", json={
            "login_email": "manager@hrgroup3.com",
            "password": "Password@123"
        })
        mgr_token = mgr_auth.json()["access_token"]

        approve_resp = await ac.post(
            f"/api/v1/leave/requests/{req_id}/approve",
            json={"status": "APPROVED", "review_note": "Đồng ý cho nghỉ"},
            headers={"Authorization": f"Bearer {mgr_token}"}
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_payroll_calculation_and_export():
    """Verify calculating monthly payroll and downloading Excel spreadsheet"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        auth_resp = await ac.post("/api/v1/auth/login", json={
            "login_email": "admin@hrgroup3.com",
            "password": "Password@123"
        })
        admin_token = auth_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Check existing periods
        periods_resp = await ac.get("/api/v1/payroll/periods", headers=headers)
        periods = periods_resp.json()
        if periods:
            period_id = periods[0]["payroll_period_id"]
        else:
            period_resp = await ac.post("/api/v1/payroll/periods", json={
                "period_year": 2026,
                "period_month": 10
            }, headers=headers)
            assert period_resp.status_code == 201
            period_id = period_resp.json()["payroll_period_id"]

        # Calculate payroll
        calc_resp = await ac.post(f"/api/v1/payroll/periods/{period_id}/calculate", headers=headers)
        assert calc_resp.status_code == 200
        assert calc_resp.json()["status"] == "CALCULATED"

        # Check payroll lines
        lines_resp = await ac.get(f"/api/v1/payroll/periods/{period_id}/lines", headers=headers)
        assert lines_resp.status_code == 200
        lines = lines_resp.json()
        assert len(lines) >= 3

        # Export Excel spreadsheet
        export_resp = await ac.get(f"/api/v1/payroll/periods/{period_id}/export", headers=headers)
        assert export_resp.status_code == 200
        assert export_resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert len(export_resp.content) > 1000


@pytest.mark.asyncio
async def test_ai_chat_flow():
    """Verify AI chatbot answers policy and checks leave balance"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        auth_resp = await ac.post("/api/v1/auth/login", json={
            "login_email": "employee@hrgroup3.com",
            "password": "Password@123"
        })
        token = auth_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        chat_resp = await ac.post("/api/v1/ai/chat", json={
            "message": "Tôi còn bao nhiêu ngày phép năm?"
        }, headers=headers)
        assert chat_resp.status_code == 200
        chat_data = chat_resp.json()
        assert "reply" in chat_data
        assert "phép" in chat_data["reply"].lower()


@pytest.mark.asyncio
async def test_google_login_invalid_token():
    """Verify Google login blocks invalid token"""
    settings.GOOGLE_CLIENT_ID = "mock_client_id"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/auth/login/google", json={"id_token": "fake_invalid_token"})
    assert response.status_code == 401
    assert "Invalid Google token" in response.json()["detail"]


@pytest.mark.asyncio
@patch("app.api.v1.endpoints.auth.id_token.verify_oauth2_token")
async def test_google_login_unverified_email(mock_verify):
    """Verify Google login blocks unverified Google email"""
    settings.GOOGLE_CLIENT_ID = "mock_client_id"
    mock_verify.return_value = {"email": "admin@hrgroup3.com", "email_verified": False}
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/auth/login/google", json={"id_token": "valid_token_but_unverified_email"})
    
    assert response.status_code == 400
    assert "Email Google chưa được xác thực" in response.json()["detail"]


@pytest.mark.asyncio
@patch("app.api.v1.endpoints.auth.id_token.verify_oauth2_token")
async def test_google_login_success(mock_verify):
    """Verify Google login succeeds for valid verified employee"""
    mock_verify.return_value = {"email": "admin@hrgroup3.com", "email_verified": True}
    settings.GOOGLE_CLIENT_ID = "mock_client_id"
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/auth/login/google", json={"id_token": "valid_token_all_good"})
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
