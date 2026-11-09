"""Área do dono (perfil admin): regras do programa, lotes de cupons e prêmios."""
import segno
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, regras, schemas
from ..auth_utils import get_admin_atual
from ..config import settings
from ..database import get_db

# Every route here requires an admin token; declaring it on the router means a new
# route cannot be added by mistake without the check.
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_admin_atual)])


# ---------- regras do programa ----------

@router.get("/configuracao", response_model=schemas.ConfiguracaoOut)
def ver_configuracao(db: Session = Depends(get_db)):
    return regras.configuracao(db)


@router.put("/configuracao", response_model=schemas.ConfiguracaoOut)
def editar_configuracao(payload: schemas.ConfiguracaoUpdate, db: Session = Depends(get_db)):
    """Muda as regras para o que vier daqui em diante (lotes já impressos mantêm o valor deles)."""
    config = regras.configuracao(db)
    for campo, valor in payload.model_dump(exclude_none=True).items():
        setattr(config, campo, valor)
    config.atualizado_em = regras.agora()
    db.commit()
    db.refresh(config)
    return config


# ---------- lotes de cupons ----------

def _usados_por_lote(db: Session) -> dict[str, int]:
    linhas = (db.query(models.Cupom.lote_id, func.count(models.Cupom.id))
              .filter(models.Cupom.usado_em.isnot(None))
              .group_by(models.Cupom.lote_id))
    return dict(linhas)


def _resumo(lote: models.LoteCupom, usados: int) -> dict:
    return {
        "id": lote.id,
        "quantidade": lote.quantidade,
        "creditos": lote.creditos,
        "criado_em": lote.criado_em,
        "expira_em": lote.expira_em,
        "usados": usados,
        "cancelado": lote.cancelado_em is not None,
    }


def _impressao(cupom: models.Cupom) -> schemas.CupomImpressao:
    url = f"{settings.app_public_url}/?cupom={cupom.codigo}"
    # Error level M survives a smudged or slightly torn print. The SVG is built by segno
    # from our own URL, and an <img> never runs scripts inside an SVG anyway.
    qr = segno.make(url, error="m").svg_data_uri(scale=4, border=2)
    return schemas.CupomImpressao(codigo=regras.formatar_codigo(cupom.codigo), url=url, qr=qr,
                                  usado=cupom.usado_em is not None)


def _buscar_lote(db: Session, lote_id: str) -> models.LoteCupom:
    lote = db.get(models.LoteCupom, lote_id)
    if lote is None:
        raise HTTPException(status_code=404, detail="Lote não encontrado")
    return lote


@router.get("/lotes", response_model=list[schemas.LoteOut])
def listar_lotes(db: Session = Depends(get_db)):
    usados = _usados_por_lote(db)
    lotes = db.query(models.LoteCupom).order_by(models.LoteCupom.criado_em.desc()).limit(50)
    return [_resumo(lote, usados.get(lote.id, 0)) for lote in lotes]


@router.post("/lotes", response_model=schemas.LoteDetalhe, status_code=201)
def gerar_lote(payload: schemas.LoteCreate, db: Session = Depends(get_db),
               admin: models.Usuario = Depends(get_admin_atual)):
    lote = regras.gerar_lote(db, admin, payload.quantidade)
    db.commit()
    return ver_lote(lote.id, db)


@router.get("/lotes/{lote_id}", response_model=schemas.LoteDetalhe)
def ver_lote(lote_id: str, db: Session = Depends(get_db)):
    """Lote com os QRs, pronto para a folha de impressão."""
    lote = _buscar_lote(db, lote_id)
    cupons = [_impressao(c) for c in sorted(lote.cupons, key=lambda c: c.codigo)]
    return {**_resumo(lote, sum(c.usado for c in cupons)), "cupons": cupons}


@router.post("/lotes/{lote_id}/cancelar", response_model=schemas.LoteOut)
def cancelar_lote(lote_id: str, db: Session = Depends(get_db)):
    """Folha perdida ou roubada: os cupons ainda não usados deixam de valer. Créditos já dados ficam."""
    lote = _buscar_lote(db, lote_id)
    if lote.cancelado_em is None:
        lote.cancelado_em = regras.agora()
        db.commit()
    return _resumo(lote, _usados_por_lote(db).get(lote.id, 0))


# ---------- prêmios ----------

@router.get("/premios", response_model=list[schemas.PremioOut])
def listar_premios(db: Session = Depends(get_db)):
    """Todos os prêmios, inclusive os desativados (o cliente só verá os ativos)."""
    return (db.query(models.Premio)
            .order_by(models.Premio.ativo.desc(), models.Premio.custo_creditos)
            .all())


@router.post("/premios", response_model=schemas.PremioOut, status_code=201)
def criar_premio(payload: schemas.PremioCreate, db: Session = Depends(get_db)):
    premio = models.Premio(estabelecimento_id=models.ESTABELECIMENTO_PADRAO,
                           nome=payload.nome, custo_creditos=payload.custo_creditos)
    db.add(premio)
    db.commit()
    db.refresh(premio)
    return premio


@router.put("/premios/{premio_id}", response_model=schemas.PremioOut)
def editar_premio(premio_id: str, payload: schemas.PremioUpdate, db: Session = Depends(get_db)):
    """Editar ou desativar. Não há exclusão: resgates antigos continuam apontando para o prêmio."""
    premio = db.get(models.Premio, premio_id)
    if premio is None:
        raise HTTPException(status_code=404, detail="Prêmio não encontrado")
    for campo, valor in payload.model_dump(exclude_none=True).items():
        setattr(premio, campo, valor)
    db.commit()
    db.refresh(premio)
    return premio
