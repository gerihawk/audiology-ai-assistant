"""Regresión de metadata (no del evaluator) — regla de diseño del Golden
Dataset acordada en el diagnóstico post-mortem de la ronda de benchmark
del 2026-08-12:

- `forbidden_facts` es para contenido fabricado/imposible cuya detección
  por simple presencia textual NO puede coincidir con ninguna formulación
  legítima (p. ej. "diagnóstico confirmado", un resultado de prueba
  inventado).
- `negation_cases` es para conceptos que SÍ forman parte del caso y cuya
  polaridad (negada/afirmada) hay que preservar (p. ej. vértigo, alergias
  medicamentosas, cirugía ótica negada).
- Un concepto de `negation_cases` NUNCA debe duplicarse como
  `forbidden_fact` mediante un patrón genérico cuya simple presencia
  pueda darse en una formulación correctamente polarizada — `
  evaluate_forbidden_facts` es (deliberadamente, encargo Fase 6.2 §5, "no
  heurísticas frágiles para hallucination semántica") un simple *substring
  match* sin noción de polaridad, así que un patrón sin marca de polaridad
  (p. ej. "cirugía") puede aparecer igual en una mención afirmada
  ("cirugía de oído") o en una negada con redacción no anticipada por los
  patrones de ejemplo declarados ("sin cirugía ótica previa") — visto en
  vivo con Opus 5 en la ronda post-mortem: el patrón "cirugía" no
  coincidía textualmente con ninguna de las frases `negated` declaradas
  para `ear_surgery`, pero SÍ con su frase `affirmed` declarada
  ("cirugía de oído"), lo que prueba que el patrón pertenece al mismo
  concepto — por eso la comprobación de abajo consulta TODAS las ramas de
  polaridad declaradas de cada `negation_case`, no solo la esperada.

Reutiliza el mismo matching que usa `evaluate_forbidden_facts` en
producción (`_matches_any`/`_padded` de `benchmark.generation.metrics`)
para que esta comprobación nunca diverja de lo que el evaluator real
haría — determinista, sin LLM, sin NLP clínico, sin heurísticas de
distancia de palabras: solo los patrones ya declarados en `metadata.json`."""

from __future__ import annotations

import json
from pathlib import Path

from benchmark.dataset_metadata import NegationCase
from benchmark.generation.case_metadata import GenerationCaseMetadata
from benchmark.generation.dataset import list_generation_case_ids, load_generation_case
from benchmark.generation.metrics import _matches_any, _padded, evaluate_required_facts
from benchmark.metrics.negation import evaluate_negations

_REAL_DATASET_DIR = Path(__file__).resolve().parent.parent / "benchmark" / "generation_dataset"


def _find_contradictions(metadata: GenerationCaseMetadata) -> list[tuple[str, str, str]]:
    """Devuelve `(concepto, patrón_declarado_del_negation_case,
    patrón_forbidden)` por cada combinación donde un `forbidden_fact`
    comparte vocabulario con un concepto ya modelado en `negation_cases` —
    consultando TODAS las ramas de polaridad declaradas (`patterns.values()`,
    no solo `patterns[expected]`), porque un patrón de mera presencia no
    lleva marca de polaridad y el propio catálogo de frases de ejemplo del
    negation_case (afirmadas + negadas) es la única fuente determinista
    disponible sin inventar variantes nuevas."""
    contradictions: list[tuple[str, str, str]] = []
    for neg_case in metadata.negation_cases:
        declared_patterns = [p for plist in neg_case.patterns.values() for p in plist]
        for declared_pattern in declared_patterns:
            haystack = _padded(declared_pattern)
            for forbidden in metadata.forbidden_facts:
                match = _matches_any(haystack, forbidden.patterns)
                if match is not None:
                    contradictions.append((neg_case.concept, declared_pattern, match))
    return contradictions


def _all_real_cases():
    case_ids = list_generation_case_ids(_REAL_DATASET_DIR)
    assert case_ids, "el dataset real de generación no debería estar vacío"
    return [load_generation_case(_REAL_DATASET_DIR, case_id) for case_id in case_ids]


def _all_real_case_metadata() -> list[GenerationCaseMetadata]:
    return [case.metadata for case in _all_real_cases() if case.metadata is not None]


