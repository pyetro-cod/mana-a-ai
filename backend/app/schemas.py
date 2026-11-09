import re
from datetime import datetime
from typing import Optional, Literal, List

from pydantic import BaseModel, Field, field_validator

# Letters (any language), digits, spaces and common punctuation. Rejects <, >, quotes
# and backticks, so a stored name can never be turned into HTML/JS by some other screen.
NOME_PERMITIDO = re.compile(r"^[\w\s.,()\-/&+%ºª]+$")
TELEFONE = re.compile(r"^\d{10,11}$")


def validar_nome(valor: str) -> str:
    valor = valor.strip()
    if not NOME_PERMITIDO.fullmatch(valor):
        raise ValueError("use apenas letras, números, espaços e . , ( ) - / & + %")
    return valor


def validar_telefone(valor: str) -> str:
    if not TELEFONE.fullmatch(valor):
        raise ValueError("telefone deve ter 10 ou 11 dígitos, só números (DDD + número)")
    return valor


class ProdutoCreate(BaseModel):
    nome: str = Field(..., min_length=2, max_length=80)
    valor_creditos: int = Field(..., gt=0)

    @field_validator("nome")
    @classmethod
    def nome_valido(cls, v):
        return validar_nome(v)


class ProdutoUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=2, max_length=80)
    valor_creditos: Optional[int] = Field(None, gt=0)

    @field_validator("nome")
    @classmethod
    def nome_valido(cls, v):
        return v if v is None else validar_nome(v)


class ProdutoOut(BaseModel):
    id: str
    nome: str
    valor_creditos: int

    class Config:
        from_attributes = True


class ClienteCreate(BaseModel):
    nome: str = Field(..., min_length=2, max_length=120)
    telefone: str = Field(..., min_length=10, max_length=11)

    @field_validator("nome")
    @classmethod
    def nome_valido(cls, v):
        return validar_nome(v)

    @field_validator("telefone")
    @classmethod
    def telefone_valido(cls, v):
        return validar_telefone(v)


class LoginRequest(BaseModel):
    telefone: str = Field(..., min_length=10, max_length=11)
    senha: str = Field(..., min_length=8)


class LoginResponse(BaseModel):
    token: str
    perfil: str


class SolicitarCodigoRequest(BaseModel):
    telefone: str

    @field_validator("telefone")
    @classmethod
    def telefone_valido(cls, v):
        return validar_telefone(v)


class EntrarClienteRequest(BaseModel):
    telefone: str
    codigo: str = Field(..., pattern=r"^\d{6}$")
    # Only needed the first time, when the phone has no account yet.
    nome: Optional[str] = Field(None, min_length=2, max_length=120)
    aceite_termos: bool = False

    @field_validator("telefone")
    @classmethod
    def telefone_valido(cls, v):
        return validar_telefone(v)

    @field_validator("nome")
    @classmethod
    def nome_valido(cls, v):
        return v if v is None else validar_nome(v)


class EntrarClienteResponse(BaseModel):
    token: str
    novo_cadastro: bool


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
    motivo: str
    criado_em: datetime
    produto_id: Optional[str] = None

    class Config:
        from_attributes = True


class ExtratoOut(BaseModel):
    saldo: int
    # When the current balance expires (None if there is nothing to expire).
    vence_em: Optional[datetime] = None
    historico: List[HistoricoItem]


class UsarCupomRequest(BaseModel):
    # What the QR encodes. Case and surrounding spaces are normalised before lookup.
    codigo: str = Field(..., min_length=6, max_length=32, pattern=r"^\s*[A-Za-z0-9-]+\s*$")

    @field_validator("codigo")
    @classmethod
    def normalizar(cls, v):
        return v.strip().upper()


class UsarCupomOut(BaseModel):
    creditos: int
    bonus: int
    expirado: int
    novo_saldo: int
    vence_em: Optional[datetime] = None