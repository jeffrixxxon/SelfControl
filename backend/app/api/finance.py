from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user
from ..db import get_session
from ..models import Budget, Debt, Receipt, Transaction, User
from ..services import core
from ..timeutils import local_month_bounds, parse_local

router = APIRouter(tags=["finance"])


class TransactionIn(BaseModel):
    kind: str = Field("expense", pattern="^(expense|income)$")
    amount: float = Field(gt=0)
    category: str = "Прочее"
    description: str | None = None
    merchant: str | None = None
    occurred_at: str | None = None


class BudgetIn(BaseModel):
    category: str | None = None
    monthly_limit: float = Field(gt=0)


class DebtIn(BaseModel):
    direction: str = Field(pattern="^(i_owe|owed_to_me)$")
    counterparty: str
    amount: float = Field(gt=0)
    due_date: date | None = None
    note: str | None = None


class PaymentIn(BaseModel):
    amount: float = Field(gt=0)


@router.get("/categories")
async def categories():
    return {"expense": core.EXPENSE_CATEGORIES, "income": core.INCOME_CATEGORIES}


@router.get("/transactions")
async def list_transactions(
    year: int | None = None, month: int | None = None, kind: str | None = None,
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session),
):
    start, end = local_month_bounds(user, year, month)
    q = select(Transaction).where(Transaction.user_id == user.id, Transaction.occurred_at >= start,
                                  Transaction.occurred_at < end)
    if kind:
        q = q.where(Transaction.kind == kind)
    rows = (await session.scalars(q.order_by(Transaction.occurred_at.desc()))).all()
    return [core.to_dict(t) for t in rows]


@router.post("/transactions")
async def create_transaction(data: TransactionIn, user: User = Depends(current_user),
                             session: AsyncSession = Depends(get_session)):
    payload = data.model_dump()
    payload["occurred_at"] = parse_local(user, data.occurred_at)
    return core.to_dict(await core.add_transaction(session, user, **payload))


@router.delete("/transactions/{tx_id}")
async def delete_transaction(tx_id: int, user: User = Depends(current_user),
                             session: AsyncSession = Depends(get_session)):
    t = await core.get_owned(session, Transaction, user, tx_id)
    if not t:
        raise HTTPException(404)
    await session.delete(t)
    await session.commit()
    return {"ok": True}


@router.get("/finance/summary")
async def finance_summary(year: int | None = None, month: int | None = None,
                          user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    return await core.month_finance(session, user, year, month)


@router.get("/receipts")
async def list_receipts(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = (await session.scalars(
        select(Receipt).where(Receipt.user_id == user.id).order_by(Receipt.purchased_at.desc()).limit(50)
    )).all()
    return [core.to_dict(r) for r in rows]


@router.get("/budgets")
async def list_budgets(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    return (await core.month_finance(session, user))["budgets"]


@router.post("/budgets")
async def upsert_budget(data: BudgetIn, user: User = Depends(current_user),
                        session: AsyncSession = Depends(get_session)):
    b = await session.scalar(select(Budget).where(Budget.user_id == user.id, Budget.category == data.category)
                             if data.category else
                             select(Budget).where(Budget.user_id == user.id, Budget.category.is_(None)))
    if b:
        b.monthly_limit = data.monthly_limit
        await session.commit()
    else:
        b = await core.add_simple(session, Budget, user, **data.model_dump())
    return core.to_dict(b)


@router.delete("/budgets/{budget_id}")
async def delete_budget(budget_id: int, user: User = Depends(current_user),
                        session: AsyncSession = Depends(get_session)):
    b = await core.get_owned(session, Budget, user, budget_id)
    if not b:
        raise HTTPException(404)
    await session.delete(b)
    await session.commit()
    return {"ok": True}


@router.get("/debts")
async def list_debts(include_closed: bool = False, user: User = Depends(current_user),
                     session: AsyncSession = Depends(get_session)):
    q = select(Debt).where(Debt.user_id == user.id)
    if not include_closed:
        q = q.where(Debt.closed.is_(False))
    rows = (await session.scalars(q.order_by(Debt.closed, Debt.due_date))).all()
    return [core.debt_dict(d) for d in rows]


@router.post("/debts")
async def create_debt(data: DebtIn, user: User = Depends(current_user),
                      session: AsyncSession = Depends(get_session)):
    return core.debt_dict(await core.add_debt(session, user, **data.model_dump()))


@router.post("/debts/{debt_id}/payments")
async def add_payment(debt_id: int, data: PaymentIn, user: User = Depends(current_user),
                      session: AsyncSession = Depends(get_session)):
    d = await core.get_owned(session, Debt, user, debt_id)
    if not d:
        raise HTTPException(404)
    return core.debt_dict(await core.pay_debt(session, user, d, data.amount))


@router.delete("/debts/{debt_id}")
async def delete_debt(debt_id: int, user: User = Depends(current_user),
                      session: AsyncSession = Depends(get_session)):
    d = await core.get_owned(session, Debt, user, debt_id)
    if not d:
        raise HTTPException(404)
    await session.delete(d)
    await session.commit()
    return {"ok": True}
