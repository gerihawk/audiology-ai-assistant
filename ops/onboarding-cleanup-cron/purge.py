"""Dispara POST /api/v1/onboarding/system-cleanup via HTTP para el Cron Job de Railway.

Variables de entorno obligatorias:
- ONBOARDING_CLEANUP_URL: URL completa del endpoint.
- ONBOARDING_CLEANUP_CRON_SECRET: secreto compartido, enviado en X-Onboarding-Cleanup-Cron-Secret.

Sale con 0 si la limpieza responde 200, 1 en cualquier otro caso (para que
Railway marque la ejecución del cron como fallida). Mismo patrón que
ops/retention-cron/purge.py.
"""

import http.client
import os
import sys
from urllib.parse import urlsplit


def main() -> int:
    url = os.environ["ONBOARDING_CLEANUP_URL"]
    secret = os.environ["ONBOARDING_CLEANUP_CRON_SECRET"]

    parts = urlsplit(url)
    conn_cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parts.netloc)
    try:
        conn.request(
            "POST",
            parts.path or "/",
            headers={"X-Onboarding-Cleanup-Cron-Secret": secret},
        )
        response = conn.getresponse()
        status = response.status
        body = response.read().decode(errors="replace")
    finally:
        conn.close()

    print(status)
    print(body)
    return 0 if status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
