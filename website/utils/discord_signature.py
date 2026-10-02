"""Verification of Discord interaction request signatures (Ed25519)."""

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey


def verify_discord_signature(public_key: str, signature: str, timestamp: str, body: bytes) -> bool:
    """Check that a request was signed by Discord.

    Args:
        public_key: Application public key, hex-encoded.
        signature: Value of the X-Signature-Ed25519 header, hex-encoded.
        timestamp: Value of the X-Signature-Timestamp header.
        body: Raw request body, exactly as received.

    Returns:
        True if the signature is valid, False otherwise (never raises).
    """
    try:
        VerifyKey(bytes.fromhex(public_key)).verify(
            timestamp.encode() + body, bytes.fromhex(signature)
        )
        return True
    except (BadSignatureError, ValueError, TypeError):
        return False
