from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from .auth import verify_token

router = APIRouter(prefix="/users")

users_store = {
    1: {"id": 1, "email": "user@test.com", "name": "Alice", "role": "user"},
    2: {"id": 2, "email": "admin@test.com", "name": "Bob", "role": "admin"}
}


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


def get_user_or_404(user_id: int):
    user = users_store.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/")
def list_users(token_data: dict = Depends(verify_token)):
    return {"items": list(users_store.values()), "total": len(users_store)}


@router.get("/{user_id}")
def get_user(user_id: int, token_data: dict = Depends(verify_token)):
    return get_user_or_404(user_id)


@router.put("/{user_id}")
def update_user(user_id: int, update: UserUpdate, token_data: dict = Depends(verify_token)):
    user = get_user_or_404(user_id)
    requesting_user_id = int(token_data["sub"])
    if requesting_user_id != user_id and token_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    if update.name:
        user["name"] = update.name
    if update.email:
        user["email"] = update.email
    return user


@router.delete("/{user_id}")
def delete_user(user_id: int, token_data: dict = Depends(verify_token)):
    if token_data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    get_user_or_404(user_id)
    del users_store[user_id]
    return {"deleted": user_id}
