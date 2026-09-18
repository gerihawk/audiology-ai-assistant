"""Tests de `app/core/field_encryption.py` (Fase 12, cifrado a nivel de
campo — ver docs/privacy-and-security.md §4 y docs/eipd-dpia.md, riesgo
R9). Tres bloques: (1) `FieldCipher`/`parse_keys_env` como unidades
puras, sin base de datos ni Settings; (2) round-trip transparente de los
`TypeDecorator` (`EncryptedString`/`EncryptedInt`/`EncryptedJSON`) contra
la base de datos de test real, vía los mismos factories que usa el resto
de la suite; (3) `field_encryption_cli.main()` end-to-end, mismo patrón
de integración que test_retention_cli.py — verifica en concreto que
`flag_modified` (ver el docstring de `_reencrypt_table`) hace que el
re-cifrado tras una rotación de clave activa ocurra de verdad, no solo
que el código no lance ninguna excepción."""

from __future__ import annotations

import base64
import os
import secrets

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.field_encryption import (
    FieldCipher,
    FieldEncryptionError,
    get_field_cipher,
    parse_keys_env,
)
from app.core.field_encryption_cli import main as run_field_encryption_cli
from app.patients.domain.entities import Patient
from app.patients.infrastructure.orm import PatientORM
from tests.factories import (
    ClinicWithUsers,
    create_ai_artifact_with_version,
    create_clinical_session,
    create_patient,
)


def _b64_key() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


# --- FieldCipher / parse_keys_env: unidades puras ------------------------


def test_encrypt_decrypt_roundtrip() -> None:
    cipher = FieldCipher(keys={"1": secrets.token_bytes(32)}, active_key_id="1")

    token = cipher.encrypt(b"contenido clinico sensible")

    assert cipher.decrypt(token) == b"contenido clinico sensible"


def test_encrypt_is_non_deterministic_nonce() -> None:
    # Requisito documentado en EncryptedString/EncryptedJSON: el nonce
    # aleatorio hace que el mismo texto claro nunca produzca el mismo
    # ciphertext dos veces — por eso no se puede filtrar/ordenar en SQL.
    cipher = FieldCipher(keys={"1": secrets.token_bytes(32)}, active_key_id="1")

    token_a = cipher.encrypt(b"mismo valor")
    token_b = cipher.encrypt(b"mismo valor")

    assert token_a != token_b
    assert cipher.decrypt(token_a) == cipher.decrypt(token_b) == b"mismo valor"


def test_token_is_prefixed_with_active_key_id() -> None:
    cipher = FieldCipher(keys={"2026a": secrets.token_bytes(32)}, active_key_id="2026a")

    token = cipher.encrypt(b"x")

    assert token.startswith("2026a:")


def test_old_key_still_decrypts_after_rotation() -> None:
    # Simula el runbook de rotación de field_encryption_cli.py: una clave
    # vieja sigue descifrando aunque ya no sea la activa.
    key_old = secrets.token_bytes(32)
    key_new = secrets.token_bytes(32)
    cipher_before_rotation = FieldCipher(keys={"1": key_old}, active_key_id="1")
    token = cipher_before_rotation.encrypt(b"escrito antes de rotar")

    cipher_after_rotation = FieldCipher(keys={"1": key_old, "2": key_new}, active_key_id="2")

    assert cipher_after_rotation.decrypt(token) == b"escrito antes de rotar"
    # Y lo nuevo ya usa la clave activa nueva.
    assert cipher_after_rotation.encrypt(b"escrito tras rotar").startswith("2:")


def test_decrypt_unknown_key_id_raises() -> None:
    cipher = FieldCipher(keys={"1": secrets.token_bytes(32)}, active_key_id="1")

    with pytest.raises(FieldEncryptionError, match="clave con id"):
        cipher.decrypt("clave-retirada:AAAA")


def test_decrypt_malformed_token_raises() -> None:
    cipher = FieldCipher(keys={"1": secrets.token_bytes(32)}, active_key_id="1")

    with pytest.raises(FieldEncryptionError, match="separador"):
        cipher.decrypt("sin-separador-de-key-id")


def test_decrypt_tampered_ciphertext_raises() -> None:
    # Autenticación GCM: manipular un solo byte del ciphertext debe hacer
    # fallar la verificación del tag, nunca devolver un valor parcial.
    cipher = FieldCipher(keys={"1": secrets.token_bytes(32)}, active_key_id="1")
    token = cipher.encrypt(b"dato original")
    key_id, payload = token.split(":", 1)
    raw = bytearray(base64.b64decode(payload))
    raw[-1] ^= 0xFF  # flip del último byte (dentro del tag GCM)
    tampered = f"{key_id}:{base64.b64encode(bytes(raw)).decode('ascii')}"

    with pytest.raises(FieldEncryptionError, match="descifrar"):
        cipher.decrypt(tampered)


def test_constructor_rejects_empty_keys() -> None:
    with pytest.raises(FieldEncryptionError):
        FieldCipher(keys={}, active_key_id="1")


def test_constructor_rejects_active_key_not_in_keys() -> None:
    with pytest.raises(FieldEncryptionError, match="ACTIVE_KEY_ID"):
        FieldCipher(keys={"1": secrets.token_bytes(32)}, active_key_id="2")


def test_constructor_rejects_wrong_key_length() -> None:
    with pytest.raises(FieldEncryptionError, match="32"):
        FieldCipher(keys={"1": secrets.token_bytes(16)}, active_key_id="1")


def test_parse_keys_env_multiple_entries() -> None:
    raw_a, raw_b = secrets.token_bytes(32), secrets.token_bytes(32)
    encoded = f"1:{base64.b64encode(raw_a).decode()},2:{base64.b64encode(raw_b).decode()}"

    parsed = parse_keys_env(encoded)

    assert parsed == {"1": raw_a, "2": raw_b}


