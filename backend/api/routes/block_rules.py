"""
Routes API pour les regles de blocage (pattern exact, prefixe, regex).
Inspire de callattendant BLOCK_NUMBER_PATTERNS / BLOCK_NAME_PATTERNS.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from backend.api.dependencies import get_block_rule_repository
from backend.api.models import BlockRuleResponse, BlockRuleCreate
from backend.repositories.block_rule_repository import BlockRuleRepository


router = APIRouter()


@router.get("/block-rules", response_model=List[BlockRuleResponse])
async def list_block_rules(
    block_rule_repo: BlockRuleRepository = Depends(get_block_rule_repository),
) -> List[BlockRuleResponse]:
    """
    Liste toutes les regles de blocage (actives et inactives).
    """
    rules = block_rule_repo.db.query(block_rule_repo.model).order_by(block_rule_repo.model.id).all()
    return [BlockRuleResponse.model_validate(r) for r in rules]


@router.post("/block-rules", response_model=BlockRuleResponse, status_code=201)
async def create_block_rule(
    payload: BlockRuleCreate,
    block_rule_repo: BlockRuleRepository = Depends(get_block_rule_repository),
) -> BlockRuleResponse:
    """
    Cree une regle de blocage (exact, prefix ou regex).
    """
    rule = block_rule_repo.create(
        name=payload.name,
        pattern=payload.pattern,
        pattern_type=payload.pattern_type,
        description=payload.description,
        is_active=True,
    )
    return BlockRuleResponse.model_validate(rule)


@router.delete("/block-rules/{rule_id}")
async def delete_block_rule(
    rule_id: int,
    block_rule_repo: BlockRuleRepository = Depends(get_block_rule_repository),
):
    """
    Supprime une regle de blocage.
    """
    if not block_rule_repo.delete(rule_id):
        raise HTTPException(status_code=404, detail="Regle non trouvee")
    return {"message": "Regle supprimee"}
