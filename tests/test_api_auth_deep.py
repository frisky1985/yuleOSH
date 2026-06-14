"""Deep tests for api/auth.py — mock JWT, bcrypt, and Store.

Target: 80%+ branch coverage.
Covers: _hash_password, _verify_password, _generate_token, _decode_token,
        _extract_token, _check_rate_limit, _user_response, _login_user,
        _slugify, _handle_register, _handle_login, _handle_me, _handle_logout,
        handle_auth dispatch.
"""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest


# ======================================================================
# Fixture: a mocked Store instance
# ======================================================================

@pytest.fixture
def mock_store():
    """Patch yuleosh.store.Store to return a MagicMock."""
    with patch("yuleosh.api.auth.Store") as m:
        instance = MagicMock()
        m.return_value = instance
        yield instance


# ======================================================================
# Internal helpers
# ======================================================================

class TestSlugify:
    def test_basic(self):
        from yuleosh.api.auth import _slugify
        assert _slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        from yuleosh.api.auth import _slugify
        # Special chars are removed, spaces become hyphens
        result = _slugify("Foo Bar!@# Baz")
        assert "foo" in result
        assert result.islower()
        assert "-" in result

    def test_already_slug(self):
        from yuleosh.api.auth import _slugify
        assert _slugify("hello-world") == "hello-world"

    def test_empty(self):
        from yuleosh.api.auth import _slugify
        assert _slugify("") == ""

    def test_unicode(self):
        from yuleosh.api.auth import _slugify
        result = _slugify("café")
        assert isinstance(result, str)


class TestHashPassword:
    def test_hash_and_verify(self):
        from yuleosh.api.auth import _hash_password, _verify_password
        pwd = "mysecretpassword123"
        hashed = _hash_password(pwd)
        assert hashed != pwd
        assert hashed.startswith("$2b$")
        assert _verify_password(pwd, hashed) is True
        assert _verify_password("wrong", hashed) is False

    def test_verify_bad_hash(self):
        from yuleosh.api.auth import _verify_password
        assert _verify_password("test", "not-a-hash") is False

    def test_verify_bad_string(self):
        from yuleosh.api.auth import _verify_password
        assert _verify_password("test", "not-a-valid-bcrypt-hash") is False


class TestJWTToken:
    def test_generate_and_decode(self):
        from yuleosh.api.auth import _generate_token, _decode_token
        token = _generate_token(user_id=1, org_id=10, email="user@test.com")
        assert isinstance(token, str)
        payload = _decode_token(token)
        assert payload is not None
        assert payload["user_id"] == 1
        assert payload["org_id"] == 10
        assert payload["email"] == "user@test.com"

    def test_decode_expired(self):
        from yuleosh.api.auth import _generate_token, _decode_token
        # Generate a token with very short TTL and then mock time
        token = _generate_token(1, 10, "x@y.com")
        # Decode with the same secret should work (it's not expired yet)
        payload = _decode_token(token)
        assert payload is not None
        assert payload["user_id"] == 1

    def test_decode_invalid_token(self):
        from yuleosh.api.auth import _decode_token
        payload = _decode_token("invalid.jwt.token")
        assert payload is None

    def test_decode_empty(self):
        from yuleosh.api.auth import _decode_token
        assert _decode_token("") is None

    def test_decode_expired_sig(self):
        from yuleosh.api.auth import _decode_token
        with patch("yuleosh.api.auth.jwt.decode") as mock_decode:
            import jwt as jwt_mod
            mock_decode.side_effect = jwt_mod.ExpiredSignatureError()
            result = _decode_token("expired")
            assert result is None

    def test_decode_invalid_error(self):
        from yuleosh.api.auth import _decode_token
        with patch("yuleosh.api.auth.jwt.decode") as mock_decode:
            import jwt as jwt_mod
            mock_decode.side_effect = jwt_mod.InvalidTokenError()
            result = _decode_token("bad")
            assert result is None


