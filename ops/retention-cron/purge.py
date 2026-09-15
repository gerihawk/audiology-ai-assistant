"""Dispara POST /api/v1/retention/system-purge via HTTP para el Cron Job de Railway.

Variables de entorno obligatorias:
- RETENTION_PURGE_URL: URL completa del endpoint.
- RETENTION_CRON_SECRET: secreto compartido, enviado en X-Retention-Cron-Secret.

Sale con 0 si la purga responde 200, 1 en cualquier otro caso (para que
Railway marque la ejecución del cron como fallida).
"""

import http.client
import os
import sys
from urllib.parse import urlsplit


def main() -> int:
    url = os.environ["RETENTION_PURGE_URL"]
    secret = os.environ["RETENTION_CRON_SECRET"]

    parts = urlsplit(url)
    conn_cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parts.netloc)
    try:
        conn.request(
            "POST",
            parts.path or "/",
            headers={"X-Retention-Cron-Secret": secret},
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
