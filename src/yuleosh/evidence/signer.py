#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
evidence/signer.py — RSA-SHA256 digital signature for evidence packs.

Provides key generation, signing, and verification using RSA-2048 +
SHA-256 (PKCS1v15 padding) — all via the ``cryptography`` library.

Usage::

    from yuleosh.evidence.signer import (
        generate_keypair,
        sign_manifest,
        verify_manifest,
        load_public_key,
        load_private_key,
    )

    # Generate once at deployment time
    priv, pub = generate_keypair()
    save_keys(priv, pub)

    # Sign a manifest JSON string
    sig = sign_manifest(manifest_json, priv)

    # Verify later
    valid = verify_manifest(manifest_json, sig, pub)
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger("evidence.signer")

# Try to import cryptography — gracefully degrade if not available
_HAS_CRYPTO = False
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.exceptions import InvalidSignature
    _HAS_CRYPTO = True
except ImportError:
    log.warning("cryptography not installed — signing/verification disabled")


# ═══════════════════════════════════════════════════════════════════════
# Key Generation
# ═══════════════════════════════════════════════════════════════════════


def generate_keypair(key_size: int = 2048) -> Tuple[object, object]:
    """Generate an RSA key pair.

    Args:
        key_size: RSA key size in bits (default 2048, min 1024).

    Returns:
        (private_key, public_key) cryptography objects.

    Raises:
        RuntimeError: If cryptography is not installed.
    """
    if not _HAS_CRYPTO:
        raise RuntimeError(
            "cryptography library required for key generation. "
            "Install with: pip install cryptography"
        )
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
    )
    return private_key, private_key.public_key()


def save_keys(
    private_key: object,
    public_key: object,
    private_path: str = None,
    public_path: str = None,
    password: Optional[bytes] = None,
) -> Tuple[str, str]:
    """Serialize and save key pair to PEM files.

    Args:
        private_key: Private key object.
        public_key: Public key object.
        private_path: Output path for private key PEM.
        public_path: Output path for public key PEM.
        password: Passphrase to encrypt private key (optional).

    Returns:
        (private_path, public_path) where files were written.

    Raises:
        RuntimeError: If cryptography not installed.
    """
    if not _HAS_CRYPTO:
        raise RuntimeError("cryptography library required.")

    private_path = private_path or ".yuleosh/signing/private.pem"
    public_path = public_path or ".yuleosh/signing/public.pem"

    # Ensure output directory exists
    Path(private_path).parent.mkdir(parents=True, exist_ok=True)
    Path(public_path).parent.mkdir(parents=True, exist_ok=True)

    encryption = (
        serialization.BestAvailableEncryption(password)
        if password
        else serialization.NoEncryption()
    )

    with open(private_path, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=encryption,
            )
        )
    os.chmod(private_path, 0o600)  # restrict access

    with open(public_path, "wb") as f:
        f.write(
            public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )

    log.info("Saved key pair: private=%s, public=%s", private_path, public_path)
    return private_path, public_path


def load_private_key(path: str, password: Optional[bytes] = None) -> object:
    """Load an RSA private key from a PEM file.

    Args:
        path: Path to PEM file.
        password: Passphrase (if encrypted).

    Returns:
        Private key object.
    """
    if not _HAS_CRYPTO:
        raise RuntimeError("cryptography library required.")

    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=password)


def load_public_key(path: str) -> object:
    """Load an RSA public key from a PEM file.

    Args:
        path: Path to PEM file.

    Returns:
        Public key object.
    """
    if not _HAS_CRYPTO:
        raise RuntimeError("cryptography library required.")

    with open(path, "rb") as f:
        return serialization.load_pem_public_key(f.read())


# ═══════════════════════════════════════════════════════════════════════
# Signing & Verification
# ═══════════════════════════════════════════════════════════════════════


def sign_manifest(manifest_json: str, private_key: object) -> str:
    """Sign a manifest JSON string and return base64-encoded signature.

    Args:
        manifest_json: The serialized manifest JSON string.
        private_key: RSA private key object.

    Returns:
        Base64-encoded signature string.

    Raises:
        RuntimeError: If cryptography is not installed.
    """
    if not _HAS_CRYPTO:
        raise RuntimeError("cryptography library required for signing.")

    signature = private_key.sign(
        manifest_json.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("ascii")


def verify_manifest(
    manifest_json: str,
    signature_b64: str,
    public_key: object,
) -> bool:
    """Verify an RSA-SHA256 signature of a manifest JSON string.

    Args:
        manifest_json: The original serialized manifest JSON.
        signature_b64: Base64-encoded signature to verify.
        public_key: RSA public key object.

    Returns:
        True if signature matches, False otherwise.
    """
    if not _HAS_CRYPTO:
        raise RuntimeError("cryptography library required for verification.")

    try:
        public_key.verify(
            base64.b64decode(signature_b64),
            manifest_json.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except InvalidSignature:
        return False


# ═══════════════════════════════════════════════════════════════════════
# Convenience: sign a manifest file
# ═══════════════════════════════════════════════════════════════════════


def sign_manifest_file(manifest_path: str, private_key_path: str) -> str:
    """Load, sign, and save signature into an existing manifest JSON file.

    Args:
        manifest_path: Path to audit-manifest.json.
        private_key_path: Path to private PEM key.

    Returns:
        Base64 signature string written into the file.
    """
    private_key = load_private_key(private_key_path)

    with open(manifest_path) as f:
        manifest_data = f.read()

    sig = sign_manifest(manifest_data, private_key)

    # Update file with signature
    import json as _json
    manifest_obj = _json.loads(manifest_data)
    manifest_obj["signature"] = sig
    with open(manifest_path, "w") as f:
        _json.dump(manifest_obj, f, indent=2, ensure_ascii=False)

    log.info("Signed manifest: %s (signature: %s...)", manifest_path, sig[:24])
    return sig
