from datetime import datetime

import pytest

from src.analytics import ingestao, repository
from src.analytics.model import CanalAquisicao, EventoAnalytics, TipoEventoAnalytics
from src.analytics.schema import EscopoAquisicao, PeriodoAquisicao
from src.analytics.test_analytics_integracao import (
    AGORA,
    VERSAO_TESTE,
    _popular_exemplo_unidades,
    configurar_origem_site,
    fixture_cliente,
    fixture_db_session,
    fixture_outra_unidade,
    fixture_produto,
    fixture_unidade,
    override_get_db,
)
from src.main import app
from src.produtos.model import Produto
from src.security import get_current_user


def _criar_eventos(db_session, tipo: TipoEventoAnalytics, quantidade: int = 1, **campos):
    dados = {
        "primeiro_na_visita": True,
        "canal": CanalAquisicao.direto,
        "ocorrido_em": datetime(2026, 10, 26, 12),
        "versao_coleta": VERSAO_TESTE,
        **campos,
    }
    db_session.add_all(EventoAnalytics(tipo=tipo, **dados) for _ in range(quantidade))
    db_session.commit()


def _criar_produto(db_session, nome: str, subcategoria) -> Produto:
    produto = Produto(
        nome=nome,
        ativo=True,
        pontos_fidelidade_por_unidade=1,
        disponivel_todas_unidades=True,
        subcategoria=subcategoria,
    )
    db_session.add(produto)
    db_session.commit()
    return produto


def _origem(resultado) -> dict[CanalAquisicao, object]:
    return {linha.canal: linha for linha in resultado.origem}


def test_origem_por_canal_com_participacao_e_taxa(db_session):
    tipos = TipoEventoAnalytics
    _criar_eventos(db_session, tipos.visita_site, 6, canal=CanalAquisicao.instagram)
    _criar_eventos(db_session, tipos.visita_site, 2, canal=CanalAquisicao.qrcode)
    _criar_eventos(db_session, tipos.visita_site, 3, primeiro_na_visita=False, canal=CanalAquisicao.qrcode)
    _criar_eventos(db_session, tipos.clique_pedir, 3, canal=CanalAquisicao.instagram)
    _criar_eventos(db_session, tipos.clique_pedir, 2, primeiro_na_visita=False, canal=CanalAquisicao.instagram)

    resultado = repository.obter_analises_aquisicao(db_session, agora=AGORA)
    origem = _origem(resultado)

    assert list(origem) == list(CanalAquisicao)
    instagram, qrcode = origem[CanalAquisicao.instagram], origem[CanalAquisicao.qrcode]
    assert (instagram.visitantes, str(instagram.participacao)) == (6, "75.00")
    assert (instagram.cliques_pedir, str(instagram.taxa_visita_clique)) == (5, "50.00")
    assert (qrcode.visitantes, str(qrcode.participacao)) == (2, "25.00")
    assert (qrcode.cliques_pedir, str(qrcode.taxa_visita_clique)) == (0, "0.00")
    assert {linha.escopo_taxa for linha in resultado.origem} == {EscopoAquisicao.site}
    assert {linha.escopo_cliques for linha in resultado.origem} == {EscopoAquisicao.site}


def test_origem_canal_sem_visitas_aparece_zerado(db_session):
    _criar_eventos(db_session, TipoEventoAnalytics.visita_site, 4, canal=CanalAquisicao.instagram)

    busca = _origem(repository.obter_analises_aquisicao(db_session, agora=AGORA))[CanalAquisicao.busca]

    assert (busca.visitantes, busca.cliques_pedir) == (0, 0)
    assert str(busca.participacao) == "0.00"
    assert busca.taxa_visita_clique is None


def test_origem_sem_visitas_tem_participacao_indisponivel(db_session):
    resultado = repository.obter_analises_aquisicao(db_session, agora=AGORA)

    assert len(resultado.origem) == len(CanalAquisicao)
    assert {linha.participacao for linha in resultado.origem} == {None}
    assert {linha.taxa_visita_clique for linha in resultado.origem} == {None}


def test_origem_com_filtro_de_canal_mostra_so_o_canal(db_session):
    _criar_eventos(db_session, TipoEventoAnalytics.visita_site, 4, canal=CanalAquisicao.instagram)
    _criar_eventos(db_session, TipoEventoAnalytics.visita_site, 6, canal=CanalAquisicao.qrcode)

    resultado = repository.obter_analises_aquisicao(
        db_session, canal=CanalAquisicao.qrcode, agora=AGORA
    )

    [qrcode] = resultado.origem
    assert (qrcode.canal, qrcode.visitantes, str(qrcode.participacao)) == (
        CanalAquisicao.qrcode,
        6,
        "100.00",
    )


