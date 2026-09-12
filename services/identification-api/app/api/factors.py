import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.calculations.factor_resolver import (
    AmbiguousFactorError,
    NoCompatibleFactorError,
    resolve_factor,
)
from app.persistence.database import get_db
from app.persistence.models import EmissionFactor
from app.schemas.factors import (
    FactorResolutionRequest,
    FactorResolutionResponse,
    FactorResponse,
    FactorSeedResponse,
)

router = APIRouter(prefix="/api", tags=["emission-factors"])
ROOT = Path(__file__).resolve().parents[4]
FACTOR_FILE = ROOT / "data/emission-factors/demo-factors.json"


def _date(value: str | None):
    return datetime.fromisoformat(value).replace(tzinfo=UTC) if value else None


def _scope(value: str) -> str | None:
    if "SCOPE_1" in value:
        return "SCOPE_1"
    if "SCOPE_2" in value:
        return "SCOPE_2"
    if "SCOPE_3" in value:
        return "SCOPE_3"
    return None


@router.post("/emission-factors/seed-demo", response_model=FactorSeedResponse)
async def seed_demo_factors(db: Annotated[AsyncSession, Depends(get_db)]):
    document = json.loads(FACTOR_FILE.read_text(encoding="utf-8"))
    inserted = existing = 0
    for item in document["factors"]:
        found = (
            await db.execute(
                select(EmissionFactor).where(
                    EmissionFactor.factor_code == item["factor_id"],
                    EmissionFactor.version == item["factor_version"],
                )
            )
        ).scalar_one_or_none()
        if found is not None:
            existing += 1
            continue
        db.add(
            EmissionFactor(
                factor_code=item["factor_id"],
                version=item["factor_version"],
                name=item["name"],
                source_category=item["activity_category"],
                scope=_scope(item["scope_or_boundary"]),
                factor_value=item["factor_value"],
                activity_unit=item["input_unit"],
                emission_unit=item["output_unit"],
                geography=item["geography"]["country"],
                valid_from=_date(item.get("valid_from")),
                valid_to=_date(item.get("valid_to")),
                source_organization=item.get("source_organization"),
                source_document=item.get("source_reference"),
                method=item.get("calculation_method"),
                quality_rating=item.get("quality_label"),
                metadata_json={
                    **item,
                    "registry_id": document["registry_id"],
                    "registry_version": document["registry_version"],
                },
            )
        )
        inserted += 1
    await db.flush()
    return FactorSeedResponse(
        registry_id=document["registry_id"],
        registry_version=document["registry_version"],
        inserted=inserted,
        existing=existing,
    )


@router.get("/emission-factors", response_model=list[FactorResponse])
async def list_factors(db: Annotated[AsyncSession, Depends(get_db)]):
    return list(
        (
            await db.execute(
                select(EmissionFactor).order_by(
                    EmissionFactor.factor_code, EmissionFactor.version
                )
            )
        )
        .scalars()
        .all()
    )


@router.get("/emission-factors/{factor_code}", response_model=list[FactorResponse])
async def read_factor(factor_code: str, db: Annotated[AsyncSession, Depends(get_db)]):
    factors = list(
        (
            await db.execute(
                select(EmissionFactor)
                .where(EmissionFactor.factor_code == factor_code)
                .order_by(EmissionFactor.version)
            )
        )
        .scalars()
        .all()
    )
    if not factors:
        raise HTTPException(404, "Emission factor not found")
    return factors


@router.post("/emission-factors/resolve", response_model=FactorResolutionResponse)
async def resolve(
    payload: FactorResolutionRequest, db: Annotated[AsyncSession, Depends(get_db)]
):
    factors = list((await db.execute(select(EmissionFactor))).scalars().all())
    try:
        factor = resolve_factor(factors, **payload.model_dump())
    except NoCompatibleFactorError as exc:
        raise HTTPException(422, str(exc)) from exc
    except AmbiguousFactorError as exc:
        raise HTTPException(409, str(exc)) from exc
    return FactorResolutionResponse(
        status="RESOLVED",
        reason="One active source, unit, date and geography-compatible factor matched.",
        factor=FactorResponse.model_validate(factor),
    )
