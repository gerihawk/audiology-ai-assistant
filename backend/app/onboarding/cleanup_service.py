"""UnverifiedClinicCleanupService (Fase 12, hito 12.4): borra clínicas
fantasma — dadas de alta vía `POST /clinics/signup` pero nunca verificadas
dentro del plazo de gracia (`unverified_clinic_ttl_days`, 7 días por
defecto, ver `core/config.py`).

Sin puerto propio (mismo criterio que `RetentionCleanupService`, Fase
7.2): opera directamente sobre `ClinicRepository`/`UserRepository`/
`AccountTokenRepository`, sin proveedor que intercambiar. A diferencia de
`RetentionCleanupService`, sin `CurrentUser` en absoluto — no hay ningún
actor de clínica posible, ver `purge()` — y por tanto invocado
exclusivamente desde `app/onboarding/cleanup_cli.py` (comando manual) o,
en el entorno de despliegue real, desde
`POST /api/v1/onboarding/system-cleanup` (cron externo, mismo patrón que
`app/retention/api/router.py::system_purge`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.clinics.domain.entities import Clinic
from app.clinics.infrastructure.repository import SqlAlchemyClinicRepository
from app.core.config import Settings, get_settings
from app.onboarding.infrastructure.repository import SqlAlchemyAccountTokenRepository
from app.users.infrastructure.repository import SqlAlchemyUserRepository


class UnverifiedClinicCleanupService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        clinic_repository: SqlAlchemyClinicRepository | None = None,
        user_repository: SqlAlchemyUserRepository | None = None,
        account_token_repository: SqlAlchemyAccountTokenRepository | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._clinics = clinic_repository or SqlAlchemyClinicRepository()
        self._users = user_repository or SqlAlchemyUserRepository()
        self._tokens = account_token_repository or SqlAlchemyAccountTokenRepository()

    def _cutoff(self) -> datetime:
        return datetime.now(UTC) - timedelta(days=self._settings.unverified_clinic_ttl_days)

    async def find_unverified(self) -> list[Clinic]:
        return await self._clinics.list_unverified_older_than(self._session, self._cutoff())

    async def purge(self) -> list[Clinic]:
        """Borra físicamente cada clínica fantasma encontrada, junto con
        sus usuarios y los `account_tokens` de esos usuarios — nunca un
        borrado lógico: una clínica nunca verificada no tiene ningún dato
        clínico que conservar (su único usuario, siempre inactivo, no
        pudo crear pacientes ni sesiones — ningún `CurrentUserProvider`
        resuelve un usuario inactivo, ver `core/current_user.py`).

        Sin entrada en `audit_log`, a diferencia de
        `RetentionCleanupService.purge()`: esa tabla exige `clinic_id`/
        `actor_user_id` NOT NULL válidos, y aquí ninguno de los dos existe
        todavía al terminar (la clínica deja de existir en esta misma
        operación, y por definición no tiene ningún usuario activo que
        pueda ser el actor). El detalle de cada purga se imprime por
        stdout desde `app/onboarding/cleanup_cli.py`, mismo criterio que
        las clínicas omitidas de `app/retention/cli.py`.

        Cada clínica se purga y confirma (`commit`) por separado — no es
        una única transacción atómica (misma decisión deliberada que
        `RetentionCleanupService.purge()`, ver docs/development-plan.md
        §Fase 7.2): si una falla, las anteriores ya purgadas quedan
        purgadas y una ejecución posterior simplemente ya no las
        encuentra."""
        candidates = await self.find_unverified()
        purged: list[Clinic] = []
        for clinic in candidates:
            users = await self._users.list_by_clinic(self._session, clinic.id)
            await self._tokens.delete_for_user_ids(self._session, [user.id for user in users])
            await self._users.delete_by_clinic(self._session, clinic.id)
            await self._clinics.delete(self._session, clinic.id)
            await self._session.commit()
            purged.append(clinic)
        return purged