def test_parse_keys_env_rejects_missing_colon() -> None:
    with pytest.raises(FieldEncryptionError):
        parse_keys_env("1-sin-separador")


def test_parse_keys_env_rejects_invalid_base64() -> None:
    with pytest.raises(FieldEncryptionError):
        parse_keys_env("1:no-es-base64-valido-!!")


def test_parse_keys_env_ignores_blank_entries() -> None:
    key = secrets.token_bytes(32)

    parsed = parse_keys_env(f"1:{base64.b64encode(key).decode()},,")

    assert parsed == {"1": key}


# --- Round-trip transparente vía los TypeDecorator, contra la BD real ----


async def test_patient_display_name_and_birth_year_round_trip_through_db(
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
) -> None:
    patient: Patient = await create_patient(
        db_session, clinic_with_users.clinic.id, clinic_with_users.admin.id
    )

    # Vía ORM (a través del TypeDecorator): descifrado transparente, se ve
    # el valor de dominio normal.
    assert patient.display_name == "Paciente de test"
    assert patient.birth_year == 1980

    # Vía SQL crudo (sin pasar por el TypeDecorator): la columna NO debe
    # contener el texto plano ni el año en claro, sino el formato
    # "<key_id>:<base64>" de field_encryption.py.
    raw_display_name, raw_birth_year = (
        await db_session.execute(
            text("SELECT display_name, birth_year FROM patients WHERE id = :id"),
            {"id": str(patient.id)},
        )
    ).one()
    assert raw_display_name != "Paciente de test"
    assert "Paciente de test" not in raw_display_name
    assert ":" in raw_display_name
    assert raw_birth_year != "1980"


async def test_ai_artifact_version_content_round_trips_as_dict(
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
) -> None:
    clinical_session = await create_clinical_session(
        db_session,
        clinic_with_users.clinic.id,
        patient.id,
        clinic_with_users.audiologist.id,
        clinic_with_users.admin.id,
    )
    artifact = await create_ai_artifact_with_version(
        db_session, clinic_with_users.clinic.id, clinical_session.id, clinic_with_users.admin.id
    )

    raw_content = (
        await db_session.execute(
            text("SELECT content FROM ai_artifact_versions WHERE id = :id"),
            {"id": str(artifact.current_version_id)},
        )
    ).scalar_one()
    # Ya no es JSON en claro: es "<key_id>:<base64>", y desde luego no
    # contiene la clave de negocio "text" del dict original de la factory.
    assert "Contenido ficticio de test." not in raw_content
    assert raw_content.split(":", 1)[0].isalnum()


# --- field_encryption_cli.py: rotación end-to-end -------------------------


async def test_cli_reencrypts_rows_under_new_active_key_via_flag_modified(
    test_engine: AsyncEngine,
    db_session: AsyncSession,
    clinic_with_users: ClinicWithUsers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reproduce el runbook de rotación completo (ver el docstring de
    field_encryption_cli.py): un paciente escrito con la clave "1" activa
    debe terminar re-cifrado bajo la clave "2" tras rotar
    FIELD_ENCRYPTION_ACTIVE_KEY_ID y ejecutar el CLI — y seguir
    descifrando al mismo valor de dominio de siempre. Esto es justo lo
    que confirma que el `flag_modified()` de `_reencrypt_table` hace
    efecto de verdad: sin él, SQLAlchemy consideraría la columna "sin
    cambios" (mismo valor Python antes/después) y el UPDATE nunca
    llegaría a re-cifrar nada."""
    original_keys = os.environ["FIELD_ENCRYPTION_KEYS"]
    monkeypatch.setenv("FIELD_ENCRYPTION_KEYS", f"{original_keys},2:{_b64_key()}")
    # La clave activa sigue siendo "1" en este punto: así el paciente se
    # crea con algo pendiente de re-cifrar bajo la "2".
    get_settings.cache_clear()
    get_field_cipher.cache_clear()

    patient = await create_patient(
        db_session, clinic_with_users.clinic.id, clinic_with_users.admin.id
    )
    raw_before = (
        await db_session.execute(
            text("SELECT display_name FROM patients WHERE id = :id"), {"id": str(patient.id)}
        )
    ).scalar_one()
    assert raw_before.startswith("1:")

    monkeypatch.setenv("FIELD_ENCRYPTION_ACTIVE_KEY_ID", "2")
    get_settings.cache_clear()
    get_field_cipher.cache_clear()
    try:
        test_session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
        summary = await run_field_encryption_cli(test_session_factory)

        assert summary["patients"]["filas_recifradas"] == 1

        raw_after = (
            await db_session.execute(
                text("SELECT display_name FROM patients WHERE id = :id"),
                {"id": str(patient.id)},
            )
        ).scalar_one()
        assert raw_after.startswith("2:")

        # Sesión nueva (no reutiliza el objeto Python ya cargado en
        # `db_session`) para confirmar que el valor de dominio sigue
        # siendo correcto tras la rotación, ahora cifrado con la clave
        # nueva.
        fresh_session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
        async with fresh_session_factory() as fresh_session:
            reloaded = await fresh_session.get(PatientORM, patient.id)
            assert reloaded is not None
            assert reloaded.display_name == "Paciente de test"
    finally:
        # `monkeypatch` revierte las env vars automáticamente al terminar
        # el test, pero el caché de get_settings()/get_field_cipher()
        # (ambos @lru_cache) no se entera solo — sin este clear, el resto
        # de la suite seguiría viendo la clave "2" añadida aquí.
        get_settings.cache_clear()
        get_field_cipher.cache_clear()
