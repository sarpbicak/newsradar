"""Kullanıcıya giden API hataları: KOD + PARAMETRE (metin frontend'de, kullanıcının dilinde).

`detail` Türkçe kalır (log, eski istemciler, testler); yanıt gövdesine `code` ve `params`
eklenir. Frontend `err.<code>` anahtarını bulursa onu gösterir, bulamazsa `detail`'i.
Yeni bir kod eklerken frontend/src/i18n.jsx (TR/EN) ve locales/de.json'a da ekleyin.
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class ApiError(HTTPException):
    def __init__(self, status_code: int, detail: str, code: str,
                 params: dict | None = None, headers: dict | None = None):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code
        self.params = params or {}


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code, "params": exc.params},
        headers=exc.headers,
    )
