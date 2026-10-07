from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


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


class BiVendaPeriodoRead(BaseModel):
    periodo: str
    receita_bruta: Decimal
    total_pedidos: int


class BiUnidadeRead(BaseModel):
    unidade_id: int
    nome: str
    total_pedidos: int
    receita_bruta: Decimal
    lucro_liquido: Decimal
    ticket_medio: Decimal
    participacao: Decimal


class BiClienteFidelidadeRead(BaseModel):
    cliente_id: int
    nome: str
    total_pedidos: int
    receita_bruta: Decimal
    pontos_atuais: int


class BiFidelidadeRead(BaseModel):
    pedidos_com_cliente: int
    percentual_pedidos_com_cliente: Decimal
    clientes_unicos: int
    pontos_resgatados: int
    descontos_concedidos: Decimal
    ticket_medio_com_cliente: Decimal
    ticket_medio_sem_cliente: Decimal
    top_clientes: list[BiClienteFidelidadeRead] = Field(default_factory=list)


class BiDashboardRead(BaseModel):
    kpis: BiKpiRead
    vendas_por_hora: list[BiVendaHoraRead]
    top_produtos: list[BiProdutoRead]
    mix_produtos: list[BiMixProdutoRead]
    vendas_totais: Decimal
    pedidos_registrados: int
    destaque: BiDestaqueRead | None = None
    agrupamento_periodo: Literal["dia", "mes"] = "dia"
    vendas_por_periodo: list[BiVendaPeriodoRead] = Field(default_factory=list)
    desempenho_unidades: list[BiUnidadeRead] = Field(default_factory=list)
    fidelidade: BiFidelidadeRead | None = None
