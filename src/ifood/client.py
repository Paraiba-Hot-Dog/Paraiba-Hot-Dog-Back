"""Cliente centralizado. Credenciais nunca saem do processo servidor."""
import re
from urllib.parse import urlsplit
import threading
import time

import requests

from src.config import settings

BASE_URL = "https://merchant-api.ifood.com.br"


class IfoodError(Exception):
    def __init__(self, status=503, retry_after=30):
        super().__init__(f"Falha na API iFood (HTTP {status})")
        self.status = status
        self.retry_after = retry_after


class IfoodClient:
    def __init__(self, session=None, clock=time.monotonic):
        self.session = session or requests.Session()
        self.clock = clock
        self.token = None
        self.expires_at = 0
        self.lock = threading.Lock()

    def _response(self, response, binary=False):
        if not response.ok:
            try:
                retry = max(30, int(response.headers.get("Retry-After", "30")))
            except ValueError:
                retry = 30
            raise IfoodError(response.status_code, retry)
        if binary:
            try:
                media_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if response.status_code != 200 or media_type not in (
                        "image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"):
                    raise IfoodError(502)
                chunks, size = [], 0
                for chunk in response.iter_content(64 * 1024):
                    size += len(chunk)
                    if size > 10 * 1024 * 1024:
                        raise IfoodError(502)
                    chunks.append(chunk)
                return b"".join(chunks), media_type
            finally:
                response.close()
        return response.json() if response.content else None

    def authenticate(self):
        with self.lock:
            if self.token and self.clock() < self.expires_at:
                return
            response = self.session.post(
                f"{BASE_URL}/authentication/v1.0/oauth/token",
                data={"grantType": "client_credentials", "clientId": settings.ifood_client_id,
                      "clientSecret": settings.ifood_client_secret}, timeout=(5, 20),
            )
            data = self._response(response)
            token = data["accessToken"]
            expires = int(data["expiresIn"])
            if not token or len(token) > 8000 or expires <= 0:
                raise IfoodError(502)
            self.token, self.expires_at = token, self.clock() + expires

    def request(self, method, path, **kwargs):
        binary = kwargs.pop("binary", False)
        extra_headers = kwargs.pop("headers", {})
        for attempt in range(2):
            self.authenticate()
            headers = {"Authorization": f"Bearer {self.token}", **extra_headers}
            response = self.session.request(method, BASE_URL + path, headers=headers,
                                            timeout=(5, 20), **kwargs)
            if response.status_code == 401 and attempt == 0:
                response.close()
                self.token = None
                continue
            try:
                return self._response(response, binary=binary)
            finally:
                if binary:
                    response.close()
        raise IfoodError(401)

    def polling(self, merchants):
        return self.request("GET", "/order/v1.0/events:polling",
                            headers={"x-polling-merchants": ",".join(merchants)}) or []

    def acknowledge(self, ids):
        return self.request("POST", "/order/v1.0/events/acknowledgment",
                            json=[{"id": event_id} for event_id in ids])

    def details(self, order_id):
        return self.request("GET", f"/order/v1.0/orders/{order_id}")

    def reasons(self, order_id):
        return self.request("GET", f"/order/v1.0/orders/{order_id}/cancellationReasons")

    def command(self, order_id, action, payload):
        return self.request("POST", f"/order/v1.0/orders/{order_id}/{action}", json=payload)

    def dispute(self, dispute_id, path, body):
        # Accept without reason is sent with an empty body, as in the negotiation guide.
        kwargs = {"json": body} if body else {}
        return self.request("POST", f"/order/v1.0/disputes/{dispute_id}/{path}", **kwargs)

    def tracking(self, order_id):
        return self.request("GET", f"/order/v1.0/orders/{order_id}/tracking")

    def evidence(self, order_id, url):
        # Only a media URL attached to this order on the fixed iFood origin may receive our token.
        parsed = urlsplit(url)
        prefix = f"/order/v1.0/orders/{order_id}/cancellationEvidences/"
        if (parsed.scheme != "https" or parsed.netloc != "merchant-api.ifood.com.br"
                or parsed.query or parsed.fragment
                or not re.fullmatch(re.escape(prefix) + r"[a-zA-Z0-9-]+", parsed.path)):
            raise ValueError("URL de evidência inválida")
        return self.request("GET", parsed.path, binary=True, stream=True, allow_redirects=False)

    def validate_pickup_code(self, order_id, code):
        return self.request("POST", f"/order/v1.0/orders/{order_id}/validatePickupCode", json={"code": code})


client = IfoodClient()
