import http.client
import tempfile
import threading
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import worker


class AuthServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        Path(cls.tmp.name, "index.html").write_text("panel", encoding="utf-8")
        worker.DashboardHandler.access_key = "clave-prueba"
        worker.DashboardHandler.auth_salt = "sal-prueba"
        worker.DashboardHandler.brand_name = "SEO Radar Local"
        handler = partial(worker.DashboardHandler, directory=cls.tmp.name)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response, data

    def test_health_is_public(self):
        response, data = self.request("GET", "/health")
        self.assertEqual(response.status, 200)
        self.assertIn(b'"status": "ok"', data)

    def test_dashboard_requires_login(self):
        response, _ = self.request("GET", "/")
        self.assertEqual(response.status, 303)
        self.assertEqual(response.getheader("Location"), "/login")

    def test_login_rejects_wrong_password(self):
        body = "password=incorrecta"
        response, data = self.request("POST", "/login", body, {
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": str(len(body)),
        })
        self.assertEqual(response.status, 401)
        self.assertIn("Clave incorrecta".encode(), data)

    def test_login_cookie_opens_dashboard(self):
        body = "password=clave-prueba"
        response, _ = self.request("POST", "/login", body, {
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": str(len(body)),
        })
        self.assertEqual(response.status, 303)
        cookie = response.getheader("Set-Cookie").split(";", 1)[0]
        dashboard, data = self.request("GET", "/", headers={"Cookie": cookie})
        self.assertEqual(dashboard.status, 200)
        self.assertEqual(data, b"panel")


if __name__ == "__main__":
    unittest.main()