class TestNegationForbiddenFactsConsistency:
    def test_ningun_caso_real_tiene_contradiccion_negacion_forbidden(self):
        for metadata in _all_real_case_metadata():
            contradictions = _find_contradictions(metadata)
            assert not contradictions, (
                f"'{metadata.id}' tiene forbidden_facts que comparten vocabulario con un "
                f"concepto ya modelado en negation_cases: {contradictions}"
            )

    def test_forbidden_facts_genuinos_siguen_presentes_summary(self):
        case = load_generation_case(_REAL_DATASET_DIR, "consulta_ficticia_01__summary")
        assert case.metadata is not None
        descriptions = [f.description for f in case.metadata.forbidden_facts]
        assert any("diagnóstico confirmado" in d for d in descriptions)
        # vértigo, alergias y cirugía ótica se retiraron de forbidden_facts
        # por completo — quedan gobernados en exclusiva por negation_cases.
        assert not any("vértigo" in d.lower() for d in descriptions)
        assert not any("alergias" in d.lower() for d in descriptions)
        assert not any("cirugía" in d.lower() for d in descriptions)
        concepts = [c.concept for c in case.metadata.negation_cases]
        assert "vertigo" in concepts
        assert "drug_allergies" in concepts
        assert "ear_surgery" in concepts

    def test_forbidden_facts_genuinos_siguen_presentes_patient_summary(self):
        case = load_generation_case(_REAL_DATASET_DIR, "consulta_ficticia_01__patient_summary")
        assert case.metadata is not None
        descriptions = [f.description for f in case.metadata.forbidden_facts]
        assert any("diagnóstico" in d for d in descriptions)
        assert any("audífonos" in d for d in descriptions)
        assert not any("vértigo" in d.lower() for d in descriptions)
        concepts = [c.concept for c in case.metadata.negation_cases]
        assert "vertigo" in concepts

    def test_missing_information_no_tiene_negation_cases_ni_contradiccion(self):
        case = load_generation_case(_REAL_DATASET_DIR, "consulta_ficticia_01__missing_information")
        assert case.metadata is not None
        assert case.metadata.negation_cases == []
        # sin negation_cases no puede haber contradicción — su forbidden_facts
        # (no marcar temas como ausentes) es de otra naturaleza y debe seguir intacto.
        assert len(case.metadata.forbidden_facts) == 4

    def test_ear_surgery_affirmed_detecta_inversion_de_polaridad(self):
        """La rama `affirmed` de `ear_surgery` (que ahora es la ÚNICA fuente
        de verdad para este concepto, tras retirar el forbidden_fact
        genérico) debe seguir detectando de forma determinista una
        inversión real de polaridad — sin necesidad de ningún forbidden_fact
        adicional."""
        case = load_generation_case(_REAL_DATASET_DIR, "consulta_ficticia_01__summary")
        assert case.metadata is not None
        ear_surgery = next(c for c in case.metadata.negation_cases if c.concept == "ear_surgery")
        report = evaluate_negations(
            "Antecedentes: me han operado de los oídos hace dos años.",
            [ear_surgery],
        )
        assert report.failed == 1
        assert report.details[0].result == "fail"


