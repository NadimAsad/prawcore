"""Test for prawcore.Sessions module."""
import logging
import unittest
from json import dumps

from betamax import Betamax
from mock import Mock, patch
from requests.exceptions import ChunkedEncodingError, ConnectionError, ReadTimeout
from testfixtures import LogCapture

import prawcore
from prawcore.exceptions import RequestException

from .conftest import (
    CLIENT_ID,
    CLIENT_SECRET,
    PASSWORD,
    REFRESH_TOKEN,
    REQUESTOR,
    USERNAME,
    two_factor_callback,
)


class InvalidAuthorizer(prawcore.Authorizer):
    def __init__(self):
        super(InvalidAuthorizer, self).__init__(
            prawcore.TrustedAuthenticator(REQUESTOR, CLIENT_ID, CLIENT_SECRET)
        )

    def is_valid(self):
        return False


def client_authorizer():
    authenticator = prawcore.TrustedAuthenticator(REQUESTOR, CLIENT_ID, CLIENT_SECRET)
    authorizer = prawcore.Authorizer(authenticator, refresh_token=REFRESH_TOKEN)
    authorizer.refresh()
    return authorizer


def readonly_authorizer(refresh=True, requestor=REQUESTOR):
    authenticator = prawcore.TrustedAuthenticator(requestor, CLIENT_ID, CLIENT_SECRET)
    authorizer = prawcore.ReadOnlyAuthorizer(authenticator)
    if refresh:
        authorizer.refresh()
    return authorizer


def script_authorizer():
    authenticator = prawcore.TrustedAuthenticator(REQUESTOR, CLIENT_ID, CLIENT_SECRET)
    authorizer = prawcore.ScriptAuthorizer(
        authenticator, USERNAME, PASSWORD, two_factor_callback
    )
    authorizer.refresh()
    return authorizer


