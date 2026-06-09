"""Model provider/account routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from app.core.deps import DbSession, get_current_user
from app.models.user import User
from app.schemas.model_account import (
    CreateModelAccountRequest,
    ModelAccountListOut,
    ModelAccountOut,
    ModelAccountVerifyOut,
    ModelProviderListOut,
    UpdateModelAccountRequest,
)
from app.services.model_accounts import (
    account_is_used_by_agent,
    create_model_account,
    get_user_model_account,
    list_model_accounts,
    persist_verification_result,
    provider_list,
    update_model_account,
    validate_provider_payload,
    verify_model_account,
)

router = APIRouter()


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "MODEL_ACCOUNT_NOT_FOUND", "message": "Model account not found"}},
    )


@router.get("/model-providers", response_model=ModelProviderListOut)
async def list_model_providers(
    _user: Annotated[User, Depends(get_current_user)],
) -> ModelProviderListOut:
    return ModelProviderListOut(items=provider_list())


@router.get("/model-accounts", response_model=ModelAccountListOut)
async def list_accounts(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> ModelAccountListOut:
    accounts = await list_model_accounts(db, user_id=user.id)
    return ModelAccountListOut(
        items=[ModelAccountOut.model_validate(item) for item in accounts]
    )


@router.post("/model-accounts", response_model=ModelAccountOut, status_code=201)
async def create_account(
    payload: CreateModelAccountRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> ModelAccountOut:
    try:
        account = await create_model_account(
            db,
            user_id=user.id,
            display_name=payload.display_name,
            provider=payload.provider,
            api_key=payload.api_key,
            model=payload.model,
            base_url=payload.base_url,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "INVALID_MODEL_ACCOUNT", "message": str(exc)}},
        ) from exc
    return ModelAccountOut.model_validate(account)


@router.patch("/model-accounts/{account_id}", response_model=ModelAccountOut)
async def update_account(
    account_id: UUID,
    payload: UpdateModelAccountRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> ModelAccountOut:
    account = await get_user_model_account(db, user_id=user.id, account_id=account_id)
    if account is None:
        raise _not_found()
    try:
        if payload.base_url is not None:
            validate_provider_payload(account.provider, payload.base_url)
        account = await update_model_account(
            db,
            account,
            display_name=payload.display_name,
            api_key=payload.api_key,
            model=payload.model,
            base_url=payload.base_url,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "INVALID_MODEL_ACCOUNT", "message": str(exc)}},
        ) from exc
    return ModelAccountOut.model_validate(account)


@router.delete("/model-accounts/{account_id}", status_code=204)
async def delete_account(
    account_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    account = await get_user_model_account(db, user_id=user.id, account_id=account_id)
    if account is None:
        raise _not_found()
    if await account_is_used_by_agent(db, user_id=user.id, account_id=account_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "MODEL_ACCOUNT_IN_USE",
                    "message": "This model account is still used by one or more Agents.",
                }
            },
        )
    await db.delete(account)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/model-accounts/{account_id}/verify", response_model=ModelAccountVerifyOut)
async def verify_account(
    account_id: UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> ModelAccountVerifyOut:
    account = await get_user_model_account(db, user_id=user.id, account_id=account_id)
    if account is None:
        raise _not_found()
    status_, error = await verify_model_account(account)
    account = await persist_verification_result(db, account, status=status_, error=error)
    return ModelAccountVerifyOut(
        status=account.status,  # type: ignore[arg-type]
        error=account.last_error,
        verified_at=account.last_verified_at,
    )
