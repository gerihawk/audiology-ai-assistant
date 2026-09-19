"""Dispara POST /api/v1/billing/reconcile via HTTP para el Cron Job de
Railway — Fase 13, hito 13.2 (docs/fase-13-rfc.md §6).

Variables de entorno obligatorias:
- BILLING_RECONCILE_URL: URL completa del endpoint.
- BILLING_RECONCILE_CRON_SECRET: secreto compartido, enviado en
  X-Billing-Reconcile-Cron-Secret.

Sale con 0 si la reconciliación responde 200, 1 en cualquier otro caso
(para que Railway marque la ejecución del cron como fallida). Mismo
patrón que ops/retention-cron/purge.py y
ops/onboarding-cleanup-cron/purge.py.
"""

import http.client
import os
import sys
from urllib.parse import urlsplit


def main() -> int:
    url = os.environ["BILLING_RECONCILE_URL"]
    secret = os.environ["BILLING_RECONCILE_CRON_SECRET"]

    parts = urlsplit(url)
    conn_cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parts.netloc)
    try:
        conn.request(
            "POST",
            parts.path or "/",
            headers={"X-Billing-Reconcile-Cron-Secret": secret},
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
