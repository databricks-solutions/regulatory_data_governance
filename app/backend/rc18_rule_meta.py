"""RC18 rule metadata — hard-coded mapping keyed by DQX check `name`.

The DQX Studio rule storage (`dq_quality_rules`) carries only minimal user
tags (`projeto`, `descricao`). The structural metadata that drives the
Críticas SCR / Qualidade R.18 UI (critica_id, dimensão R.18, nível de
verificação, documento alvo) lives here so the YAML tags can stay clean
while the backend still produces rich responses.

When new rules are authored via DQX Studio, they will NOT have an entry here
and will fall back to safe defaults (dim=0/"Outras", nivel=1, document
derived from `table_fqn`).
"""

from __future__ import annotations

from typing import TypedDict


class RuleMeta(TypedDict):
    critica_id: str        # BACEN-style identifier surfaced as rule_id in the UI
    dimension_r18: int     # 1..12 per docs/spec/01_requirements.md §1.2
    dimension_name: str    # PT-BR display name
    nivel_verificacao: int # 1=syntactic, 2=inter_document, 3=business
    document: str          # '3040' | '3050' | ''
    rule_type: str         # 'syntactic' | 'semantic' | 'inter_document' | 'business'


_DIM_NAMES = {
    1: "Acessibilidade", 2: "Acurácia", 3: "Adaptabilidade", 4: "Clareza",
    5: "Comparabilidade", 6: "Completude", 7: "Confiabilidade", 8: "Consistência",
    9: "Integridade", 10: "Rastreabilidade", 11: "Relevância", 12: "Tempestividade",
}


# Single source of truth for the 4 initial RC18 rules.
RC18_RULE_META: dict[str, RuleMeta] = {
    "autorzc_in_dominio": {
        "critica_id":        "S20_001",
        "dimension_r18":     3,
        "dimension_name":    _DIM_NAMES[3],
        "nivel_verificacao": 1,
        "document":          "3040",
        "rule_type":         "syntactic",
    },
    "porte_cli_in_dominio_por_tipo": {
        "critica_id":        "S20_002",
        "dimension_r18":     3,
        "dimension_name":    _DIM_NAMES[3],
        "nivel_verificacao": 1,
        "document":          "3040",
        "rule_type":         "syntactic",
    },
    "tp_ctrl_in_dominio": {
        "critica_id":        "S20_003",
        "dimension_r18":     3,
        "dimension_name":    _DIM_NAMES[3],
        "nivel_verificacao": 1,
        "document":          "3040",
        "rule_type":         "syntactic",
    },
    "dia_atraso_nao_negativo": {
        "critica_id":        "S10_004",
        "dimension_r18":     2,
        "dimension_name":    _DIM_NAMES[2],
        "nivel_verificacao": 1,
        "document":          "3040",
        "rule_type":         "syntactic",
    },
}


_DEFAULT_META: RuleMeta = {
    "critica_id":        "",
    "dimension_r18":     0,
    "dimension_name":    "Outras",
    "nivel_verificacao": 1,
    "document":          "",
    "rule_type":         "syntactic",
}

# Backwards-compat only: rules authored before the Arabic-numeral convention
# may still carry Roman 'I'..'XII' in `user_metadata.dimensao_r18`. New rules
# should use Arabic '1'..'12' (see `_parse_dim_r18`).
_ROMAN_TO_INT = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
                 "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}


def _parse_dim_r18(value) -> int | None:
    """Parse an authored `dimensao_r18` tag into a 1..12 int, or None.

    Preferred authoring form is an Arabic numeral (int or string) '1'..'12'.
    Roman numerals 'I'..'XII' are still accepted for rules authored before the
    convention changed. Anything else (blank, out-of-range, junk) → None, which
    leaves the caller's baseline dimension untouched.
    """
    raw = str(value if value is not None else "").strip().upper()
    if not raw:
        return None
    if raw.isdigit():
        n = int(raw)
        return n if 1 <= n <= 12 else None
    return _ROMAN_TO_INT.get(raw)


def meta_for(
    check_name: str | None,
    *,
    table_fqn: str = "",
    user_metadata: dict | None = None,
) -> RuleMeta:
    """Resolve structural metadata for a rule.

    Resolution order for `dimension_r18` (authoritative → fallback):
      1. `user_metadata.dimensao_r18` — an Arabic numeral '1'..'12' (Roman
         'I'..'XII' still accepted for legacy rules). Authored on the DQX
         Studio rule; this is the source of truth.
      2. `RC18_RULE_META[check_name]` hard-coded entry (covers the 4 initial
         RC18 rules even if the tag is missing — backwards compat).
      3. Default = 0 ("Outras").

    Other fields (critica_id, nivel_verificacao, document, rule_type) still
    come from `RC18_RULE_META` since the user opted for keeping DQX Studio
    tags lean. New rules added via the Studio receive sensible defaults.
    """
    # Start from the hard-coded baseline (covers all fields with sane defaults).
    if check_name and check_name in RC18_RULE_META:
        out: RuleMeta = {**RC18_RULE_META[check_name]}
    else:
        out = {**_DEFAULT_META}
        if "scr3040" in (table_fqn or "").lower():
            out["document"] = "3040"
        elif "scr3050" in (table_fqn or "").lower():
            out["document"] = "3050"

    # Authoritative override from user_metadata if a valid dimension is present.
    if user_metadata:
        dim_int = _parse_dim_r18(user_metadata.get("dimensao_r18"))
        if dim_int:
            out["dimension_r18"] = dim_int
            out["dimension_name"] = _DIM_NAMES[dim_int]

    return out
