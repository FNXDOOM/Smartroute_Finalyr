from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class UserBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: str = Field(..., min_length=3, max_length=320)
    phone: Optional[str] = Field("", max_length=40)
    role: Optional[str] = "passenger"


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    email: Optional[str] = Field(None, min_length=3, max_length=320)
    phone: Optional[str] = Field(None, max_length=40)

class UserResponse(UserBase):
    id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
