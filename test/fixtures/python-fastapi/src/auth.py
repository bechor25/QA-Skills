from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
from pydantic import BaseModel
import os

router = APIRouter(prefix="/auth")
pwd_context = CryptContext(schemes=["bcrypt"])
security = HTTPBearer()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")
ALGORITHM = "HS256"

fake_users_db = {
    "user@test.com": {
        "id": 1,
        "email": "user@test.com",
        "hashed_password": pwd_context.hash("TestPass1!"),
        "role": "user"
    },
    "admin@test.com": {
        "id": 2,
        "email": "admin@test.com",
        "hashed_password": pwd_context.hash("AdminPass1!"),
        "role": "admin"
    }
}


class LoginRequest(BaseModel):
    email: str
    password: str


def create_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/login")
def login(request: LoginRequest):
    user = fake_users_db.get(request.email)
    if not user or not pwd_context.verify(request.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(user["id"], user["role"])
    return {"token": token, "user_id": user["id"]}


@router.get("/me")
def get_me(token_data: dict = Depends(verify_token)):
    return {"user_id": token_data["sub"], "role": token_data["role"]}
