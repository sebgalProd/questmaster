"""Tests for Discord Ed25519 request signature verification."""

import pytest
from nacl.signing import SigningKey

from website.utils.discord_signature import verify_discord_signature


@pytest.fixture
def keys():
    signing = SigningKey.generate()
    return signing, signing.verify_key.encode().hex()


def _sign(signing, timestamp, body):
    return signing.sign(timestamp.encode() + body).signature.hex()


def test_valid_signature(keys):
    signing, public = keys
    body = b'{"type":1}'
    assert verify_discord_signature(public, _sign(signing, "123", body), "123", body)


def test_modified_body_is_rejected(keys):
    signing, public = keys
    sig = _sign(signing, "123", b'{"type":1}')
    assert not verify_discord_signature(public, sig, "123", b'{"type":2}')


def test_modified_timestamp_is_rejected(keys):
    signing, public = keys
    body = b'{"type":1}'
    assert not verify_discord_signature(public, _sign(signing, "123", body), "124", body)


def test_other_key_is_rejected(keys):
    signing, _ = keys
    other_public = SigningKey.generate().verify_key.encode().hex()
    body = b"{}"
    assert not verify_discord_signature(other_public, _sign(signing, "1", body), "1", body)


@pytest.mark.parametrize("signature", ["", "zz", "00"])
def test_malformed_signature_is_rejected(keys, signature):
    _, public = keys
    assert not verify_discord_signature(public, signature, "1", b"{}")


def test_malformed_public_key_is_rejected(keys):
    signing, _ = keys
    body = b"{}"
    assert not verify_discord_signature("not-hex", _sign(signing, "1", body), "1", body)
