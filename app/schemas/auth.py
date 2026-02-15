from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    token: str
    name: str
    password: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
