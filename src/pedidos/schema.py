from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from src.pedidos.model import FormaPagamento, StatusItemPedido, StatusPedido


class ItemPedidoAdicionalRead(BaseModel):
    id: int
    adicional_id: Optional[int] = None
    nome: str
    preco: Decimal

    model_config = ConfigDict(from_attributes=True)


class ItemPedidoCreate(BaseModel):
    produto_variacao_id: int = Field(..., gt=0)
    quantidade: int = Field(..., gt=0)
    observacao: Optional[str] = None
    adicional_ids: list[int] = []


class ItemPedidoRead(BaseModel):
    id: int
    pedido_id: int
    produto_variacao_id: int
    produto_id: int
    produto_nome: str
    produto_variacao_nome: Optional[str] = None
    quantidade: int
    preco_unitario: Decimal
    observacao: Optional[str] = None
    status: StatusItemPedido
    lote: int
    motivo_cancelamento: Optional[str] = None
    cancelado_em: Optional[datetime] = None
    created_at: datetime
    adicionais: list[ItemPedidoAdicionalRead] = []

    model_config = ConfigDict(from_attributes=True)


class PedidoCreate(BaseModel):
    unidade_id: int = Field(..., gt=0)
    nome_comanda: str = Field(..., min_length=1, max_length=120)
    cliente_id: Optional[int] = Field(None, gt=0)
    observacao: Optional[str] = None
    usar_desconto_fidelidade: bool = False
    itens: list[ItemPedidoCreate] = []


class PedidoRead(BaseModel):
    id: int
    unidade_id: int
    nome_comanda: str
    cliente_id: Optional[int] = None
    status: StatusPedido
    subtotal: Decimal
    desconto_fidelidade: Decimal
    total: Decimal
    forma_pagamento: Optional[FormaPagamento] = None
    observacao: Optional[str] = None
    pontos_fidelidade_utilizados: int
    pontos_fidelidade_creditados: bool
    created_at: datetime
    fechado_em: Optional[datetime] = None
    itens: list[ItemPedidoRead] = []

    model_config = ConfigDict(from_attributes=True)


class PedidoFiltro(BaseModel):
    unidade_id: Optional[int] = Field(None, gt=0)
    status: Optional[StatusPedido] = None
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, gt=0, le=100)


class AdicionarItensPedido(BaseModel):
    itens: list[ItemPedidoCreate] = Field(..., min_length=1)


class CancelarItemPedido(BaseModel):
    motivo_cancelamento: str = Field(..., min_length=1)
    quantidade: Optional[int] = Field(None, gt=0)


class AumentarQuantidadeItemPedido(BaseModel):
    quantidade: int = Field(default=1, gt=0)


class CancelarPedido(BaseModel):
    motivo_cancelamento: str = Field(..., min_length=1)


class FinalizarPedido(BaseModel):
    forma_pagamento: FormaPagamento


class CozinhaAdicionalRead(BaseModel):
    adicional_id: Optional[int] = None
    nome: str
    preco: Decimal


class CozinhaItemRead(BaseModel):
    pedido_id: int
    nome_comanda: str
    lote: int
    produto_variacao_id: int
    produto_id: int
    produto_nome: str
    produto_variacao_nome: Optional[str] = None
    observacao: Optional[str] = None
    status: StatusItemPedido
    quantidade: int
    adicionais: list[CozinhaAdicionalRead] = []


class AtualizarStatusCozinha(BaseModel):
    pedido_id: int = Field(..., gt=0)
    lote: int = Field(..., gt=0)
    status: StatusItemPedido