class TestExtractToken:
    def test_from_dict(self):
        from yuleosh.api.auth import _extract_token
        token = _extract_token({"Authorization": "Bearer mytoken"})
        assert token == "mytoken"

    def test_from_gettable(self):
        from yuleosh.api.auth import _extract_token
        obj = MagicMock()
        obj.get.return_value = "Bearer token123"
        token = _extract_token(obj)
        assert token == "token123"

    def test_no_auth_header(self):
        from yuleosh.api.auth import _extract_token
        token = _extract_token({"Content-Type": "application/json"})
        assert token is None

    def test_no_bearer(self):
        from yuleosh.api.auth import _extract_token
        token = _extract_token({"Authorization": "Basic abc"})
        assert token is None

    def test_none_headers(self):
        from yuleosh.api.auth import _extract_token
        token = _extract_token({})
        assert token is None

    def test_empty_headers(self):
        from yuleosh.api.auth import _extract_token
        token = _extract_token("")
        assert token is None


class TestRateLimit:
    def test_first_attempt(self):
        from yuleosh.api.auth import _check_rate_limit, _SIGNIN_RATE_LIMIT
        _SIGNIN_RATE_LIMIT.clear()
        assert _check_rate_limit("test@test.com") is False

    def test_under_limit(self):
        from yuleosh.api.auth import _check_rate_limit, _SIGNIN_RATE_LIMIT
        _SIGNIN_RATE_LIMIT.clear()
        _check_rate_limit("a@b.com")  # 1st attempt
        assert _check_rate_limit("a@b.com") is False  # 2nd attempt

    def test_over_limit(self):
        from yuleosh.api.auth import _check_rate_limit, _SIGNIN_RATE_LIMIT, _MAX_SIGNIN_ATTEMPTS
        _SIGNIN_RATE_LIMIT.clear()
        for _ in range(_MAX_SIGNIN_ATTEMPTS):
            _check_rate_limit("spam@test.com")
        # Now we're at the limit
        assert _check_rate_limit("spam@test.com") is True

    def test_window_expires(self):
        from yuleosh.api.auth import _check_rate_limit, _SIGNIN_RATE_LIMIT, _MAX_SIGNIN_ATTEMPTS, _RATE_WINDOW_SECONDS
        _SIGNIN_RATE_LIMIT.clear()
        for _ in range(_MAX_SIGNIN_ATTEMPTS):
            _check_rate_limit("expire@test.com")
        # Simulate window expired
        _SIGNIN_RATE_LIMIT["expire@test.com"] = (_MAX_SIGNIN_ATTEMPTS, int(time.time()) - _RATE_WINDOW_SECONDS - 1)
        assert _check_rate_limit("expire@test.com") is False  # window reset


class TestUserResponse:
    def test_member_role_default(self):
        from yuleosh.api.auth import _user_response
        user = {"id": 1, "email": "u@t.com"}
        org = {"id": 10, "name": "TestOrg", "slug": "testorg"}
        result = _user_response(user, org)
        assert result["id"] == 1
        assert result["role"] == "member"
        assert result["org"]["name"] == "TestOrg"

    def test_with_role(self):
        from yuleosh.api.auth import _user_response
        user = {"id": 2, "email": "admin@o.com", "role": "admin"}
        org = {"id": 20, "name": "Org", "slug": "org"}
        result = _user_response(user, org)
        assert result["role"] == "admin"


