"""API Key 加密工具 — 基于 Fernet 对称加密"""

import base64
import hashlib
import os
import secrets
from cryptography.fernet import Fernet, InvalidToken
from app.log import get_logger

log = get_logger("crypto")

# 固定 salt 用于从 SECRET_KEY 派生 Fernet 密钥
_DERIVE_SALT = b"pywork-llm-key-salt-v1"
_ENCRYPT_PREFIX = "fernet:"
_PBKDF2_ITERATIONS = 600_000  # OWASP 2023 推荐值
_PBKDF2_ITERATIONS_OLD = 100_000  # 旧版本兼容


async def get_or_create_secret_key(engine) -> str:
    """从 site_config 读取 SECRET_KEY，不存在则生成并持久化"""
    row = await engine.fetchone(
        "SELECT value FROM site_config WHERE key = 'SECRET_KEY'"
    )
    if row and row["value"]:
        return row["value"]

    secret = base64.urlsafe_b64encode(os.urandom(32)).decode()
    await engine.execute(
        "INSERT OR REPLACE INTO site_config (key, value) VALUES ('SECRET_KEY', ?)",
        (secret,),
    )
    return secret


def _derive_fernet_key(secret_key: str, iterations: int = _PBKDF2_ITERATIONS) -> bytes:
    """从 SECRET_KEY 通过 PBKDF2 派生 Fernet 密钥（32 bytes base64）"""
    dk = hashlib.pbkdf2_hmac("sha256", secret_key.encode(), _DERIVE_SALT, iterations)
    return base64.urlsafe_b64encode(dk)


def make_encryptor(secret_key: str) -> Fernet:
    """创建 Fernet 实例（使用新迭代次数）"""
    return Fernet(_derive_fernet_key(secret_key))


def _make_encryptor_old(secret_key: str) -> Fernet:
    """创建旧版 Fernet 实例（100k 迭代，用于向后兼容解密）"""
    return Fernet(_derive_fernet_key(secret_key, _PBKDF2_ITERATIONS_OLD))


def encrypt_value(fernet: Fernet, plaintext: str) -> str:
    """加密，返回 fernet:base64 格式"""
    token = fernet.encrypt(plaintext.encode())
    return _ENCRYPT_PREFIX + token.decode()


def decrypt_value(fernet: Fernet, ciphertext: str, allow_plaintext: bool = True,
                  old_fernet: Fernet = None) -> str:
    """解密；兼容无前缀的明文（平滑升级用）

    Args:
        allow_plaintext: True 时无前缀值直接返回（兼容），False 时抛出 ValueError
        old_fernet: 旧版 Fernet 实例，用于尝试旧密钥解密（迭代次数升级兼容）
    """
    if not ciphertext.startswith(_ENCRYPT_PREFIX):
        if not allow_plaintext:
            raise ValueError("Value is not encrypted (missing fernet: prefix)")
        return ciphertext
    raw = ciphertext[len(_ENCRYPT_PREFIX):]
    try:
        return fernet.decrypt(raw.encode()).decode()
    except InvalidToken:
        if old_fernet is not None:
            plaintext = old_fernet.decrypt(raw.encode()).decode()
            log.info("Decrypted with old key (100k iterations), consider re-encrypting")
            return plaintext
        raise


def is_encrypted(value: str) -> bool:
    """判断是否已加密"""
    return value.startswith(_ENCRYPT_PREFIX)


# ============================================================
#  Token 哈希（用于 MCP Token 等只需验证、不需恢复的场景）
# ============================================================

_TOKEN_HASH_PREFIX = "sha256:"


def hash_token(token: str) -> str:
    """SHA-256 哈希 token，返回 sha256:hex 格式"""
    h = hashlib.sha256(token.encode()).hexdigest()
    return _TOKEN_HASH_PREFIX + h


def verify_token_hash(token: str, stored: str) -> bool:
    """验证 token 是否匹配存储的哈希（恒定时间比较）"""
    if stored.startswith(_TOKEN_HASH_PREFIX):
        return secrets.compare_digest(hash_token(token), stored)
    # 兼容明文（平滑升级）
    return secrets.compare_digest(token, stored)


def is_hashed(value: str) -> bool:
    """判断是否已哈希"""
    return value.startswith(_TOKEN_HASH_PREFIX)