def test_origem_com_filtro_de_unidade_divide_unidade_pelo_site(db_session, unidade, outra_unidade):
    tipos = TipoEventoAnalytics
    _criar_eventos(db_session, tipos.visita_site, 10, canal=CanalAquisicao.instagram)
    _criar_eventos(db_session, tipos.clique_pedir, 2, canal=CanalAquisicao.instagram, unidade_id=unidade.id)
    _criar_eventos(
        db_session, tipos.clique_pedir, 3, canal=CanalAquisicao.instagram, unidade_id=outra_unidade.id
    )

    resultado = repository.obter_analises_aquisicao(db_session, unidade_id=unidade.id, agora=AGORA)
    instagram = _origem(resultado)[CanalAquisicao.instagram]

    assert (instagram.visitantes, instagram.cliques_pedir) == (10, 2)
    assert str(instagram.taxa_visita_clique) == "20.00"
    assert instagram.escopo_cliques == EscopoAquisicao.unidade
    assert instagram.escopo_taxa == EscopoAquisicao.unidade_sobre_site


def test_acoes_geradas_somam_todos_os_eventos(db_session, unidade):
    tipos = TipoEventoAnalytics
    _criar_eventos(db_session, tipos.visita_site, 4)
    _criar_eventos(db_session, tipos.abertura_cardapio, 4)
    _criar_eventos(db_session, tipos.abertura_cardapio, 2, primeiro_na_visita=False)
    _criar_eventos(db_session, tipos.selecao_unidade, 3, unidade_id=unidade.id)
    _criar_eventos(db_session, tipos.visualizacao_produto, 5, unidade_id=unidade.id)
    _criar_eventos(db_session, tipos.clique_pedir, 1, unidade_id=unidade.id)

    acoes = repository.obter_analises_aquisicao(db_session, agora=AGORA).acoes

    assert acoes.total_acoes == 19
    assert str(acoes.acoes_por_visita) == "4.75"
    assert acoes.escopo_acoes_por_visita == EscopoAquisicao.site
    assert [(acao.tipo, acao.total) for acao in acoes.por_tipo] == [
        (tipos.visita_site, 4),
        (tipos.abertura_cardapio, 6),
        (tipos.selecao_unidade, 3),
        (tipos.visualizacao_produto, 5),
        (tipos.clique_pedir, 1),
    ]


def test_acoes_com_filtro_de_unidade_informam_escopo(db_session, unidade, outra_unidade):
    _popular_exemplo_unidades(db_session, unidade.id, outra_unidade.id)

    acoes = repository.obter_analises_aquisicao(db_session, unidade_id=unidade.id, agora=AGORA).acoes

    assert acoes.total_acoes == 100 + 60 + 25 + 15 + 6
    assert str(acoes.acoes_por_visita) == "2.06"
    assert acoes.escopo_acoes_por_visita == EscopoAquisicao.unidade_sobre_site
    assert [acao.escopo for acao in acoes.por_tipo] == [
        EscopoAquisicao.site,
        EscopoAquisicao.site,
        EscopoAquisicao.unidade,
        EscopoAquisicao.unidade,
        EscopoAquisicao.unidade,
    ]


def test_acoes_sem_visitas_nao_dividem_por_zero(db_session):
    _criar_eventos(db_session, TipoEventoAnalytics.abertura_cardapio, 3)

    acoes = repository.obter_analises_aquisicao(db_session, agora=AGORA).acoes

    assert acoes.total_acoes == 3
    assert acoes.acoes_por_visita is None


def test_produtos_ranking_ordem_empate_e_removido(db_session, produto):
    tipos = TipoEventoAnalytics
    subcategoria = produto.subcategoria
    batata = _criar_produto(db_session, "Batata", subcategoria)
    coxinha = _criar_produto(db_session, "Coxinha", subcategoria)
    _criar_eventos(db_session, tipos.visualizacao_produto, 5, produto_id=produto.id)
    _criar_eventos(db_session, tipos.visualizacao_produto, 2, primeiro_na_visita=False, produto_id=produto.id)
    _criar_eventos(db_session, tipos.visualizacao_produto, 3, produto_id=coxinha.id)
    _criar_eventos(db_session, tipos.visualizacao_produto, 3, produto_id=batata.id)
    _criar_eventos(db_session, tipos.visualizacao_produto, 3)
    _criar_eventos(db_session, tipos.clique_pedir, 9, produto_id=batata.id)

    produtos = repository.obter_analises_aquisicao(db_session, agora=AGORA).produtos

    assert [(item.rank, item.nome, item.visualizacoes) for item in produtos] == [
        (1, "Paraiba Monster XL", 7),
        (2, "Batata", 3),
        (2, "Coxinha", 3),
        (2, "Produto removido", 3),
    ]
    assert produtos[-1].produto_id is None