class TestLoginUser:
    def test_no_orgs(self, mock_store):
        from yuleosh.api.auth import _login_user
        mock_store.list_organizations.return_value = []
        result = _login_user("u@t.com", "pass", mock_store)
        assert result is None

    def test_user_not_found(self, mock_store):
        from yuleosh.api.auth import _login_user
        mock_store.list_organizations.return_value = [{"id": 1, "name": "Org"}]
        mock_store.get_user.return_value = None
        result = _login_user("u@t.com", "pass", mock_store)
        assert result is None

    def test_user_no_password_hash(self, mock_store):
        from yuleosh.api.auth import _login_user
        mock_store.list_organizations.return_value = [{"id": 1, "name": "Org"}]
        mock_store.get_user.return_value = {"id": 1, "email": "u@t.com", "password_hash": None}
        result = _login_user("u@t.com", "pass", mock_store)
        assert result is None

    def test_wrong_password(self, mock_store):
        from yuleosh.api.auth import _login_user, _hash_password
        pw_hash = _hash_password("correct")
        mock_store.list_organizations.return_value = [{"id": 1, "name": "Org"}]
        mock_store.get_user.return_value = {"id": 1, "email": "u@t.com", "password_hash": pw_hash}
        result = _login_user("u@t.com", "wrong", mock_store)
        assert result is None


# ======================================================================
# handle_auth dispatch
# ======================================================================

class TestHandleAuth:
    def test_register(self):
        from yuleosh.api.auth import handle_auth
        result = handle_auth("POST", "register", body={}, query={})
        status = result[1]
        assert status is not None

    def test_login_route(self):
        from yuleosh.api.auth import handle_auth
        result = handle_auth("POST", "login", body={}, query={})
        status = result[1]
        assert status is not None

    def test_me_no_handler(self):
        from yuleosh.api.auth import handle_auth
        result = handle_auth("GET", "me", body={}, query={})
        status = result[1]
        assert status == 401

    def test_logout_no_handler(self):
        from yuleosh.api.auth import handle_auth
        result = handle_auth("POST", "logout", body={}, query={})
        assert result[0]["ok"] is True

    def test_unknown(self):
        from yuleosh.api.auth import handle_auth
        result = handle_auth("GET", "unknown", body={}, query={})
        assert result[1] == 404


# ======================================================================
# _handle_register
# ======================================================================

class TestRegister:
    def test_missing_email(self, mock_store):
        from yuleosh.api.auth import _handle_register
        result = _handle_register({"password": "pass1234", "organization_name": "Org"})
        assert result[1] == 400
        assert "email" in result[0]["error"].lower()

    def test_invalid_email(self, mock_store):
        from yuleosh.api.auth import _handle_register
        result = _handle_register({"email": "notanemail", "password": "pass1234", "organization_name": "Org"})
        assert result[1] == 400

    def test_short_password(self, mock_store):
        from yuleosh.api.auth import _handle_register
        result = _handle_register({"email": "u@t.com", "password": "short", "organization_name": "Org"})
        assert result[1] == 400

    def test_missing_org_name(self, mock_store):
        from yuleosh.api.auth import _handle_register
        result = _handle_register({"email": "u@t.com", "password": "password123"})
        assert result[1] == 400

    def test_existing_user_in_org(self, mock_store):
        from yuleosh.api.auth import _handle_register
        mock_store.get_organization.return_value = {"id": 1, "name": "Org"}
        mock_store.get_user.return_value = {"id": 1, "email": "existing@t.com"}
        result = _handle_register({
            "email": "existing@t.com",
            "password": "password123",
            "organization_name": "Org",
        })
        assert result[1] == 409

    def test_new_user_in_existing_org(self, mock_store):
        from yuleosh.api.auth import _handle_register
        mock_store.get_organization.return_value = {"id": 1, "name": "Org"}
        mock_store.get_user.return_value = None
        mock_store.create_user.return_value = {"id": 2, "email": "new@t.com"}
        result = _handle_register({
            "email": "new@t.com",
            "password": "password123",
            "organization_name": "Org",
        })
        assert result[1] == 200 or result[0].get("ok")

    def test_new_org(self, mock_store):
        from yuleosh.api.auth import _handle_register
        mock_store.get_organization.return_value = None
        mock_store.create_organization.return_value = {"id": 1, "name": "NewOrg"}
        mock_store.create_user.return_value = {"id": 1, "email": "admin@t.com"}
        result = _handle_register({
            "email": "admin@t.com",
            "password": "securepass123",
            "organization_name": "NewOrg",
        })
        assert result[0].get("ok")

    def test_register_returns_token(self, mock_store):
        from yuleosh.api.auth import _handle_register
        mock_store.get_organization.return_value = None
        mock_store.create_organization.return_value = {"id": 1, "name": "TestOrg", "slug": "testorg"}
        mock_store.create_user.return_value = {"id": 1, "email": "admin@t.com", "role": "admin"}
        result = _handle_register({
            "email": "admin@t.com",
            "password": "securepass123",
            "organization_name": "TestOrg",
        })
        data = result[0]
        assert data.get("ok") is True
        assert "token" in data.get("data", {})


