from app.core.security import hash_password, verify_password

def test_password_suffix_is_not_truncated():
    password = 'a' * 80 + 'correct'
    encoded = hash_password(password)
    assert verify_password(password, encoded)
    assert not verify_password('a' * 80 + 'wrong', encoded)

import pytest
import jwt
from datetime import timedelta
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.core.config import get_settings

def test_tokens_require_expiry_and_validate_signature():
    assert decode_token(create_access_token({'sub': 'user'}))['type'] == 'access'
    assert decode_token(create_refresh_token({'sub': 'user'}))['type'] == 'refresh'
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(create_access_token({'sub': 'user'}, timedelta(seconds=-1)))
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_token(jwt.encode({'sub': 'user', 'type': 'access'}, get_settings().JWT_SECRET_KEY, algorithm='HS256'))
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(jwt.encode({'sub': 'user', 'type': 'access', 'exp': 9999999999}, 'wrong-secret-key-that-is-long-enough', algorithm='HS256'))
