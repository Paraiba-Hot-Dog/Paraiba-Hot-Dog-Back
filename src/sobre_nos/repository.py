"""Operacoes de banco de dados para Sobre Nos e carrossel."""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.sobre_nos.model import SobreNos, SobreNosImagem
from src.sobre_nos.schema import (
    SobreNosImagemCreate,
    SobreNosImagemUpdate,
    SobreNosUpdate,
)

TEXTO_PADRAO = (
    "Nascemos da paixão pela gastronomia de rua e pelo sabor autêntico da Paraíba. "
    "Desde 2015, levamos o melhor hot dog arretado para os brasilenses com qualidade, "
    "fartura e tradição. Nossa missão é servir ingredientes frescos, receitas exclusivas "
    "e um atendimento que faz você se sentir em casa."
)

ESTATISTICAS_PADRAO = [
    {"valor": "10+", "legenda": "Anos de funcionamento"},
    {"valor": "4,9", "legenda": "Avaliação média"},
    {"valor": "3", "legenda": "Unidades"},
]


def obter_sobre_nos(db: Session) -> SobreNos:
    """Retorna o registro unico de Sobre Nos, criando o padrao caso nao exista."""
    conteudo = db.query(SobreNos).filter(SobreNos.id == 1).first()
    if not conteudo:
        conteudo = SobreNos(
            id=1,
            texto=TEXTO_PADRAO,
            estatisticas=ESTATISTICAS_PADRAO,
        )
        db.add(conteudo)
        db.commit()
        db.refresh(conteudo)
    return conteudo


def atualizar_sobre_nos(db: Session, data: SobreNosUpdate) -> SobreNos:
    """Atualiza o texto institucional e os cards de estatisticas de Sobre Nos."""
    conteudo = obter_sobre_nos(db)
    conteudo.texto = data.texto
    conteudo.estatisticas = [item.model_dump() for item in data.estatisticas]
    db.commit()
    db.refresh(conteudo)
    return conteudo


def listar_imagens(db: Session) -> list[SobreNosImagem]:
    """Lista as imagens do carrossel ordenadas pelo campo ordem."""
    return (
        db.query(SobreNosImagem)
        .order_by(SobreNosImagem.ordem.asc(), SobreNosImagem.id.asc())
        .all()
    )


def criar_imagem(db: Session, data: SobreNosImagemCreate) -> SobreNosImagem:
    """Adiciona uma nova imagem ao final do carrossel."""
    proxima_ordem = (
        db.query(SobreNosImagem.ordem).order_by(SobreNosImagem.ordem.desc()).first()
    )
    ordem = (proxima_ordem[0] + 1) if proxima_ordem else 0
    nova_imagem = SobreNosImagem(
        imagem_url=data.imagem_url,
        posicao=data.posicao,
        ordem=ordem,
    )
    db.add(nova_imagem)
    db.commit()
    db.refresh(nova_imagem)
    return nova_imagem


def obter_imagem(db: Session, imagem_id: int) -> SobreNosImagem:
    """Busca uma imagem pelo ID ou lanca 404."""
    imagem = db.query(SobreNosImagem).filter(SobreNosImagem.id == imagem_id).first()
    if not imagem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Imagem nao encontrada",
        )
    return imagem


def atualizar_imagem(
    db: Session, imagem_id: int, data: SobreNosImagemUpdate
) -> SobreNosImagem:
    """Atualiza ordem e/ou posicao de uma imagem existente."""
    imagem = obter_imagem(db, imagem_id)
    if data.ordem is not None:
        imagem.ordem = data.ordem
    if data.posicao is not None:
        imagem.posicao = data.posicao
    db.commit()
    db.refresh(imagem)
    return imagem


def excluir_imagem(db: Session, imagem_id: int) -> None:
    """Remove uma imagem do banco de dados."""
    imagem = obter_imagem(db, imagem_id)
    db.delete(imagem)
    db.commit()