class TestNegationPolarityRegression:
    """Casos mínimos pedidos explícitamente: una formulación afirmada debe
    seguir detectándose como inversión de polaridad por `evaluate_negations`,
    y una formulación negada (con la redacción real que motivó esta ronda,
    no solo los patrones de ejemplo) no debe generar ningún hallazgo de
    alucinación por mera presencia — porque el forbidden_fact genérico
    correspondiente ya no existe en metadata."""

    @staticmethod
    def _metadata():
        case = load_generation_case(_REAL_DATASET_DIR, "consulta_ficticia_01__summary")
        assert case.metadata is not None
        return case.metadata

    @staticmethod
    def _negation_case(metadata: GenerationCaseMetadata, concept: str) -> NegationCase:
        return next(c for c in metadata.negation_cases if c.concept == concept)

    def _forbidden_hits(self, metadata: GenerationCaseMetadata, text: str) -> list[str]:
        haystack = _padded(text)
        hits = []
        for forbidden in metadata.forbidden_facts:
            match = _matches_any(haystack, forbidden.patterns)
            if match is not None:
                hits.append(forbidden.description)
        return hits

    def test_vertigo_afirmado_falla_negation_case(self):
        # El texto debe contener el patrón `affirmed` declarado literalmente
        # ("he tenido vértigo") — evaluate_negations es substring puro, sin
        # comprensión gramatical; una redacción distinta como "Refiere
        # vértigo." no coincide con ningún patrón declarado y da
        # `not_detected`, no `fail`.
        metadata = self._metadata()
        vertigo = self._negation_case(metadata, "vertigo")
        report = evaluate_negations("El paciente indica que he tenido vértigo.", [vertigo])
        assert report.failed == 1
        assert report.details[0].result == "fail"

    def test_vertigo_negado_pasa_y_sin_falso_positivo_de_hallucination(self):
        metadata = self._metadata()
        vertigo = self._negation_case(metadata, "vertigo")
        text = "El paciente indica: no vértigo, solo mareos esporádicos sin relevancia."
        report = evaluate_negations(text, [vertigo])
        assert report.passed == 1
        assert report.failed == 0
        assert self._forbidden_hits(metadata, text) == []

    def test_alergias_afirmadas_polaridad_incorrecta(self):
        metadata = self._metadata()
        drug_allergies = self._negation_case(metadata, "drug_allergies")
        report = evaluate_negations("Tiene alergias medicamentosas.", [drug_allergies])
        assert report.failed == 1
        assert report.details[0].result == "fail"

    def test_alergias_negadas_polaridad_correcta_sin_forbidden_fact_falso(self):
        # Contiene literalmente el patrón `negated` declarado ("sin alergias")
        # — "No tiene alergias conocidas." contendría el patrón `affirmed`
        # ("tiene alergias") como substring y se clasificaría "fail", no
        # "pass": el evaluador no entiende la negación gramatical "No", solo
        # busca los fragmentos declarados.
        metadata = self._metadata()
        drug_allergies = self._negation_case(metadata, "drug_allergies")
        text = "Antecedentes: sin alergias medicamentosas conocidas."
        report = evaluate_negations(text, [drug_allergies])
        assert report.passed == 1
        assert report.failed == 0
        assert self._forbidden_hits(metadata, text) == []

    def test_ear_surgery_afirmado_declarado_polaridad_incorrecta(self):
        metadata = self._metadata()
        ear_surgery = self._negation_case(metadata, "ear_surgery")
        report = evaluate_negations("Antecedentes: me han operado de los oídos.", [ear_surgery])
        assert report.failed == 1
        assert report.details[0].result == "fail"

    def test_ear_surgery_negado_tres_formulaciones_sin_disparar_hallucination(self):
        metadata = self._metadata()
        # La primera es la redacción real de Opus 5 que motivó esta ronda —
        # no está entre los patrones `negated` de ejemplo declarados, y aun
        # así no debe generar ningún finding: ya no existe ningún
        # forbidden_fact con "cirugía"/"operado"/"intervención".
        for text in (
            "Sin cirugía ótica previa.",
            "Nunca me han operado de los oídos.",
            "No ha sido operado.",
        ):
            assert (
                self._forbidden_hits(metadata, text) == []
            ), f"'{text}' no debería disparar ningún forbidden_fact"

    def test_diagnostico_confirmado_inventado_sigue_detectandose(self):
        metadata = self._metadata()
        hits = self._forbidden_hits(
            metadata, "Diagnóstico confirmado de hipoacusia neurosensorial bilateral."
        )
        assert any("diagnóstico confirmado" in h for h in hits)

    def test_forbidden_fact_generico_existente_sigue_detectandose(self):
        # Cualquier forbidden_fact genuino restante en metadata (no ligado a
        # polaridad) debe seguir disparando por simple presencia, tal y como
        # antes de esta corrección — aquí, con los datos reales de
        # metadata.json en vez de un ejemplo hardcodeado en el test.
        metadata = self._metadata()
        for forbidden in metadata.forbidden_facts:
            pattern = forbidden.patterns[0]
            hits = self._forbidden_hits(metadata, f"Contexto de prueba: {pattern}.")
            assert forbidden.description in hits


