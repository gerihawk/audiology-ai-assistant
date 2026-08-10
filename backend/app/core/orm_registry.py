"""Importa todos los modelos ORM para registrarlos en Base.metadata.

SQLAlchemy resuelve `ForeignKey("clinics.id")` por nombre de tabla, no por
import directo de la clase ORM. Si un módulo ORM nunca se importa en el
proceso en marcha, su tabla no existe en Base.metadata y cualquier FK que
apunte a ella falla en tiempo de flush con NoReferencedTableError. Este
módulo se importa una única vez, por su efecto secundario, al arrancar la
aplicación (app.main) y en alembic/env.py — así ningún módulo de negocio
tiene que acordarse de importar los ORM de los módulos de los que depende.
"""

from __future__ import annotations

from app.ai_pipeline.infrastructure import orm as _ai_pipeline_orm  # noqa: F401
from app.audio.infrastructure import orm as _audio_orm  # noqa: F401
from app.audit_log.infrastructure import orm as _audit_log_orm  # noqa: F401
from app.clinical_sessions.infrastructure import orm as _clinical_sessions_orm  # noqa: F401
from app.clinics.infrastructure import orm as _clinics_orm  # noqa: F401
from app.patients.infrastructure import orm as _patients_orm  # noqa: F401
from app.users.infrastructure import orm as _users_orm  # noqa: F401