def test_produtos_respeitam_limite(db_session, produto):
    for indice in range(repository.LIMITE_PRODUTOS_MAIS_VISUALIZADOS + 2):
        item = _criar_produto(db_session, f"Produto {indice:02d}", produto.subcategoria)
        _criar_eventos(db_session, TipoEventoAnalytics.visualizacao_produto, indice + 1, produto_id=item.id)

    produtos = repository.obter_analises_aquisicao(db_session, agora=AGORA).produtos

    assert len(produtos) == repository.LIMITE_PRODUTOS_MAIS_VISUALIZADOS
    assert produtos[0].nome == "Produto 11"
    assert [item.rank for item in produtos] == list(range(1, 11))


def test_produtos_com_filtro_de_unidade_e_canal(db_session, unidade, outra_unidade, produto):
    tipos = TipoEventoAnalytics
    _criar_eventos(
        db_session, tipos.visualizacao_produto, 4,
        produto_id=produto.id, unidade_id=unidade.id, canal=CanalAquisicao.instagram,
    )
    _criar_eventos(
        db_session, tipos.visualizacao_produto, 2,
        produto_id=produto.id, unidade_id=unidade.id, canal=CanalAquisicao.qrcode,
    )
    _criar_eventos(db_session, tipos.visualizacao_produto, 7, produto_id=produto.id, unidade_id=outra_unidade.id)

    [so_unidade] = repository.obter_analises_aquisicao(
        db_session, unidade_id=unidade.id, agora=AGORA
    ).produtos
    [unidade_e_canal] = repository.obter_analises_aquisicao(
        db_session, unidade_id=unidade.id, canal=CanalAquisicao.instagram, agora=AGORA
    ).produtos

    assert (so_unidade.visualizacoes, so_unidade.escopo) == (6, EscopoAquisicao.unidade)
    assert unidade_e_canal.visualizacoes == 4


def test_comparacao_por_unidade(db_session, unidade, outra_unidade):
    _popular_exemplo_unidades(db_session, unidade.id, outra_unidade.id)
    _criar_eventos(db_session, TipoEventoAnalytics.selecao_unidade, 5, primeiro_na_visita=False, unidade_id=unidade.id)

    unidades = repository.obter_analises_aquisicao(db_session, agora=AGORA).unidades

    assert [
        (
            item.unidade_id,
            item.escolhas,
            str(item.participacao_escolhas),
            item.cliques_pedir,
            str(item.taxa_escolha_clique),
        )
        for item in unidades
    ] == [
        (unidade.id, 25, "62.50", 6, "24.00"),
        (outra_unidade.id, 15, "37.50", 4, "26.67"),
    ]
    assert unidades[0].nome == "Unidade Analytics"


def test_comparacao_agrupa_cliques_sem_unidade(db_session, unidade):
    tipos = TipoEventoAnalytics
    _criar_eventos(db_session, tipos.selecao_unidade, 4, unidade_id=unidade.id)
    _criar_eventos(db_session, tipos.clique_pedir, 2, unidade_id=unidade.id)
    _criar_eventos(db_session, tipos.clique_pedir, 3)

    unidades = repository.obter_analises_aquisicao(db_session, agora=AGORA).unidades

    sem_unidade = unidades[-1]
    assert (sem_unidade.unidade_id, sem_unidade.nome) == (None, repository.NOME_SEM_UNIDADE)
    assert (sem_unidade.escolhas, sem_unidade.cliques_pedir) == (0, 3)
    assert str(sem_unidade.participacao_escolhas) == "0.00"
    assert sem_unidade.taxa_escolha_clique is None


def test_comparacao_com_filtros_de_unidade_e_canal(db_session, unidade, outra_unidade):
    tipos = TipoEventoAnalytics
    _criar_eventos(db_session, tipos.selecao_unidade, 4, unidade_id=unidade.id, canal=CanalAquisicao.instagram)
    _criar_eventos(db_session, tipos.selecao_unidade, 6, unidade_id=unidade.id, canal=CanalAquisicao.qrcode)
    _criar_eventos(db_session, tipos.selecao_unidade, 9, unidade_id=outra_unidade.id, canal=CanalAquisicao.instagram)

    por_canal = repository.obter_analises_aquisicao(
        db_session, canal=CanalAquisicao.instagram, agora=AGORA
    ).unidades
    [filtrada] = repository.obter_analises_aquisicao(
        db_session, unidade_id=unidade.id, agora=AGORA
    ).unidades

    assert [(item.unidade_id, item.escolhas) for item in por_canal] == [
        (outra_unidade.id, 9),
        (unidade.id, 4),
    ]
    assert (filtrada.unidade_id, filtrada.escolhas, str(filtrada.participacao_escolhas)) == (
        unidade.id,
        10,
        "100.00",
    )


