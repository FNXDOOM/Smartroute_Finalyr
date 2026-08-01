from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    name: str
    email: str
    phone: Optional[str] = ""
    role: Optional[str] = "passenger"


class UserCreate(UserBase):
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

class UserResponse(UserBase):
    id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Optional[UserResponse] = None


class TokenData(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None
    role: Optional[str] = None
