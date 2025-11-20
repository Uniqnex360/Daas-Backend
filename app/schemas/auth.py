from pydantic import BaseModel, EmailStr, validator
from typing import Optional
from uuid import UUID
class UserCreate(BaseModel):
    email:EmailStr
    password:str
    first_name:str
    last_name:str
    tenant_id:Optional[UUID]=None
    
    @validator('password')
    def validate_password(cls,v):
        if(len(v)<8):
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper()for c in v):
            raise ValueError("Password must contain uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain lowercase letter")
        if not any(c.isdigit()for c in v):
            raise ValueError("Password must contain digit")
        return v
class UserLogin(BaseModel):
    email:EmailStr
    password:str
class Token(BaseModel):
    access_token:str 
    token_type:str='bearer'
class UserResponse(BaseModel):
    id:UUID
    email:str
    first_name:str
    last_name:str
    role:str
    tenant_id:Optional[UUID]
    is_active:bool  

class Config:
    from_attributes=True
    

    