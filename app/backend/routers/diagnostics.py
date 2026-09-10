"""Diagnóstico de pré-requisitos. Sem cache: cada GET é uma verificação nova."""

from __future__ import annotations

from fastapi import APIRouter

from diagnostics import PrereqReport, run_prereq_checks

router = APIRouter()


@router.get("/prereqs", response_model=PrereqReport)
async def get_prereqs() -> PrereqReport:
    """Estado dos acessos externos. Chamado só quando uma tela vem vazia."""
    return await run_prereq_checks()
