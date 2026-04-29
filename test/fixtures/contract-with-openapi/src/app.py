from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class LoginReq(BaseModel):
    email: str
    password: str

@app.post("/auth/login")
def login(req: LoginReq):
    if req.email == "user@test.com" and req.password == "pass":
        return {"token": "fake-jwt-token"}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/users")
def list_users():
    return {
        "items": [{"id": 1, "email": "user@test.com", "name": "Alice"}],
        "total": 1
    }