class SessionTest(unittest.TestCase):
    def test_close(self):
        prawcore.Session(readonly_authorizer(refresh=False)).close()

    def test_context_manager(self):
        with prawcore.Session(readonly_authorizer(refresh=False)) as session:
            self.assertIsInstance(session, prawcore.Session)

    def test_init__without_authenticator(self):
        self.assertRaises(prawcore.InvalidInvocation, prawcore.Session, None)

    def test_init__with_device_id_authorizer(self):
        authenticator = prawcore.UntrustedAuthenticator(REQUESTOR, CLIENT_ID)
        authorizer = prawcore.DeviceIDAuthorizer(authenticator)
        prawcore.Session(authorizer)

    def test_init__with_implicit_authorizer(self):
        authenticator = prawcore.UntrustedAuthenticator(REQUESTOR, CLIENT_ID)
        authorizer = prawcore.ImplicitAuthorizer(authenticator, None, 0, "")
        prawcore.Session(authorizer)

    def test_request__accepted(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__accepted"):
            session = prawcore.Session(script_authorizer())
            with LogCapture(level=logging.DEBUG) as log_capture:
                session.request("POST", "api/read_all_messages")
            log_capture.check_present(("prawcore", "DEBUG", "Response: 202 (2 bytes)"))

    @patch("requests.Session")
    def test_request__chunked_encoding_retry(self, mock_session):
        session_instance = mock_session.return_value

        # Handle Auth
        response_dict = {"access_token": "", "expires_in": 99, "scope": ""}
        session_instance.request.return_value = Mock(
            headers={}, json=lambda: response_dict, status_code=200
        )
        requestor = prawcore.Requestor("prawcore:test (by /u/bboe)")
        authorizer = readonly_authorizer(requestor=requestor)
        session_instance.request.reset_mock()

        # Fail on subsequent request
        exception = ChunkedEncodingError()
        session_instance.request.side_effect = exception

        expected = (
            "prawcore",
            "WARNING",
            "Retrying due to ChunkedEncodingError() status: GET "
            "https://oauth.reddit.com/",
        )

        with LogCapture(level=logging.WARNING) as log_capture:
            with self.assertRaises(RequestException) as context_manager:
                prawcore.Session(authorizer).request("GET", "/")
            log_capture.check(expected, expected)
        self.assertIsInstance(context_manager.exception, RequestException)
        self.assertIs(exception, context_manager.exception.original_exception)
        self.assertEqual(3, session_instance.request.call_count)

    @patch("requests.Session")
    def test_request__connection_error_retry(self, mock_session):
        session_instance = mock_session.return_value

        # Handle Auth
        response_dict = {"access_token": "", "expires_in": 99, "scope": ""}
        session_instance.request.return_value = Mock(
            headers={}, json=lambda: response_dict, status_code=200
        )
        requestor = prawcore.Requestor("prawcore:test (by /u/bboe)")
        authorizer = readonly_authorizer(requestor=requestor)
        session_instance.request.reset_mock()

        # Fail on subsequent request
        exception = ConnectionError()
        session_instance.request.side_effect = exception

        expected = (
            "prawcore",
            "WARNING",
            "Retrying due to ConnectionError() status: GET "
            "https://oauth.reddit.com/",
        )

        with LogCapture(level=logging.WARNING) as log_capture:
            with self.assertRaises(RequestException) as context_manager:
                prawcore.Session(authorizer).request("GET", "/")
            log_capture.check(expected, expected)
        self.assertIsInstance(context_manager.exception, RequestException)
        self.assertIs(exception, context_manager.exception.original_exception)
        self.assertEqual(3, session_instance.request.call_count)

    def test_request__get(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__get"):
            session = prawcore.Session(readonly_authorizer())
            params = {"limit": 100}
            response = session.request("GET", "/", params=params)
        self.assertIsInstance(response, dict)
        self.assertEqual(1, len(params))
        self.assertEqual("Listing", response["kind"])

    def test_request__patch(self):
        with Betamax(REQUESTOR).use_cassette(
            "Session_request__patch",
            match_requests_on=["method", "uri", "json-body"],
        ):
            session = prawcore.Session(script_authorizer())
            json = {"lang": "ja", "num_comments": 123}
            response = session.request("PATCH", "/api/v1/me/prefs", json=json)
            self.assertEqual("ja", response["lang"])
            self.assertEqual(123, response["num_comments"])

    def test_request__post(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__post"):
            session = prawcore.Session(script_authorizer())
            data = {
                "kind": "self",
                "sr": "reddit_api_test",
                "text": "Test!",
                "title": "A Test from PRAWCORE.",
            }
            key_count = len(data)
            response = session.request("POST", "/api/submit", data=data)
            self.assertIn("a_test_from_prawcore", response["json"]["data"]["url"])
            self.assertEqual(key_count, len(data))  # Ensure data is untouched

    def test_request__post__with_files(self):
        with Betamax(REQUESTOR).use_cassette(
            "Session_request__post__with_files",
            match_requests_on=["uri", "method"],
        ):
            session = prawcore.Session(script_authorizer())
            data = {"upload_type": "header"}
            with open("tests/files/white-square.png", "rb") as fp:
                files = {"file": fp}
                response = session.request(
                    "POST",
                    "/r/reddit_api_test/api/upload_sr_img",
                    data=data,
                    files=files,
                )
            self.assertIn("img_src", response)

    def test_request__raw_json(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__raw_json"):
            session = prawcore.Session(readonly_authorizer())
            response = session.request(
                "GET",
                "/r/reddit_api_test/comments/45xjdr/want_raw_json_test/",
            )
        self.assertEqual(
            "WANT_RAW_JSON test: < > &",
            response[0]["data"]["children"][0]["data"]["title"],
        )

    def test_request__bad_gateway(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__bad_gateway"):
            session = prawcore.Session(readonly_authorizer())
            with self.assertRaises(prawcore.ServerError) as context_manager:
                session.request("GET", "/")
            self.assertEqual(502, context_manager.exception.response.status_code)

    def test_request__bad_json(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__bad_json"):
            session = prawcore.Session(script_authorizer())
            with self.assertRaises(prawcore.BadJSON) as context_manager:
                session.request("GET", "/")
            self.assertEqual(92, len(context_manager.exception.response.content))

    def test_request__bad_request(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__bad_request"):
            session = prawcore.Session(script_authorizer())
            with self.assertRaises(prawcore.BadRequest) as context_manager:
                session.request(
                    "PUT",
                    "/api/v1/me/friends/spez",
                    data='{"note": "prawcore"}',
                )
            self.assertIn("reason", context_manager.exception.response.json())

    def test_request__cloudflare_connection_timed_out(self):
        with Betamax(REQUESTOR).use_cassette(
            "Session_request__cloudflare_connection_timed_out"
        ):
            session = prawcore.Session(readonly_authorizer())
            with self.assertRaises(prawcore.ServerError) as context_manager:
                session.request("GET", "/")
                session.request("GET", "/")
                session.request("GET", "/")
            self.assertEqual(522, context_manager.exception.response.status_code)

    def test_request__cloudflare_unknown_error(self):
        with Betamax(REQUESTOR).use_cassette(
            "Session_request__cloudflare_unknown_error"
        ):
            session = prawcore.Session(readonly_authorizer())
            with self.assertRaises(prawcore.ServerError) as context_manager:
                session.request("GET", "/")
                session.request("GET", "/")
                session.request("GET", "/")
            self.assertEqual(520, context_manager.exception.response.status_code)

    def test_request__conflict(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__conflict"):
            session = prawcore.Session(script_authorizer())
            previous = "f0214574-430d-11e7-84ca-1201093304fa"
            with self.assertRaises(prawcore.Conflict) as context_manager:
                session.request(
                    "POST",
                    "/r/ThirdRealm/api/wiki/edit",
                    data={
                        "content": "New text",
                        "page": "index",
                        "previous": previous,
                    },
                )
            self.assertEqual(409, context_manager.exception.response.status_code)

    def test_request__created(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__created"):
            session = prawcore.Session(script_authorizer())
            response = session.request("PUT", "/api/v1/me/friends/spez", data="{}")
            self.assertIn("name", response)

    def test_request__forbidden(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__forbidden"):
            session = prawcore.Session(script_authorizer())
            self.assertRaises(
                prawcore.Forbidden,
                session.request,
                "GET",
                "/user/spez/gilded/given",
            )

    def test_request__gateway_timeout(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__gateway_timeout"):
            session = prawcore.Session(readonly_authorizer())
            with self.assertRaises(prawcore.ServerError) as context_manager:
                session.request("GET", "/")
            self.assertEqual(504, context_manager.exception.response.status_code)

    def test_request__internal_server_error(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__internal_server_error"):
            session = prawcore.Session(readonly_authorizer())
            with self.assertRaises(prawcore.ServerError) as context_manager:
                session.request("GET", "/")
            self.assertEqual(500, context_manager.exception.response.status_code)

    def test_request__no_content(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__no_content"):
            session = prawcore.Session(script_authorizer())
            response = session.request("DELETE", "/api/v1/me/friends/spez")
            self.assertIsNone(response)

    def test_request__not_found(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__not_found"):
            session = prawcore.Session(script_authorizer())
            self.assertRaises(
                prawcore.NotFound,
                session.request,
                "GET",
                "/r/reddit_api_test/wiki/invalid",
            )

    def test_request__okay_with_0_byte_content(self):
        with Betamax(REQUESTOR).use_cassette(
            "Session_request__okay_with_0_byte_content"
        ):
            session = prawcore.Session(script_authorizer())
            data = {"model": dumps({"name": "redditdev"})}
            path = f"/api/multi/user/{USERNAME}/m/praw_x5g968f66a/r/redditdev"
            response = session.request("DELETE", path, data=data)
            self.assertEqual("", response)

    @patch("requests.Session")
    def test_request__read_timeout_retry(self, mock_session):
        session_instance = mock_session.return_value

        # Handle Auth
        response_dict = {"access_token": "", "expires_in": 99, "scope": ""}
        session_instance.request.return_value = Mock(
            headers={}, json=lambda: response_dict, status_code=200
        )
        requestor = prawcore.Requestor("prawcore:test (by /u/bboe)")
        authorizer = readonly_authorizer(requestor=requestor)
        session_instance.request.reset_mock()

        # Fail on subsequent request
        exception = ReadTimeout()
        session_instance.request.side_effect = exception

        expected = (
            "prawcore",
            "WARNING",
            "Retrying due to ReadTimeout() status: GET https://oauth.reddit.com/",
        )

        with LogCapture(level=logging.WARNING) as log_capture:
            with self.assertRaises(RequestException) as context_manager:
                prawcore.Session(authorizer).request("GET", "/")
            log_capture.check(expected, expected)
        self.assertIsInstance(context_manager.exception, RequestException)
        self.assertIs(exception, context_manager.exception.original_exception)
        self.assertEqual(3, session_instance.request.call_count)

    def test_request__redirect(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__redirect"):
            session = prawcore.Session(readonly_authorizer())
            with self.assertRaises(prawcore.Redirect) as context_manager:
                session.request("GET", "/r/random")
            self.assertTrue(context_manager.exception.path.startswith("/r/"))

    def test_request__redirect_301(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__redirect_301"):
            session = prawcore.Session(readonly_authorizer())
            with self.assertRaises(prawcore.Redirect) as context_manager:
                session.request("GET", "t/bird")
            self.assertTrue(context_manager.exception.path == "/r/t:bird/")

    def test_request__service_unavailable(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__service_unavailable"):
            session = prawcore.Session(readonly_authorizer())
            with self.assertRaises(prawcore.ServerError) as context_manager:
                session.request("GET", "/")
                session.request("GET", "/")
                session.request("GET", "/")
            self.assertEqual(503, context_manager.exception.response.status_code)

    def test_request__too_large(self):
        with Betamax(REQUESTOR).use_cassette(
            "Session_request__too_large", match_requests_on=["uri", "method"]
        ):
            session = prawcore.Session(script_authorizer())
            data = {"upload_type": "header"}
            with open("tests/files/too_large.jpg", "rb") as fp:
                files = {"file": fp}
                with self.assertRaises(prawcore.TooLarge) as context_manager:
                    session.request(
                        "POST",
                        "/r/reddit_api_test/api/upload_sr_img",
                        data=data,
                        files=files,
                    )
            self.assertEqual(413, context_manager.exception.response.status_code)

    def test_request__too__many_requests__with_retry_headers(self):
        requestor = prawcore.Requestor("prawcore:test (by /u/bboe)")

        with Betamax(requestor).use_cassette(
            "Session_request__too__many_requests__with_retry_headers"
        ):
            session = prawcore.Session(readonly_authorizer(requestor=requestor))
            session._requestor._http.headers.update(
                {"User-Agent": "python-requests/2.25.1"}
            )
            with self.assertRaises(prawcore.TooManyRequests) as context_manager:
                session.request("GET", "/api/v1/me")
            self.assertEqual(429, context_manager.exception.response.status_code)
            self.assertTrue(
                context_manager.exception.response.headers.get("retry-after")
            )
            self.assertEqual(
                "Too Many Requests", context_manager.exception.response.reason
            )
            self.assertTrue(
                str(context_manager.exception).startswith(
                    "received 429 HTTP response. Please wait at least"
                )
            )
            self.assertTrue(
                context_manager.exception.message.startswith("\n<!doctype html>")
            )

    def test_request__too__many_requests__without_retry_headers(self):
        requestor = prawcore.Requestor("python-requests/2.25.1")

        with Betamax(requestor).use_cassette(
            "Session_request__too__many_requests__without_retry_headers"
        ):
            with self.assertRaises(
                prawcore.exceptions.ResponseException
            ) as context_manager:
                prawcore.Session(readonly_authorizer(requestor=requestor))
            self.assertEqual(429, context_manager.exception.response.status_code)
            self.assertFalse(
                context_manager.exception.response.headers.get("retry-after")
            )
            self.assertEqual(
                "Too Many Requests", context_manager.exception.response.reason
            )
            self.assertEqual(
                context_manager.exception.response.json(),
                {"message": "Too Many Requests", "error": 429},
            )

    def test_request__unavailable_for_legal_reasons(self):
        with Betamax(REQUESTOR).use_cassette(
            "Session_request__unavailable_for_legal_reasons"
        ):
            session = prawcore.Session(readonly_authorizer())
            exception_class = prawcore.UnavailableForLegalReasons
            with self.assertRaises(exception_class) as context_manager:
                session.request("GET", "/")
            self.assertEqual(451, context_manager.exception.response.status_code)

    def test_request__unsupported_media_type(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__unsupported_media_type"):
            session = prawcore.Session(script_authorizer())
            exception_class = prawcore.SpecialError
            data = {
                "content": "type: submission\naction: upvote",
                "page": "config/automoderator",
            }
            with self.assertRaises(exception_class) as context_manager:
                session.request("POST", "r/ttft/api/wiki/edit/", data=data)
            self.assertEqual(415, context_manager.exception.response.status_code)

    def test_request__uri_too_long(self):
        with Betamax(REQUESTOR).use_cassette("Session_request__uri_too_long"):
            session = prawcore.Session(readonly_authorizer())
            path_start = "/api/morechildren?link_id=t3_n7r3uz&children="
            with open("tests/files/comment_ids.txt") as fp:
                ids = fp.read()
            with self.assertRaises(prawcore.URITooLong) as context_manager:
                session.request("GET", (path_start + ids)[:9996])
            self.assertEqual(414, context_manager.exception.response.status_code)

    def test_request__with_insufficient_scope(self):
        with Betamax(REQUESTOR).use_cassette(
            "Session_request__with_insufficient_scope"
        ):
            session = prawcore.Session(client_authorizer())
            self.assertRaises(
                prawcore.InsufficientScope,
                session.request,
                "GET",
                "/api/v1/me",
            )

    def test_request__with_invalid_access_token(self):
        authenticator = prawcore.UntrustedAuthenticator(REQUESTOR, CLIENT_ID)
        authorizer = prawcore.ImplicitAuthorizer(authenticator, None, 0, "")
        session = prawcore.Session(authorizer)

        with Betamax(REQUESTOR).use_cassette(
            "Session_request__with_invalid_access_token"
        ):
            session._authorizer.access_token = "invalid"
            self.assertRaises(prawcore.InvalidToken, session.request, "get", "/")

    def test_request__with_invalid_access_token__retry(self):
        with Betamax(REQUESTOR).use_cassette(
            "Session_request__with_invalid_access_token__retry"
        ):
            session = prawcore.Session(readonly_authorizer())
            session._authorizer.access_token += "invalid"
            response = session.request("GET", "/")
        self.assertIsInstance(response, dict)

    def test_request__with_invalid_authorizer(self):
        session = prawcore.Session(InvalidAuthorizer())
        self.assertRaises(prawcore.InvalidInvocation, session.request, "get", "/")


class SessionFunctionTest(unittest.TestCase):
    def test_session(self):
        self.assertIsInstance(prawcore.session(InvalidAuthorizer()), prawcore.Session)