class TestGlobalPolarityAudit:
    """Auditoría global determinista sobre TODA la metadata versionada del
    dataset — sin LLM, sin NLP clínico, sin heurísticas de distancia de
    palabras. Vuelve a cargar los JSON en crudo (no solo vía el loader) para
    que la auditoría no dependa de la forma en que `case_metadata.py`
    interprete el fichero, y deja constancia explícita del resultado por
    caso en el propio nombre del assert."""

    def test_auditoria_global_cero_contradicciones_en_los_tres_casos(self):
        resultados = {}
        for case in _all_real_cases():
            if case.metadata is None:
                continue
            resultados[case.metadata.id] = _find_contradictions(case.metadata)

        assert set(resultados) == {
            "consulta_ficticia_01__summary",
            "consulta_ficticia_01__patient_summary",
            "consulta_ficticia_01__missing_information",
        }
        for case_id, contradictions in resultados.items():
            assert not contradictions, f"{case_id}: {contradictions}"

    def test_metadata_json_en_crudo_no_declara_ya_los_patrones_retirados(self):
        # Cinturón y tirantes: confirma contra el JSON crudo (no el loader)
        # que los 3 patrones retirados en esta ronda ya no están en
        # forbidden_facts de ninguno de los dos ficheros afectados.
        retirados = {
            "consulta_ficticia_01__summary": [
                "vértigo",
                "mareos frecuentes",
                "alergias",
                "operado",
                "cirugía",
                "intervención quirúrgica",
            ],
            "consulta_ficticia_01__patient_summary": ["vértigo"],
        }
        for case_id, patrones in retirados.items():
            raw = json.loads((_REAL_DATASET_DIR / case_id / "metadata.json").read_text("utf-8"))
            todos_los_patrones = {
                p for fact in raw.get("forbidden_facts", []) for p in fact.get("patterns", [])
            }
            for patron in patrones:
                assert (
                    patron not in todos_los_patrones
                ), f"{case_id}: '{patron}' debería haberse retirado de forbidden_facts"


class TestAcufenoVarianteMorfologica:
    """`acúfeno` (singular) añadido a `required_facts` de SUMMARY —
    respaldado por la propia Golden Reference humana ("Refiere acúfeno
    constante", singular) — diagnóstico post-mortem 2026-08-12. No es un
    sinónimo inventado: es la misma redacción que ya usa la referencia."""

    @staticmethod
    def _metadata() -> GenerationCaseMetadata:
        case = load_generation_case(_REAL_DATASET_DIR, "consulta_ficticia_01__summary")
        assert case.metadata is not None
        return case.metadata

    @staticmethod
    def _acufenos_fact(metadata: GenerationCaseMetadata):
        return next(fc for fc in metadata.required_facts if "acúfenos/pitidos" in fc.description)

    def test_singular_acufeno_reconocido(self):
        fact = self._acufenos_fact(self._metadata())
        result = evaluate_required_facts("Refiere acúfeno constante.", [fact])
        assert result.present == 1

    def test_plural_acufenos_sigue_reconocido(self):
        fact = self._acufenos_fact(self._metadata())
        result = evaluate_required_facts("Refiere acúfenos constantes.", [fact])
        assert result.present == 1

    def test_pitido_singular_sigue_reconocido(self):
        fact = self._acufenos_fact(self._metadata())
        result = evaluate_required_facts("Refiere un pitido constante.", [fact])
        assert result.present == 1

    def test_pitidos_plural_sigue_reconocido(self):
        fact = self._acufenos_fact(self._metadata())
        result = evaluate_required_facts("Refiere pitidos constantes.", [fact])
        assert result.present == 1

    def test_no_introduce_forbidden_fact_falso(self):
        # "acúfeno" no aparece en ningún forbidden_fact de SUMMARY — la
        # adición no puede convertirse en un falso "hecho prohibido".
        metadata = self._metadata()
        haystack = _padded("Refiere acúfeno constante.")
        for forbidden in metadata.forbidden_facts:
            assert _matches_any(haystack, forbidden.patterns) is None

    def test_no_rompe_ningun_negation_case(self):
        # SUMMARY no tiene negation_case para acúfenos/tinnitus — la
        # adición no puede colisionar con ninguno de los 4 existentes
        # (vertigo, ear_surgery, other_medication, drug_allergies).
        metadata = self._metadata()
        concepts = {c.concept for c in metadata.negation_cases}
        assert "acufeno" not in concepts
        assert "tinnitus" not in concepts

    def test_no_hay_nueva_contradiccion_global(self):
        # La auditoría global genérica (misma que el resto de la ronda)
        # sigue en cero tras esta adición.
        for metadata in _all_real_case_metadata():
            assert _find_contradictions(metadata) == []

    def test_conceptos_no_relacionados_sin_cambios(self):
        # Ningún otro required_fact de SUMMARY se ha tocado.
        metadata = self._metadata()
        descriptions = [fc.description for fc in metadata.required_facts]
        assert len(descriptions) == 7
        assert "pérdida auditiva progresiva de varios meses" in " ".join(descriptions)
