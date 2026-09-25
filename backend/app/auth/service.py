"""AuthService: login real (Fase 9, hito 9.1) — busca el usuario por
email, verifica la contraseña con bcrypt y firma un JWT Bearer de vida
corta (8h). Sin domain/infraestructura propios: mismo patrón ligero que
`RetentionCleanupService`, orquesta sobre `UserRepository` (módulo
`users`) y comparte `JWT_ALGORITHM` con `RealCurrentUserProvider`
(`core/current_user.py`), que verifica el token que este servicio firma.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_log.domain.entities import AuditLogEntry
from app.audit_log.infrastructure.repository import SqlAlchemyAuditLogRepository
from app.core.config import Settings, get_settings
from app.core.current_user import JWT_ALGORITHM, TOKEN_VERSION_CLAIM, CurrentUser
from app.core.exceptions import UnauthenticatedError
from app.users.infrastructure.repository import SqlAlchemyUserRepository

ACCESS_TOKEN_TTL = timedelta(hours=8)

# Mismo mensaje para email inexistente, contraseña incorrecta, usuario
# inactivo o sin `password_hash` asignado — nunca se revela cuál de los
# casos fue, para no permitir enumerar usuarios por email.
_INVALID_CREDENTIALS_MESSAGE = "Email o contraseña incorrectos."

# Hash bcrypt precomputado de una contraseña fija que ningún usuario real
# tendrá nunca — nunca coincide con `bcrypt.checkpw`. Se compara contra
# él cuando el usuario no existe o no tiene `password_hash` asignado, para
# que `bcrypt.checkpw` (deliberadamente lento) se ejecute siempre con el
# mismo coste, exista o no el usuario. Sin esto, un email inexistente
# respondería casi al instante (cortocircuito antes de llegar a
# `checkpw`) mientras que una contraseña incorrecta sobre un email real
# tardaría el tiempo de bcrypt — el mensaje de error ya es idéntico en
# ambos casos, pero ese canal lateral de tiempo permitiría enumerar
# emails válidos midiendo latencia.
# nosemgrep: generic.secrets.security.detected-bcrypt-hash.detected-bcrypt-hash -- decoy de timing-attack (ver comentario de arriba), no es una credencial real; verificado que no está asignado a ningún usuario (docs/security/red-team-app-2026-09-22.md §F)
_DUMMY_PASSWORD_HASH = "$2b$12$reGYj6MH34Vqzv/tteadR.rlnCNHI9BnZUOmuQBXbyFJAhMO8bcni"


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        user_repository: SqlAlchemyUserRepository | None = None,
        audit_repository: SqlAlchemyAuditLogRepository | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._users = user_repository or SqlAlchemyUserRepository()
        self._audit = audit_repository or SqlAlchemyAuditLogRepository()

    async def login(self, email: str, password: str) -> str:
        user = await self._users.get_by_email(self._session, email)
        password_hash = user.password_hash if user is not None else None
        # Siempre se ejecuta, nunca en cortocircuito por `user is None` u
        # otra condición previa — ver `_DUMMY_PASSWORD_HASH`.
        password_matches = bcrypt.checkpw(
            password.encode("utf-8"), (password_hash or _DUMMY_PASSWORD_HASH).encode("utf-8")
        )
        if user is None or password_hash is None or not user.is_active or not password_matches:
            raise UnauthenticatedError(_INVALID_CREDENTIALS_MESSAGE)

        now = datetime.now(UTC)
        return jwt.encode(
            {
                "sub": str(user.id),
                TOKEN_VERSION_CLAIM: user.token_version,
                "iat": now,
                "exp": now + ACCESS_TOKEN_TTL,
            },
            self._settings.jwt_secret_key,
            algorithm=JWT_ALGORITHM,
        )

    async def logout(self, current_user: CurrentUser, request_id: str | None) -> None:
        """Hallazgo D1: revoca TODOS los JWT del usuario (todas sus
        sesiones, no solo la del token presentado) incrementando
        `token_version`. Auditoría sin metadatos: el propio evento basta."""
        await self._users.increment_token_version(self._session, current_user.id)
        await self._audit.add(
            self._session,
            AuditLogEntry(
                id=uuid.uuid4(),
                clinic_id=current_user.clinic_id,
                actor_user_id=current_user.id,
                action="auth.logout",
                entity_type="user",
                entity_id=current_user.id,
                request_id=request_id,
            ),
        )
        await self._session.commit()
