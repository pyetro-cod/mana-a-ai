from datetime import datetime
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    telefone: str = Field(..., min_length=10, max_length=11)
    senha: str = Field(..., min_length=8)


class LoginResponse(BaseModel):
    token: str
    perfil: str


class CarteiraOut(BaseModel):
    id: str
    saldo: int

    class Config:
        from_attributes = True


class ClienteOut(BaseModel):
    id: str
    nome: str
    telefone: str
    carteira: CarteiraOut

    class Config:
        from_attributes = True


class TransacaoCreate(BaseModel):
    carteira_id: str
    tipo: Literal["credito", "debito"]
    valor: int = Field(..., gt=0)
    produto_id: Optional[str] = None

    @field_validator("valor")
    @classmethod
    def valor_positivo(cls, v):
        if v <= 0:
            raise ValueError("valor deve ser um inteiro positivo")
        return v


class TransacaoOut(BaseModel):
    transacao_id: str
    novo_saldo: int


class HistoricoItem(BaseModel):
    tipo: str
    valor: int
    criado_em: datetime
    produto_id: Optional[str] = None

    class Config:
        from_attributes = True


class ExtratoOut(BaseModel):
    saldo: int
    historico: List[HistoricoItem]
