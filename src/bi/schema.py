from decimal import Decimal

from pydantic import BaseModel


class BiKpiRead(BaseModel):
    receita_bruta: Decimal
    lucro_liquido: Decimal
    ticket_medio: Decimal
    total_pedidos: int
    variacao_receita_bruta: Decimal
    variacao_lucro_liquido: Decimal
    variacao_ticket_medio: Decimal
    variacao_total_pedidos: Decimal


class BiVendaHoraRead(BaseModel):
    hora: str
    quantidade: int
    destaque: bool = False


class BiProdutoRead(BaseModel):
    rank: int
    produto_id: int
    nome: str
    quantidade: int
    receita: Decimal
    variacao: Decimal


class BiMixProdutoRead(BaseModel):
    nome: str
    percentual: Decimal


class BiDestaqueRead(BaseModel):
    nome: str
    margem_ganho: Decimal
    margem_liquida: Decimal


class BiDashboardRead(BaseModel):
    kpis: BiKpiRead
    vendas_por_hora: list[BiVendaHoraRead]
    top_produtos: list[BiProdutoRead]
    mix_produtos: list[BiMixProdutoRead]
    vendas_totais: Decimal
    pedidos_registrados: int
    destaque: BiDestaqueRead | None = None
