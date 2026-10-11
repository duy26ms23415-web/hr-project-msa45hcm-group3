import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.ai_errors import MESSAGES, install_ai_errors


@pytest.mark.asyncio
@pytest.mark.parametrize('code', ['PDF_TEXT_REQUIRED', 'PDF_ENCRYPTED', 'PDF_SIZE_INVALID', 'PDF_ACTIVE_CONTENT'])
async def test_pdf_validation_has_specific_safe_message(code):
    app = FastAPI()
    install_ai_errors(app, ['/ai'])

    @app.post('/ai/knowledge/upload')
    async def upload():
        raise HTTPException(422, code)

    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/ai/knowledge/upload')
    assert response.status_code == 422
    assert response.json()['code'] == code
    assert response.json()['detail'] == code
    assert response.json()['message'] == MESSAGES[code]
    assert response.json()['message'] != MESSAGES['INVALID_INPUT']
    assert response.json()['action'] is None
    assert response.headers['cache-control'] == 'private, no-store'
