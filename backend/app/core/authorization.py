"""Autorización centralizada.

Ningún router ni repositorio implementa comprobaciones de rol propias:
todo pasa por las funciones `authorize_*` definidas aquí.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from app.core.current_user import CurrentUser
from app.core.exceptions import ForbiddenError
from app.users.domain.entities import Role


class PatientAction(StrEnum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    ARCHIVE = "archive"
    RESTORE = "restore"


PATIENT_PERMISSIONS: dict[Role, frozenset[PatientAction]] = {
    Role.ADMIN: frozenset(PatientAction),
    Role.AUDIOLOGIST: frozenset(
        {
            PatientAction.CREATE,
            PatientAction.READ,
            PatientAction.UPDATE,
            PatientAction.ARCHIVE,
        }
    ),
    Role.VIEWER: frozenset({PatientAction.READ}),
}


def authorize_patient_action(current_user: CurrentUser, action: PatientAction) -> None:
    if action not in PATIENT_PERMISSIONS[current_user.role]:
        raise ForbiddenError(
            f"El rol '{current_user.role.value}' no tiene permiso para "
            f"'{action.value}' sobre pacientes."
        )


class ClinicalSessionAction(StrEnum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    CHANGE_PROFESSIONAL = "change_professional"
    START = "start"
    COMPLETE = "complete"
    SUBMIT_REVIEW = "submit_review"
    REVIEW = "review"
    CANCEL = "cancel"
    ARCHIVE = "archive"
    RESTORE = "restore"


CLINICAL_SESSION_PERMISSIONS: dict[Role, frozenset[ClinicalSessionAction]] = {
    Role.ADMIN: frozenset(ClinicalSessionAction),
    Role.AUDIOLOGIST: frozenset(
        {
            ClinicalSessionAction.CREATE,
            ClinicalSessionAction.READ,
            ClinicalSessionAction.UPDATE,
            ClinicalSessionAction.START,
            ClinicalSessionAction.COMPLETE,
            ClinicalSessionAction.SUBMIT_REVIEW,
            ClinicalSessionAction.CANCEL,
            ClinicalSessionAction.ARCHIVE,
        }
    ),
    Role.VIEWER: frozenset({ClinicalSessionAction.READ}),
}

#: Acciones para las que, siendo `audiologist`, se exige además ser el
#: profesional responsable de la sesión (`professional_id ==
#: current_user.id`) — "sus propias sesiones", nunca las de un compañero
#: de la misma clínica. `admin` no tiene esta restricción. `CREATE` es un
#: caso especial (corrección de la auditoría RBAC del hito 8.1,
#: docs/privacy-and-security.md §13): no hay sesión existente todavía, así
#: que `professional_id` es aquí el profesional que el cliente pide
#: asignar a la sesión nueva, no el dueño de un recurso ya persistido —
#: mismo efecto ("un audiologist solo puede crear sesiones para sí
#: mismo"), pero centralizado en esta función en vez de una comprobación
#: de rol ad-hoc en `ClinicalSessionService.create`.
_OWNERSHIP_REQUIRED_ACTIONS: frozenset[ClinicalSessionAction] = frozenset(
    {
        ClinicalSessionAction.CREATE,
        ClinicalSessionAction.UPDATE,
        ClinicalSessionAction.START,
        ClinicalSessionAction.COMPLETE,
        ClinicalSessionAction.SUBMIT_REVIEW,
        ClinicalSessionAction.CANCEL,
        ClinicalSessionAction.ARCHIVE,
    }
)


def authorize_clinical_session_action(
    current_user: CurrentUser,
    action: ClinicalSessionAction,
    *,
    professional_id: uuid.UUID | None = None,
) -> None:
    """Autoriza una acción sobre `clinical_sessions`.

    `professional_id` es el `professional_id` de la sesión ya existente
    sobre la que se actúa, salvo para `CREATE`, donde es el profesional
    que se pide asignar a la sesión nueva (`None` solo para acciones sin
    ningún profesional implicado, p. ej. el listado). Para `audiologist`,
    las acciones en `_OWNERSHIP_REQUIRED_ACTIONS` exigen además que
    `professional_id == current_user.id` — la comprobación de propiedad
    de la sesión, no solo de rol.
    """
    if action not in CLINICAL_SESSION_PERMISSIONS[current_user.role]:
        raise ForbiddenError(
            f"El rol '{current_user.role.value}' no tiene permiso para "
            f"'{action.value}' sobre sesiones clínicas."
        )
    if (
        current_user.role == Role.AUDIOLOGIST
        and action in _OWNERSHIP_REQUIRED_ACTIONS
        and professional_id != current_user.id
    ):
        raise ForbiddenError(
            "Un audiologist solo puede operar sobre sus propias sesiones clínicas."
        )


class AudioRecordingAction(StrEnum):
    UPLOAD = "upload"
    READ = "read"
    DELETE = "delete"
    TRANSCRIBE = "transcribe"


#: Mismo patrón que ClinicalSessionAction (Fase 5). `audio_recordings` no
#: tiene rol propio en la matriz de negocio — hereda el criterio de
#: "propiedad de la sesión clínica" ya establecido, resuelto vía
#: `professional_id` de la `ClinicalSession` dueña del audio (nunca un
#: campo del propio audio, que no tiene profesional responsable).
AUDIO_RECORDING_PERMISSIONS: dict[Role, frozenset[AudioRecordingAction]] = {
    Role.ADMIN: frozenset(AudioRecordingAction),
    Role.AUDIOLOGIST: frozenset(AudioRecordingAction),
    Role.VIEWER: frozenset({AudioRecordingAction.READ}),
}

_AUDIO_RECORDING_OWNERSHIP_REQUIRED: frozenset[AudioRecordingAction] = frozenset(
    {AudioRecordingAction.UPLOAD, AudioRecordingAction.DELETE, AudioRecordingAction.TRANSCRIBE}
)


def authorize_audio_recording_action(
    current_user: CurrentUser,
    action: AudioRecordingAction,
    *,
    professional_id: uuid.UUID | None = None,
) -> None:
    """`professional_id` es el profesional responsable de la sesión clínica
    dueña del audio (`None` para `READ`, sin restricción de propiedad)."""
    if action not in AUDIO_RECORDING_PERMISSIONS[current_user.role]:
        raise ForbiddenError(
            f"El rol '{current_user.role.value}' no tiene permiso para "
            f"'{action.value}' sobre grabaciones de audio."
        )
    if (
        current_user.role == Role.AUDIOLOGIST
        and action in _AUDIO_RECORDING_OWNERSHIP_REQUIRED
        and professional_id != current_user.id
    ):
        raise ForbiddenError(
            "Un audiologist solo puede subir/eliminar/transcribir audio de sus propias "
            "sesiones clínicas."
        )


class AIPipelineAction(StrEnum):
    TRIGGER = "trigger"
    READ = "read"


class AIArtifactAction(StrEnum):
    READ = "read"
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    DELETE = "delete"


#: Mismo patrón de permisos que ClinicalSessionAction — ver
#: docs/ai-pipeline-architecture.md §12, decisión 15.
AI_PIPELINE_PERMISSIONS: dict[Role, frozenset[AIPipelineAction]] = {
    Role.ADMIN: frozenset(AIPipelineAction),
    Role.AUDIOLOGIST: frozenset(AIPipelineAction),
    Role.VIEWER: frozenset({AIPipelineAction.READ}),
}

AI_ARTIFACT_PERMISSIONS: dict[Role, frozenset[AIArtifactAction]] = {
    Role.ADMIN: frozenset(AIArtifactAction),
    Role.AUDIOLOGIST: frozenset(AIArtifactAction),
    Role.VIEWER: frozenset({AIArtifactAction.READ}),
}

#: Para `audiologist`, disparar el pipeline exige ser el profesional
#: responsable de la sesión — mismo criterio de propiedad que
#: `clinical_sessions`. `READ` no tiene restricción de propiedad (igual
#: que leer sesiones clínicas).
_AI_PIPELINE_OWNERSHIP_REQUIRED: frozenset[AIPipelineAction] = frozenset({AIPipelineAction.TRIGGER})
_AI_ARTIFACT_OWNERSHIP_REQUIRED: frozenset[AIArtifactAction] = frozenset(
    {
        AIArtifactAction.APPROVE,
        AIArtifactAction.REJECT,
        AIArtifactAction.EDIT,
        AIArtifactAction.DELETE,
    }
)


def authorize_ai_pipeline_action(
    current_user: CurrentUser,
    action: AIPipelineAction,
    *,
    professional_id: uuid.UUID | None = None,
) -> None:
    """`professional_id` es el profesional responsable de la sesión clínica
    sobre la que se dispara el pipeline (`None` para acciones sin sesión
    concreta)."""
    if action not in AI_PIPELINE_PERMISSIONS[current_user.role]:
        raise ForbiddenError(
            f"El rol '{current_user.role.value}' no tiene permiso para "
            f"'{action.value}' sobre el AI Pipeline."
        )
    if (
        current_user.role == Role.AUDIOLOGIST
        and action in _AI_PIPELINE_OWNERSHIP_REQUIRED
        and professional_id != current_user.id
    ):
        raise ForbiddenError(
            "Un audiologist solo puede disparar el pipeline sobre sus propias sesiones clínicas."
        )


def authorize_ai_artifact_action(
    current_user: CurrentUser,
    action: AIArtifactAction,
    *,
    professional_id: uuid.UUID | None = None,
) -> None:
    """`professional_id` es el profesional responsable de la sesión clínica
    a la que pertenece el artefacto (`None` para `READ`, que no tiene
    restricción de propiedad)."""
    if action not in AI_ARTIFACT_PERMISSIONS[current_user.role]:
        raise ForbiddenError(
            f"El rol '{current_user.role.value}' no tiene permiso para "
            f"'{action.value}' sobre artefactos de IA."
        )
    if (
        current_user.role == Role.AUDIOLOGIST
        and action in _AI_ARTIFACT_OWNERSHIP_REQUIRED
        and professional_id != current_user.id
    ):
        raise ForbiddenError(
            "Un audiologist solo puede aprobar/rechazar/editar/eliminar artefactos de "
            "sus propias sesiones clínicas."
        )


class ClinicalDocumentAction(StrEnum):
    EXPORT = "export"


#: Precondición del hito 6.0 de la Fase 6 (docs/fase-6-rfc.md §9.1,
#: §10) — permiso declarado antes de que exista el servicio de
#: exportación (hito 6.6), mismo patrón que `HUMAN_EDITED` (declarado en
#: Fase 4, activado en Fase 6). VIEWER puede revisar pero no descargar —
#: ver docs/fase-6-rfc.md §7.5.
CLINICAL_DOCUMENT_PERMISSIONS: dict[Role, frozenset[ClinicalDocumentAction]] = {
    Role.ADMIN: frozenset(ClinicalDocumentAction),
    Role.AUDIOLOGIST: frozenset(ClinicalDocumentAction),
    Role.VIEWER: frozenset(),
}


def authorize_clinical_document_action(
    current_user: CurrentUser, action: ClinicalDocumentAction
) -> None:
    if action not in CLINICAL_DOCUMENT_PERMISSIONS[current_user.role]:
        raise ForbiddenError(
            f"El rol '{current_user.role.value}' no tiene permiso para "
            f"'{action.value}' sobre documentos clínicos."
        )


class ClinicalRecordAction(StrEnum):
    READ = "read"


#: Hito 6.7.3 (docs/fase-6-rfc.md §7.5/§8). Deliberadamente más permisivo
#: que `CLINICAL_DOCUMENT_PERMISSIONS`: `viewer` puede consultar la
#: historia clínica longitudinal en pantalla pero no descargarla — la
#: exportación longitudinal (hito 6.7.4) exigirá además
#: `ClinicalDocumentAction.EXPORT`, que `viewer` no posee. Sin ownership
#: por `professional_id`: es una vista de solo lectura del expediente
#: completo del paciente, no de "mis sesiones".
CLINICAL_RECORD_PERMISSIONS: dict[Role, frozenset[ClinicalRecordAction]] = {
    Role.ADMIN: frozenset(ClinicalRecordAction),
    Role.AUDIOLOGIST: frozenset(ClinicalRecordAction),
    Role.VIEWER: frozenset(ClinicalRecordAction),
}


def authorize_clinical_record_action(
    current_user: CurrentUser, action: ClinicalRecordAction
) -> None:
    if action not in CLINICAL_RECORD_PERMISSIONS[current_user.role]:
        raise ForbiddenError(
            f"El rol '{current_user.role.value}' no tiene permiso para "
            f"'{action.value}' sobre la historia clínica longitudinal."
        )


class ConsentAction(StrEnum):
    READ = "read"
    CREATE = "create"


#: Fase 7.1 (docs/development-plan.md). Deliberadamente distinta del
#: patrón "admin sin restricción" del resto de matrices: registrar un
#: consentimiento es un acto asistencial ante el paciente, no una tarea
#: administrativa — solo `audiologist` puede crear; `admin` puede leer el
#: histórico (supervisión) pero no registrar en nombre del profesional.
#: `viewer` no tiene ninguna acción. Sin ownership por `professional_id`:
#: el consentimiento es del paciente, no de "mis sesiones".
CONSENT_PERMISSIONS: dict[Role, frozenset[ConsentAction]] = {
    Role.ADMIN: frozenset({ConsentAction.READ}),
    Role.AUDIOLOGIST: frozenset(ConsentAction),
    Role.VIEWER: frozenset(),
}


def authorize_consent_action(current_user: CurrentUser, action: ConsentAction) -> None:
    if action not in CONSENT_PERMISSIONS[current_user.role]:
        raise ForbiddenError(
            f"El rol '{current_user.role.value}' no tiene permiso para "
            f"'{action.value}' sobre consentimientos."
        )


class RetentionAction(StrEnum):
    READ = "read"
    PURGE = "purge"
    #: Purga definitiva (física, irreversible) de TODAS las sesiones
    #: clínicas, artefactos de IA y audio de un paciente concreto —
    #: distinta de `PURGE` (que solo purga audio ya expirado por
    #: antigüedad). Añadido 2026-09-18, ver docs/privacy-and-security.md
    #: §8 y RetentionCleanupService.purge_patient_clinical_data(). Cierra
    #: el hueco de "el paciente ejerce su derecho de supresión una vez
    #: pasado el plazo legal de conservación de la clínica" — hasta ahora
    #: no existía ningún borrado físico posible de `ai_artifacts`/
    #: `clinical_sessions`.
    PURGE_PATIENT_DATA = "purge_patient_data"


#: Fase 7.2 (docs/development-plan.md). A diferencia de
#: `ConsentAction`/resto de matrices, aquí ni siquiera `audiologist` tiene
#: ninguna acción — la purga de audio expirado es una tarea puramente
#: administrativa, no asistencial (ver docs/api-specification.md
#: §Retention). `PURGE_PATIENT_DATA` hereda el mismo criterio "solo
#: admin" — es la acción más destructiva de toda la matriz, nunca
#: delegable a `audiologist`.
RETENTION_PERMISSIONS: dict[Role, frozenset[RetentionAction]] = {
    Role.ADMIN: frozenset(RetentionAction),
    Role.AUDIOLOGIST: frozenset(),
    Role.VIEWER: frozenset(),
}


def authorize_retention_action(current_user: CurrentUser, action: RetentionAction) -> None:
    if action not in RETENTION_PERMISSIONS[current_user.role]:
        raise ForbiddenError(
            f"El rol '{current_user.role.value}' no tiene permiso para "
            f"'{action.value}' sobre la retención de audio."
        )


class IntegrationConfigAction(StrEnum):
    READ = "read"
    UPDATE = "update"


#: Fase 7.3 (docs/development-plan.md). Mismo patrón "admin únicamente"
#: que `RetentionAction`: configurar integraciones externas es una tarea
#: puramente administrativa, ni siquiera `audiologist` tiene acceso.
INTEGRATION_CONFIG_PERMISSIONS: dict[Role, frozenset[IntegrationConfigAction]] = {
    Role.ADMIN: frozenset(IntegrationConfigAction),
    Role.AUDIOLOGIST: frozenset(),
    Role.VIEWER: frozenset(),
}


def authorize_integration_config_action(
    current_user: CurrentUser, action: IntegrationConfigAction
) -> None:
    if action not in INTEGRATION_CONFIG_PERMISSIONS[current_user.role]:
        raise ForbiddenError(
            f"El rol '{current_user.role.value}' no tiene permiso para "
            f"'{action.value}' sobre la configuración de integraciones."
        )


class InvitationAction(StrEnum):
    CREATE = "create"
    READ = "read"
    REVOKE = "revoke"


#: Fase 12, hitos 12.2/12.3 (docs/fase-12-rfc.md §4.2). Mismo patrón
#: "admin únicamente" que `RetentionAction`/`IntegrationConfigAction`:
#: invitar, consultar o revocar una invitación de la clínica es una tarea
#: administrativa, ni siquiera `audiologist` puede hacerlo.
INVITATION_PERMISSIONS: dict[Role, frozenset[InvitationAction]] = {
    Role.ADMIN: frozenset(InvitationAction),
    Role.AUDIOLOGIST: frozenset(),
    Role.VIEWER: frozenset(),
}


class BillingAction(StrEnum):
    CREATE_CHECKOUT_SESSION = "create_checkout_session"
    #: Fase 13, hito 13.3 — abrir el Stripe Customer Portal (gestionar
    #: método de pago, ver facturas, cancelar/cambiar de nivel).
    CREATE_PORTAL_SESSION = "create_portal_session"
    #: Fase 13, hito 13.3 — consultar plan/estado de suscripción/uso del
    #: periodo de la propia clínica (apartado "Facturación" del frontend).
    READ_STATUS = "read_status"


#: Fase 13, hitos 13.1/13.3 (docs/fase-13-rfc.md §5). Mismo patrón "admin
#: únicamente" que `RetentionAction`/`IntegrationConfigAction`/
#: `InvitationAction`: dar de alta o gestionar la facturación de la
#: clínica es una tarea administrativa, ni siquiera `audiologist` puede
#: hacerlo.
BILLING_PERMISSIONS: dict[Role, frozenset[BillingAction]] = {
    Role.ADMIN: frozenset(BillingAction),
    Role.AUDIOLOGIST: frozenset(),
    Role.VIEWER: frozenset(),
}


def authorize_billing_action(current_user: CurrentUser, action: BillingAction) -> None:
    if action not in BILLING_PERMISSIONS[current_user.role]:
        raise ForbiddenError(
            f"El rol '{current_user.role.value}' no tiene permiso para "
            f"'{action.value}' sobre facturación."
        )


def authorize_invitation_action(
    current_user: CurrentUser, action: InvitationAction, *, clinic_id: uuid.UUID
) -> None:
    """`clinic_id` es el `{clinic_id}` de la ruta (`.../clinics/{clinic_id}/
    invitations...`) — comprobado además del rol porque, a diferencia del
    resto de endpoints del proyecto (que derivan la clínica implícitamente
    de `current_user.clinic_id`, sin parámetro en la URL), aquí el RFC
    pide la clínica explícita en la ruta. Un admin solo puede
    invitar/consultar/revocar invitaciones de SU PROPIA clínica: si el id
    de la ruta no coincide, se trata como el mismo tipo de violación de
    propiedad que `authorize_clinical_session_action` (`ForbiddenError`,
    no `NotFoundError` — la clínica sí existe, simplemente no es la
    suya)."""
    if action not in INVITATION_PERMISSIONS[current_user.role]:
        raise ForbiddenError(
            f"El rol '{current_user.role.value}' no tiene permiso para "
            f"'{action.value}' sobre invitaciones."
        )
    if clinic_id != current_user.clinic_id:
        raise ForbiddenError("Un admin solo puede operar sobre invitaciones de su propia clínica.")
