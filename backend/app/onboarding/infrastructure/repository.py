"""Repositorios de AccountToken (Fase 12, hito 12.1) e Invitation (hito
12.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.onboarding.domain.entities import AccountToken, AccountTokenPurpose, Invitation
from app.onboarding.infrastructure.orm import AccountTokenORM, InvitationORM
from app.users.domain.entities import Role


def _to_domain(row: AccountTokenORM) -> AccountToken:
    return AccountToken(
        id=row.id,
        user_id=row.user_id,
        purpose=AccountTokenPurpose(row.purpose),
        token_hash=row.token_hash,
        expires_at=row.expires_at,
        used_at=row.used_at,
        created_at=row.created_at,
    )


class SqlAlchemyAccountTokenRepository:
    async def add(self, session: AsyncSession, token: AccountToken) -> None:
        session.add(
            AccountTokenORM(
                id=token.id,
                user_id=token.user_id,
                purpose=token.purpose.value,
                token_hash=token.token_hash,
                expires_at=token.expires_at,
                used_at=token.used_at,
            )
        )

    async def get_by_hash(
        self, session: AsyncSession, token_hash: str, purpose: AccountTokenPurpose
    ) -> AccountToken | None:
        """No filtra por caducidad ni por `used_at`: `AccountToken.is_usable`
        distingue "no existe" (token inventado) de "existe pero ya no sirve"
        (caducado o consumido) para que el llamador pueda dar un mensaje
        distinto en cada caso (ver `OnboardingService`)."""
        result = await session.execute(
            select(AccountTokenORM).where(
                AccountTokenORM.token_hash == token_hash, AccountTokenORM.purpose == purpose.value
            )
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def mark_used(self, session: AsyncSession, token_id: uuid.UUID) -> None:
        await session.execute(
            update(AccountTokenORM)
            .where(AccountTokenORM.id == token_id)
            .values(used_at=datetime.now(UTC))
        )

    async def invalidate_pending(
        self, session: AsyncSession, user_id: uuid.UUID, purpose: AccountTokenPurpose
    ) -> None:
        """Consume (marca `used_at`) cualquier token pendiente previo del
        mismo usuario y propósito — se llama antes de emitir uno nuevo
        (reenvío de verificación, nueva petición de reseteo) para que solo
        el último enlace enviado por email siga siendo válido."""
        await session.execute(
            update(AccountTokenORM)
            .where(
                AccountTokenORM.user_id == user_id,
                AccountTokenORM.purpose == purpose.value,
                AccountTokenORM.used_at.is_(None),
            )
            .values(used_at=datetime.now(UTC))
        )


def _invitation_to_domain(row: InvitationORM) -> Invitation:
    return Invitation(
        id=row.id,
        clinic_id=row.clinic_id,
        email=row.email,
        role=Role(row.role),
        token_hash=row.token_hash,
        expires_at=row.expires_at,
        accepted_at=row.accepted_at,
        created_by=row.created_by,
        created_at=row.created_at,
    )


class SqlAlchemyInvitationRepository:
    """Mismo patrón que `SqlAlchemyAccountTokenRepository` (Fase 12, hito
    12.1) — ver app/onboarding/domain/entities.py para por qué es una
    tabla/repositorio propios."""

    async def add(self, session: AsyncSession, invitation: Invitation) -> None:
        session.add(
            InvitationORM(
                id=invitation.id,
                clinic_id=invitation.clinic_id,
                email=invitation.email,
                role=invitation.role.value,
                token_hash=invitation.token_hash,
                expires_at=invitation.expires_at,
                accepted_at=invitation.accepted_at,
                created_by=invitation.created_by,
            )
        )

    async def get_by_hash(self, session: AsyncSession, token_hash: str) -> Invitation | None:
        """No filtra por caducidad ni por `accepted_at` — mismo motivo que
        `SqlAlchemyAccountTokenRepository.get_by_hash`: el llamador
        distingue "no existe" de "ya no es usable" vía
        `Invitation.is_usable`."""
        result = await session.execute(
            select(InvitationORM).where(InvitationORM.token_hash == token_hash)
        )
        row = result.scalar_one_or_none()
        return _invitation_to_domain(row) if row is not None else None

    async def mark_accepted(self, session: AsyncSession, invitation_id: uuid.UUID) -> None:
        await session.execute(
            update(InvitationORM)
            .where(InvitationORM.id == invitation_id)
            .values(accepted_at=datetime.now(UTC))
        )

    async def invalidate_pending_for_email(
        self, session: AsyncSession, clinic_id: uuid.UUID, email: str
    ) -> None:
        """Invalida (marca `accepted_at`) cualquier invitación pendiente
        previa para el mismo email en la misma clínica — se llama antes de
        emitir una nueva (reinvitación, p. ej. tras un email escrito mal)
        para que solo el último enlace enviado siga siendo válido. Mismo
        truco que `SqlAlchemyAccountTokenRepository.invalidate_pending`."""
        await session.execute(
            update(InvitationORM)
            .where(
                InvitationORM.clinic_id == clinic_id,
                InvitationORM.email == email,
                InvitationORM.accepted_at.is_(None),
            )
            .values(accepted_at=datetime.now(UTC))
        )