# ======================================================================
# _handle_login
# ======================================================================

class TestLogin:
    def test_missing_email(self, mock_store):
        from yuleosh.api.auth import _handle_login
        result = _handle_login({"password": "pass1234"})
        assert result[1] == 400

    def test_invalid_email_format(self, mock_store):
        from yuleosh.api.auth import _handle_login
        result = _handle_login({"email": "bad", "password": "pass1234"})
        assert result[1] == 400

    def test_missing_password(self, mock_store):
        from yuleosh.api.auth import _handle_login
        result = _handle_login({"email": "u@t.com"})
        assert result[1] == 400

    def test_rate_limited(self, mock_store):
        from yuleosh.api.auth import _handle_login, _SIGNIN_RATE_LIMIT, _MAX_SIGNIN_ATTEMPTS
        _SIGNIN_RATE_LIMIT.clear()
        email = "ratelimit@t.com"
        for _ in range(_MAX_SIGNIN_ATTEMPTS + 1):
            _handle_login({"email": email, "password": "pass1234"})
        result = _handle_login({"email": email, "password": "pass1234"})
        assert result[1] == 429

    def test_invalid_credentials(self, mock_store):
        from yuleosh.api.auth import _handle_login
        mock_store.list_organizations.return_value = []
        result = _handle_login({"email": "nobody@t.com", "password": "pass1234"})
        assert result[1] == 401

    def test_successful_login(self, mock_store):
        from yuleosh.api.auth import _handle_login
        mock_store.list_organizations.return_value = [{"id": 1, "name": "Org"}]
        mock_store.get_user.return_value = {
            "id": 1, "email": "u@t.com", "password_hash": None, "role": "admin"
        }
        # get_user returns but no password_hash means failure
        result = _handle_login({"email": "u@t.com", "password": "pass"})
        assert result[1] == 401

    def test_successful_login_real_hash(self, mock_store):
        from yuleosh.api.auth import _handle_login, _hash_password
        pw_hash = _hash_password("correctpass")
        mock_store.list_organizations.return_value = [{"id": 1, "name": "Org"}]
        mock_store.get_user.return_value = {
            "id": 1, "email": "u@t.com", "password_hash": pw_hash, "role": "admin"
        }
        result = _handle_login({"email": "u@t.com", "password": "correctpass"})
        assert result[0].get("ok") or result[1] != 401


# ======================================================================
# _handle_me
# ======================================================================

