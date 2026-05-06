"""HTTP routes — split from main.py so api-test/contract-test skills find them easily."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field

from app.auth import create_token, decode_token
from app.calc import apply_discount, calc_tax, total_with_tax
from app.users import store

api = APIRouter(prefix="/api", tags=["api"])
bearer = HTTPBearer(auto_error=False)


class RegisterReq(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class LoginReq(BaseModel):
    email: EmailStr
    password: str


class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResp(BaseModel):
    id: int
    email: str
    name: str
    role: str


class CalcReq(BaseModel):
    price: float = Field(ge=0)
    discount_pct: float = Field(ge=0, le=100, default=0)
    tax_rate: float = Field(ge=0, le=1, default=0.17)


class CalcResp(BaseModel):
    discounted: float
    tax: float
    total: float


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        payload = decode_token(creds.credentials)
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    user = store.get(int(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return user


@api.post("/register", response_model=UserResp, status_code=201)
def register(req: RegisterReq) -> UserResp:
    try:
        user = store.create(req.email, req.name, req.password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return UserResp(**user.public())


@api.post("/login", response_model=TokenResp)
def login(req: LoginReq) -> TokenResp:
    user = store.authenticate(req.email, req.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    return TokenResp(access_token=create_token(user.id, user.role))


@api.get("/me", response_model=UserResp)
def me(user=Depends(current_user)) -> UserResp:
    return UserResp(**user.public())


@api.get("/users", response_model=list[UserResp])
def list_users(user=Depends(current_user)) -> list[UserResp]:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return [UserResp(**u.public()) for u in store.list()]


@api.get("/users/{user_id}", response_model=UserResp)
def get_user(user_id: int, user=Depends(current_user)) -> UserResp:
    if user.role != "admin" and user.id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "cannot read other users")
    target = store.get(user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return UserResp(**target.public())


@api.post("/calc/quote", response_model=CalcResp)
def calc_quote(req: CalcReq) -> CalcResp:
    discounted = apply_discount(req.price, req.discount_pct)
    tax = calc_tax(discounted, req.tax_rate)
    return CalcResp(
        discounted=discounted,
        tax=tax,
        total=total_with_tax(req.price, req.discount_pct, req.tax_rate),
    )


@api.get("/health")
def health() -> dict:
    return {"status": "ok"}
