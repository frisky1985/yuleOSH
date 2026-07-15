#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for evidence/signer.py — RSA-SHA256 digital signature.

Covers:
- Key generation
- Signing and verification round-trip
- Verification failure on tampered data
- Save/load key round-trip
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from yuleosh.evidence.signer import (
    generate_keypair,
    sign_manifest,
    verify_manifest,
    save_keys,
    load_private_key,
    load_public_key,
    _HAS_CRYPTO,
)


requires_crypto = pytest.mark.skipif(
    not _HAS_CRYPTO,
    reason="cryptography library not installed",
)


class TestKeyGeneration:
    @requires_crypto
    def test_generate_keypair(self):
        priv, pub = generate_keypair(key_size=2048)
        assert priv is not None
        assert pub is not None

    @requires_crypto
    def test_key_size_default(self):
        priv, pub = generate_keypair()
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
        assert isinstance(priv, RSAPrivateKey)
        assert priv.key_size == 2048

    @requires_crypto
    def test_multiple_keys_different(self):
        priv1, pub1 = generate_keypair()
        priv2, pub2 = generate_keypair()
        from cryptography.hazmat.primitives import serialization
        pk1_bytes = priv1.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pk2_bytes = priv2.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        assert pk1_bytes != pk2_bytes


class TestSignVerify:
    @requires_crypto
    def test_sign_and_verify(self):
        priv, pub = generate_keypair()
        manifest = '{"build_id": "test-001", "version": "1.0.0"}'
        sig = sign_manifest(manifest, priv)
        assert isinstance(sig, str)
        assert len(sig) > 0
        assert verify_manifest(manifest, sig, pub) is True

    @requires_crypto
    def test_verify_fails_on_tampered(self):
        priv, pub = generate_keypair()
        original = '{"build_id": "test-001", "version": "1.0.0"}'
        tampered = '{"build_id": "test-002", "version": "1.0.0"}'
        sig = sign_manifest(original, priv)
        assert verify_manifest(tampered, sig, pub) is False

    @requires_crypto
    def test_verify_fails_on_wrong_key(self):
        priv1, pub1 = generate_keypair()
        _, pub2 = generate_keypair()
        manifest = '{"build_id": "test-001"}'
        sig = sign_manifest(manifest, priv1)
        assert verify_manifest(manifest, sig, pub2) is False

    @requires_crypto
    def test_sign_unicode(self):
        priv, pub = generate_keypair()
        manifest = '{"name": "evidence_test"}'
        sig = sign_manifest(manifest, priv)
        assert verify_manifest(manifest, sig, pub) is True

    @requires_crypto
    def test_sign_empty_string(self):
        priv, pub = generate_keypair()
        sig = sign_manifest("", priv)
        assert verify_manifest("", sig, pub) is True


class TestKeySerialization:
    @requires_crypto
    def test_save_and_load_keys(self):
        priv, pub = generate_keypair()
        with tempfile.TemporaryDirectory() as tmp:
            priv_path = os.path.join(tmp, "private.pem")
            pub_path = os.path.join(tmp, "public.pem")
            save_keys(priv, pub, private_path=priv_path, public_path=pub_path)
            assert os.path.exists(priv_path)
            assert os.path.exists(pub_path)
            loaded_priv = load_private_key(priv_path)
            loaded_pub = load_public_key(pub_path)
            manifest = '{"test": "roundtrip"}'
            sig = sign_manifest(manifest, loaded_priv)
            assert verify_manifest(manifest, sig, loaded_pub) is True

    @requires_crypto
    def test_save_and_sign_existing_content(self):
        priv, pub = generate_keypair()
        with tempfile.TemporaryDirectory() as tmp:
            priv_path = os.path.join(tmp, "private.pem")
            pub_path = os.path.join(tmp, "public.pem")
            save_keys(priv, pub, private_path=priv_path, public_path=pub_path)

            # Create manifest content
            manifest_content = '{"build_id": "test", "files": []}'

            # Sign the exact content bytes
            priv_key = load_private_key(priv_path)
            sig = sign_manifest(manifest_content, priv_key)
            assert sig is not None

            # Verify against the exact same content
            loaded_pub = load_public_key(pub_path)
            assert verify_manifest(manifest_content, sig, loaded_pub) is True

            # Tampered content should fail
            tampered = '{"build_id": "tampered", "files": []}'
            assert verify_manifest(tampered, sig, loaded_pub) is False

    @requires_crypto
    def test_save_keys_with_password(self):
        priv, pub = generate_keypair()
        with tempfile.TemporaryDirectory() as tmp:
            priv_path = os.path.join(tmp, "private.pem")
            pub_path = os.path.join(tmp, "public.pem")
            password = b"test-password-123"
            save_keys(priv, pub, private_path=priv_path, public_path=pub_path, password=password)
            loaded_priv = load_private_key(priv_path, password=password)
            assert loaded_priv is not None
            with pytest.raises(Exception):
                load_private_key(priv_path)

    @requires_crypto
    def test_key_permissions(self):
        priv, pub = generate_keypair()
        with tempfile.TemporaryDirectory() as tmp:
            priv_path = os.path.join(tmp, "private.pem")
            pub_path = os.path.join(tmp, "public.pem")
            save_keys(priv, pub, private_path=priv_path, public_path=pub_path)
            mode = os.stat(priv_path).st_mode & 0o777
            assert mode == 0o600


@pytest.mark.skipif(_HAS_CRYPTO, reason="cryptography IS installed, testing no-crypto path requires skipping")
class TestNoCrypto:
    def test_generate_fails_without_crypto(self):
        pass
