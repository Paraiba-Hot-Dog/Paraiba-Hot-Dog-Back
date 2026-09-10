from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.clientes.model import Cliente
    from src.produtos.model import ProdutoAdicional, ProdutoVariacao
    from src.unidades.model import Unidade


class StatusPedido(str, Enum):
    aberto = "aberto"
    pago = "pago"
    cancelado = "cancelado"


class StatusItemPedido(str, Enum):
    aberto = "aberto"
    preparando = "preparando"
    entregue = "entregue"
    cancelado = "cancelado"


class FormaPagamento(str, Enum):
    pix = "pix"
    credito = "credito"
    debito = "debito"
    dinheiro = "dinheiro"


class Pedido(Base):
    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), nullable=False)
    nome_comanda: Mapped[str] = mapped_column(String(120), nullable=False)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), nullable=True)
    status: Mapped[StatusPedido] = mapped_column(
        SQLEnum(StatusPedido, name="status_conta_pedido"),
        default=StatusPedido.aberto,
        nullable=False,
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    desconto_fidelidade: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    forma_pagamento: Mapped[FormaPagamento | None] = mapped_column(
        SQLEnum(FormaPagamento, name="forma_pagamento"),
        nullable=True,
    )
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    pontos_fidelidade_utilizados: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pontos_fidelidade_creditados: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),  # pylint: disable=not-callable
        nullable=False,
    )
    fechado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    unidade: Mapped[Unidade] = relationship("Unidade", lazy="joined")
    cliente: Mapped[Cliente | None] = relationship("Cliente", lazy="joined")
    itens: Mapped[list[ItemPedido]] = relationship(
        "ItemPedido",
        back_populates="pedido",
        cascade="all, delete-orphan",
    )


class ItemPedido(Base):
    __tablename__ = "itens_pedido"

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id"), nullable=False)
    produto_variacao_id: Mapped[int] = mapped_column(ForeignKey("produto_variacoes.id"), nullable=False)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    produto_nome: Mapped[str] = mapped_column(String(255), nullable=False)
    produto_variacao_nome: Mapped[str | None] = mapped_column(String(80), nullable=True)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    preco_unitario: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[StatusItemPedido] = mapped_column(
        SQLEnum(StatusItemPedido, name="status_cozinha_item_pedido"),
        default=StatusItemPedido.aberto,
        nullable=False,
    )
    lote: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    motivo_cancelamento: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),  # pylint: disable=not-callable
        nullable=False,
    )

    pedido: Mapped[Pedido] = relationship("Pedido", back_populates="itens")
    produto_variacao: Mapped[ProdutoVariacao] = relationship("ProdutoVariacao", lazy="joined")
    adicionais: Mapped[list[ItemPedidoAdicional]] = relationship(
        "ItemPedidoAdicional",
        back_populates="item",
        cascade="all, delete-orphan",
    )


class ItemPedidoAdicional(Base):
    __tablename__ = "item_pedido_adicionais"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_pedido_id: Mapped[int] = mapped_column(ForeignKey("itens_pedido.id"), nullable=False)
    adicional_id: Mapped[int | None] = mapped_column(ForeignKey("produto_adicionais.id"), nullable=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    preco: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    item: Mapped[ItemPedido] = relationship("ItemPedido", back_populates="adicionais")
    adicional: Mapped[ProdutoAdicional | None] = relationship("ProdutoAdicional", lazy="joined")
