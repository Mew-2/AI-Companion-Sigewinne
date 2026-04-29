from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


class CompanionException(Exception):
    """业务异常基类"""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code


class LLMTimeoutException(CompanionException):
    def __init__(self, message: str = "LLM响应超时"):
        super().__init__(message, status_code=504)


class MemoryFetchException(CompanionException):
    def __init__(self, message: str = "记忆查询失败"):
        super().__init__(message, status_code=500)


def setup_exception_handlers(app):
    @app.exception_handler(CompanionException)
    async def companion_exception_handler(request: Request, exc: CompanionException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "type": "business_error"}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "参数校验失败", "detail": exc.errors()}
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "服务器内部错误", "type": "internal_error"}
        )