"""统一错误体系 - 借鉴 stock-sdk SdkError 设计

将 server.py 中 4 种混用的错误响应格式归一为 1 种:
    { success: False, error: { code, message, request_id } }

设计要点:
1. ApiError 常规类(不用 dataclass,避免继承 Exception 的坑)
2. ErrorCode 枚举覆盖所有业务场景
3. handle_api_error 统一兜底,未知异常不暴露 str(e) 给客户端
4. api_success 统一成功响应格式
"""
import uuid
import logging
from enum import Enum
from typing import Any, Optional, Tuple


class ErrorCode(Enum):
    """标准错误码"""
    INVALID_SYMBOL = 'INVALID_SYMBOL'          # 符号解析失败
    DATA_NOT_FOUND = 'DATA_NOT_FOUND'          # 数据不存在
    UPSTREAM_ERROR = 'UPSTREAM_ERROR'          # 上游数据源错误
    RATE_LIMITED = 'RATE_LIMITED'              # 被限流
    VALIDATION_ERROR = 'VALIDATION_ERROR'      # 参数校验失败
    INTERNAL_ERROR = 'INTERNAL_ERROR'          # 内部错误


class ApiError(Exception):
    """
    统一 API 异常

    对外只暴露友好的 message,详细错误 detail 仅写日志。
    每个异常携带 request_id 便于排查。
    """

    def __init__(self, code: ErrorCode, message: str,
                 detail: Optional[str] = None,
                 status_code: int = 500,
                 request_id: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message          # 对用户友好(不暴露敏感信息)
        self.detail = detail            # 详细错误(仅写日志)
        self.status_code = status_code
        self.request_id = request_id or str(uuid.uuid4())[:8]

    def to_response(self) -> dict:
        """转为统一 JSON 响应格式"""
        return {
            'success': False,
            'error': {
                'code': self.code.value,
                'message': self.message,
                'request_id': self.request_id,
            }
        }


def handle_api_error(e: Exception, logger: logging.Logger) -> Tuple[dict, int]:
    """
    统一异常处理,返回 (response_dict, status_code)

    - ApiError: 按其自身的 code/message/status_code 返回
    - 其他异常: 兜底为 INTERNAL_ERROR,message 不暴露 str(e)
    """
    if isinstance(e, ApiError):
        if e.detail:
            logger.error(f"[{e.request_id}] {e.code.value}: {e.detail}")
        else:
            logger.error(f"[{e.request_id}] {e.code.value}: {e.message}")
        return e.to_response(), e.status_code

    # 未知异常兜底(不暴露 str(e) 给客户端)
    request_id = str(uuid.uuid4())[:8]
    logger.error(f"[{request_id}] UNEXPECTED: {e}", exc_info=True)
    return ApiError(
        code=ErrorCode.INTERNAL_ERROR,
        message='服务内部错误,请稍后重试',
        detail=str(e),
        request_id=request_id,
    ).to_response(), 500


def api_success(data: Any, meta: Optional[dict] = None) -> dict:
    """
    统一成功响应格式

    Args:
        data: 业务数据
        meta: 可选的元信息(如 total/count/pagination 等)
    """
    return {
        'success': True,
        'data': data,
        'meta': meta or {},
    }
