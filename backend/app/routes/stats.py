"""Product-wide statistics: the model calls the pre-check and caches avoided."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.savings import savings

router = APIRouter(prefix="/api/stats", tags=["stats"])

# Rough list prices used only for the dollar estimate; the counts are exact.
DEFAULT_GENERATION_COST_USD = 0.04
DEFAULT_EVALUATION_COST_USD = 0.002


@router.get("/savings")
async def get_savings(
    generationCost: float = Query(DEFAULT_GENERATION_COST_USD, ge=0),
    evaluationCost: float = Query(DEFAULT_EVALUATION_COST_USD, ge=0),
) -> dict:
    return await savings(generation_cost=generationCost, evaluation_cost=evaluationCost)
