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
        # Printed as ABCDE-FGHJK for readability; the stored code has no hyphen.
        return v.strip().upper().replace("-", "")


class UsarCupomOut(BaseModel):
    creditos: int
    bonus: int
    expirado: int
    novo_saldo: int
    vence_em: Optional[datetime] = None


# ---------- admin: regras do programa ----------

class ConfiguracaoOut(BaseModel):
    creditos_por_cupom: int
    bonus_boas_vindas: int
    validade_cupom_dias: int
    dias_expiracao_saldo: int
    validade_resgate_minutos: int
    max_cupons_por_dia: int
    atualizado_em: datetime

    class Config:
        from_attributes = True


class ConfiguracaoUpdate(BaseModel):
    """Each field is optional; the bounds stop a typo (e.g. 5000 credits) from going live."""
    creditos_por_cupom: Optional[int] = Field(None, ge=1, le=1000)
    bonus_boas_vindas: Optional[int] = Field(None, ge=0, le=1000)
    validade_cupom_dias: Optional[int] = Field(None, ge=1, le=365)
    dias_expiracao_saldo: Optional[int] = Field(None, ge=1, le=365)
    validade_resgate_minutos: Optional[int] = Field(None, ge=1, le=60)
    max_cupons_por_dia: Optional[int] = Field(None, ge=1, le=10)


# ---------- admin: lotes de cupons ----------

class LoteCreate(BaseModel):
    quantidade: int = Field(..., ge=1, le=200)


class LoteOut(BaseModel):
    id: str
    quantidade: int
    creditos: int
    criado_em: datetime
    expira_em: datetime
    usados: int
    cancelado: bool


class CupomImpressao(BaseModel):
    codigo: str          # grouped for humans: ABCDE-FGHJK
    url: str             # what the QR encodes
    qr: str              # data:image/svg+xml URI, safe to use as <img src>
    usado: bool


class LoteDetalhe(LoteOut):
    cupons: List[CupomImpressao]


# ---------- admin: prêmios ----------

class PremioCreate(BaseModel):
    nome: str = Field(..., min_length=2, max_length=80)
    custo_creditos: int = Field(..., ge=1, le=100000)

    @field_validator("nome")
    @classmethod
    def nome_valido(cls, v):
        return validar_nome(v)


class PremioUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=2, max_length=80)
    custo_creditos: Optional[int] = Field(None, ge=1, le=100000)
    ativo: Optional[bool] = None

    @field_validator("nome")
    @classmethod
    def nome_valido(cls, v):
        return v if v is None else validar_nome(v)


class PremioOut(BaseModel):
    id: str
    nome: str
    custo_creditos: int
    ativo: bool

    class Config:
        from_attributes = True


# ---------- resgate de prêmio ----------

class SolicitarResgateRequest(BaseModel):
    premio_id: str = Field(..., min_length=1, max_length=64)


class ResgateOut(BaseModel):
    """What the customer shows at the counter."""
    codigo: str
    premio: str
    custo_creditos: int
    expira_em: datetime
    novo_saldo: int


class CancelarResgateOut(BaseModel):
    devolvido: int
    novo_saldo: int


class ResgateCaixaOut(BaseModel):
    """What the cashier sees before handing over the prize."""
    codigo: str
    cliente: str
    premio: str
    custo_creditos: int
    expira_em: datetime
    status: str
