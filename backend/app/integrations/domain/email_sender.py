"""Puerto EmailSender (Fase 12, hito 12.1).

Mismo criterio que `TranscriptionProvider` (Fase 5): interfaz agnóstica del
proveedor real, resuelta por configuración vía
`app/integrations/factory.py::build_email_sender`. `EMAIL_PROVIDER=mock`
(por defecto, ver `MockEmailSender`) nunca envía tráfico real — regla no
negociable de `CLAUDE.md` §6 ("nunca llames a una API de pago real" fuera
de una decisión explícita por entorno).

Uso en este hito, exclusivamente correo de personal de clínica (nunca
datos de pacientes, ver docs/fase-12-rfc.md §2/§5): verificación de email
de registro y recuperación de contraseña. La Fase 12, hito 12.2
(invitaciones a compañeros) reutilizará el mismo puerto.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True, frozen=True)
class EmailMessage:
    to_email: str
    to_name: str
    subject: str
    html_body: str
    #: Alternativa en texto plano — algunos clientes de correo o filtros
    #: antispam penalizan un mensaje que solo lleva HTML.
    text_body: str


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...