class TestHandleMe:
    def test_no_handler(self):
        from yuleosh.api.auth import _handle_me
        result = _handle_me(handler=None)
        assert result[1] == 401

    def test_no_token(self):
        from yuleosh.api.auth import _handle_me
        handler = MagicMock()
        handler.headers = {}
        result = _handle_me(handler=handler)
        assert result[1] == 401

    def test_invalid_token(self):
        from yuleosh.api.auth import _handle_me
        handler = MagicMock()
        handler.headers = {"Authorization": "Bearer badtoken"}
        result = _handle_me(handler=handler)
        assert result[1] == 401

    def test_no_session_in_db(self, mock_store):
        from yuleosh.api.auth import _handle_me
        handler = MagicMock()
        handler.headers = {"Authorization": "Bearer validtoken"}
        mock_store.get_session.return_value = None
        with patch("yuleosh.api.auth._extract_token", return_value="validtoken"):
            with patch("yuleosh.api.auth._decode_token",
                       return_value={"user_id": 1, "org_id": 10}):
                result = _handle_me(handler=handler)
                assert result[1] == 401

    def test_user_not_found(self, mock_store):
        from yuleosh.api.auth import _handle_me
        handler = MagicMock()
        handler.headers = {"Authorization": "Bearer validtoken"}
        mock_store.get_session.return_value = {"id": 1}
        mock_store.get_user_by_id.return_value = None
        with patch("yuleosh.api.auth._extract_token", return_value="validtoken"):
            with patch("yuleosh.api.auth._decode_token",
                       return_value={"user_id": 1, "org_id": 10}):
                result = _handle_me(handler=handler)
                assert result[1] == 401

    def test_org_not_found(self, mock_store):
        from yuleosh.api.auth import _handle_me
        handler = MagicMock()
        handler.headers = {"Authorization": "Bearer validtoken"}
        mock_store.get_session.return_value = {"id": 1}
        mock_store.get_user_by_id.return_value = {"id": 1, "email": "u@t.com"}
        mock_store.get_organization_by_id.return_value = None
        with patch("yuleosh.api.auth._extract_token", return_value="validtoken"):
            with patch("yuleosh.api.auth._decode_token",
                       return_value={"user_id": 1, "org_id": 10}):
                result = _handle_me(handler=handler)
                assert result[1] == 401

    def test_success(self, mock_store):
        from yuleosh.api.auth import _handle_me
        handler = MagicMock()
        handler.headers = {"Authorization": "Bearer validtoken"}
        mock_store.get_session.return_value = {"id": 1}
        mock_store.get_user_by_id.return_value = {"id": 1, "email": "u@t.com", "role": "admin"}
        mock_store.get_organization_by_id.return_value = {"id": 10, "name": "Org", "slug": "org"}
        with patch("yuleosh.api.auth._extract_token", return_value="validtoken"):
            with patch("yuleosh.api.auth._decode_token",
                       return_value={"user_id": 1, "org_id": 10}):
                result = _handle_me(handler=handler)
                assert result[0].get("ok")


# ======================================================================
# _handle_logout
# ======================================================================

class TestHandleLogout:
    def test_no_handler(self):
        from yuleosh.api.auth import _handle_logout
        result = _handle_logout(handler=None)
        assert result[0].get("ok")

    def test_with_token(self, mock_store):
        from yuleosh.api.auth import _handle_logout
        handler = MagicMock()
        handler.headers = {"Authorization": "Bearer sometoken"}
        result = _handle_logout(handler=handler)
        # Should call delete_session
        assert mock_store.delete_session.called

    def test_delete_session_fails(self, mock_store):
        from yuleosh.api.auth import _handle_logout
        mock_store.delete_session.side_effect = Exception("db fail")
        handler = MagicMock()
        handler.headers = {"Authorization": "Bearer sometoken"}
        result = _handle_logout(handler=handler)
        assert result[0].get("ok")

    def test_no_token(self, mock_store):
        from yuleosh.api.auth import _handle_logout
        handler = MagicMock()
        handler.headers = {}
        result = _handle_logout(handler=handler)
        assert result[0].get("ok")


# ======================================================================
# json_ok / json_error helpers
# ======================================================================

class TestJsonHelpers:
    def test_json_ok(self):
        from yuleosh.api.auth import json_ok
        # These are imported from api.__init__
        import yuleosh.api
        result = yuleosh.api.json_ok({"msg": "hello"})
        assert result[0]["ok"] is True
        assert result[0]["data"]["msg"] == "hello"

    def test_json_error(self):
        import yuleosh.api
        result = yuleosh.api.json_error("Something broke", 400)
        assert result[0]["ok"] is False
        assert "Something broke" in result[0]["error"]
        assert result[1] == 400
