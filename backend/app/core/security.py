from cryptography.fernet import Fernet
from app.core.config import get_settings


def _get_fernet() -> Fernet:
    settings = get_settings()
    if not settings.ENCRYPTION_KEY:
        raise ValueError("ENCRYPTION_KEY not configured. Set it in .env")
    return Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt_api_key(api_key: str) -> str:
    """加密 API Key，返回加密后的字符串"""
    f = _get_fernet()
    return f.encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted: str) -> str:
    """解密 API Key，返回明文"""
    f = _get_fernet()
    return f.decrypt(encrypted.encode()).decode()


def mask_api_key(api_key: str) -> str:
    """脱敏 API Key 用于日志：sk-xxxx...xxxx"""
    if len(api_key) <= 8:
        return "***"
    return f"{api_key[:4]}...{api_key[-4:]}"
