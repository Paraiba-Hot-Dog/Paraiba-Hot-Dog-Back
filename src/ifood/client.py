"""Cliente centralizado. Credenciais nunca saem do processo servidor."""
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

    def _response(self, response):
        if not response.ok:
            try:
                retry = max(30, int(response.headers.get("Retry-After", "30")))
            except ValueError:
                retry = 30
            raise IfoodError(response.status_code, retry)
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
        extra_headers = kwargs.pop("headers", {})
        for attempt in range(2):
            self.authenticate()
            headers = {"Authorization": f"Bearer {self.token}", **extra_headers}
            response = self.session.request(method, BASE_URL + path, headers=headers,
                                            timeout=(5, 20), **kwargs)
            if response.status_code == 401 and attempt == 0:
                self.token = None
                continue
            return self._response(response)
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


client = IfoodClient()
