import uuid

from app.auth_utils import create_access_token, decode_access_token_subject, hash_password, verify_password


def test_password_hash_roundtrip() -> None:
    h = hash_password("shortSecret9")
    assert verify_password("shortSecret9", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip_subject() -> None:
    uid = uuid.uuid4()
    tok = create_access_token(uid)
    assert decode_access_token_subject(tok) == uid
