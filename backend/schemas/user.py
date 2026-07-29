from pydantic import BaseModel, Field, field_validator
from typing import Optional
from uuid import UUID
import re

class UserBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str
    phone: str = Field(..., description="Phone number with country code, e.g. +919000000000")
    age: int = Field(..., ge=0, le=120)
    gender: str = Field(..., description="Male, Female, or Other")
    preferred_language: str = Field("English")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        # Require phone number to start with '+' followed by 10 to 15 digits
        if not re.match(r"^\+\d{10,15}$", v):
            raise ValueError("Phone number must start with '+' followed by 10 to 15 digits (e.g., +919000000000)")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        # Standard email pattern validation
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", v):
            raise ValueError("Invalid email format")
        return v.lower()

class UserRegister(UserBase):
    password: str = Field(..., min_length=6, max_length=100)

class UserResponse(BaseModel):
    id: UUID
    name: str
    email: str
    phone: str
    role: str
    age: Optional[int] = None
    gender: Optional[str] = None
    preferred_language: str

    class Config:
        from_attributes = True