def test_analises_respeitam_periodo_de_brasilia(db_session, unidade):
    vespera_23h30 = ingestao.horario_truncado_utc(
        datetime(2026, 10, 19, 23, 30, tzinfo=repository.FUSO_SAO_PAULO)
    )
    hoje_23h30 = ingestao.horario_truncado_utc(
        datetime(2026, 10, 26, 23, 30, tzinfo=repository.FUSO_SAO_PAULO)
    )
    for ocorrido_em in (vespera_23h30, hoje_23h30):
        _criar_eventos(db_session, TipoEventoAnalytics.visita_site, ocorrido_em=ocorrido_em)
        _criar_eventos(
            db_session, TipoEventoAnalytics.selecao_unidade, ocorrido_em=ocorrido_em, unidade_id=unidade.id
        )

    resultado = repository.obter_analises_aquisicao(
        db_session, periodo=PeriodoAquisicao.ultimos_7_dias, agora=AGORA
    )

    assert _origem(resultado)[CanalAquisicao.direto].visitantes == 1
    assert resultado.acoes.total_acoes == 2
    assert [item.escolhas for item in resultado.unidades] == [1]


def test_analises_sem_resultados(cliente):
    resposta = cliente.get("/analytics/aquisicao/analises")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [linha["canal"] for linha in corpo["origem"]] == [canal.value for canal in CanalAquisicao]
    assert corpo["acoes"]["total_acoes"] == 0
    assert corpo["acoes"]["acoes_por_visita"] is None
    assert corpo["produtos"] == []
    assert corpo["unidades"] == []


def test_analises_cenario_de_homologacao(cliente, db_session, unidade, produto):
    tipos = TipoEventoAnalytics
    batata = _criar_produto(db_session, "Batata", produto.subcategoria)
    for canal in (CanalAquisicao.instagram, CanalAquisicao.qrcode):
        _criar_eventos(db_session, tipos.visita_site, 20, canal=canal)
        _criar_eventos(db_session, tipos.abertura_cardapio, 20, canal=canal)
        _criar_eventos(db_session, tipos.selecao_unidade, 20, canal=canal, unidade_id=unidade.id)
        for item, primeiro in ((produto, True), (batata, False)):
            _criar_eventos(
                db_session, tipos.visualizacao_produto, 20,
                primeiro_na_visita=primeiro, canal=canal, unidade_id=unidade.id, produto_id=item.id,
            )
        _criar_eventos(db_session, tipos.clique_pedir, 20, canal=canal, unidade_id=unidade.id)

    corpo = cliente.get("/analytics/aquisicao/analises").json()
    origem = {linha["canal"]: linha for linha in corpo["origem"]}

    for canal in ("instagram", "qrcode"):
        assert (origem[canal]["visitantes"], origem[canal]["participacao"]) == (20, "50.00")
        assert origem[canal]["taxa_visita_clique"] == "100.00"
    assert {origem[canal]["visitantes"] for canal in ("campanha_outros", "busca", "outros_sites", "direto")} == {0}
    assert (corpo["acoes"]["total_acoes"], corpo["acoes"]["acoes_por_visita"]) == (240, "6.00")
    assert [(item["nome"], item["visualizacoes"]) for item in corpo["produtos"]] == [
        ("Batata", 40),
        ("Paraiba Monster XL", 40),
    ]
    assert corpo["unidades"] == [
        {
            "unidade_id": unidade.id,
            "nome": "Unidade Analytics",
            "escolhas": 40,
            "participacao_escolhas": "100.00",
            "cliques_pedir": 40,
            "taxa_escolha_clique": "100.00",
        }
    ]


@pytest.mark.parametrize(
    "params",
    [
        {"periodo": "ontem"},
        {"canal": "tiktok"},
        {"unidade_id": 0},
        {"unidade_id": "abc"},
    ],
)
def test_analises_rejeitam_filtro_invalido(cliente, params):
    assert cliente.get("/analytics/aquisicao/analises", params=params).status_code == 422


def test_analises_exigem_autenticacao(cliente):
    app.dependency_overrides.pop(get_current_user, None)

    resposta = cliente.get("/analytics/aquisicao/analises")

    assert resposta.status_code == 401
