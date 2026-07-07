"""v31d — Auditoria multi-tribunal DataJud. Prova que CNJ -> tribunal
inferido -> alias DataJud está correto pra TODO o registry nacional (não
só TRF3), e que o diagnóstico mostra alias/endpoint/status real, nunca só
'não encontrado'."""
import os

os.environ.setdefault('APP_LOGIN_PASSWORD', '')
os.environ.setdefault('INTERNAL_API_TOKEN', '')

from fastapi.testclient import TestClient

from app.main import app
from app.connectors.tribunal_registry import TRIBUNAL_ALIASES
from app.utils.cnj import infer_tribunal_from_cnj
from app.services.datajud_diagnostico import diagnosticar_cnj, _endpoint_e_alias


def _cnj(segmento: str, tr: str) -> str:
    return f'0000000-00.2023.{segmento}.{tr}.0001'


# ---------------------------------------------------------------------------
# 4. Matriz completa: CNJ -> tribunal inferido -> alias DataJud correto,
# pra TODOS os segmentos (TRF1-6, TRT1-24, TJ01-27) — não só TRF3.
# ---------------------------------------------------------------------------

def test_matriz_completa_trf_tribunal_e_alias_batem():
    for tr in ['01', '02', '03', '04', '05', '06']:
        cnj = _cnj('4', tr)
        tribunal = infer_tribunal_from_cnj(cnj)
        assert tribunal == f'TRF{int(tr)}', f'TR={tr}'
        assert tribunal in TRIBUNAL_ALIASES, f'{tribunal} sem alias no registry'
        alias, endpoint = _endpoint_e_alias(tribunal)
        assert alias == tribunal.lower()
        assert endpoint == f'https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal.lower()}/_search'


def test_matriz_completa_trt_tribunal_e_alias_batem():
    for i in range(1, 25):
        tr = f'{i:02d}'
        cnj = _cnj('5', tr)
        tribunal = infer_tribunal_from_cnj(cnj)
        assert tribunal == f'TRT{i}', f'TR={tr}'
        assert tribunal in TRIBUNAL_ALIASES, f'{tribunal} sem alias no registry'
        alias, endpoint = _endpoint_e_alias(tribunal)
        assert alias == tribunal.lower()
        assert endpoint == f'https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal.lower()}/_search'


def test_matriz_completa_tj_tribunal_e_alias_batem():
    from app.utils.cnj import ESTADUAL_TR_MAP
    for tr, tribunal_esperado in ESTADUAL_TR_MAP.items():
        cnj = _cnj('8', tr)
        tribunal = infer_tribunal_from_cnj(cnj)
        assert tribunal == tribunal_esperado, f'TR={tr}'
        assert tribunal in TRIBUNAL_ALIASES, f'{tribunal} sem alias no registry'
        alias, endpoint = _endpoint_e_alias(tribunal)
        assert alias == tribunal.lower()
        assert endpoint == f'https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal.lower()}/_search'


# ---------------------------------------------------------------------------
# 3. Os 5 casos reais pedidos, via diagnosticar_cnj
# ---------------------------------------------------------------------------

def test_a_trf3_infere_e_resolve_alias_correto():
    import asyncio
    async def _run():
        r = await diagnosticar_cnj('5000563-34.2022.4.03.6331')
        assert r['tribunal_inferido'] == 'TRF3'
        assert r['alias_datajud'] == 'trf3'
        assert r['endpoint'] == 'https://api-publica.datajud.cnj.jus.br/api_publica_trf3/_search'
        assert r['status_http'] is not None or r['resultado'] == 'erro'  # tentou de verdade

    asyncio.run(_run())


def test_b_tjpe_infere_e_resolve_alias_correto():
    import asyncio
    async def _run():
        r = await diagnosticar_cnj('0001013-66.2019.8.17.2670')
        assert r['tribunal_inferido'] == 'TJPE'
        assert r['alias_datajud'] == 'tjpe'
        assert r['endpoint'] == 'https://api-publica.datajud.cnj.jus.br/api_publica_tjpe/_search'

    asyncio.run(_run())


def test_c_tjal_infere_e_resolve_alias_correto():
    import asyncio
    async def _run():
        r = await diagnosticar_cnj('0713236-85.2016.8.02.0001')
        assert r['tribunal_inferido'] == 'TJAL'
        assert r['alias_datajud'] == 'tjal'
        assert r['endpoint'] == 'https://api-publica.datajud.cnj.jus.br/api_publica_tjal/_search'

    asyncio.run(_run())


def test_d_trt7_infere_e_resolve_alias_correto():
    import asyncio
    async def _run():
        r = await diagnosticar_cnj('0000765-97.2023.5.07.0016')
        assert r['tribunal_inferido'] == 'TRT7'
        assert r['alias_datajud'] == 'trt7'
        assert r['endpoint'] == 'https://api-publica.datajud.cnj.jus.br/api_publica_trt7/_search'

    asyncio.run(_run())


def test_e_trf1_infere_e_resolve_alias_correto():
    import asyncio
    async def _run():
        r = await diagnosticar_cnj('0000000-00.2023.4.01.0001')
        assert r['tribunal_inferido'] == 'TRF1'
        assert r['alias_datajud'] == 'trf1'
        assert r['endpoint'] == 'https://api-publica.datajud.cnj.jus.br/api_publica_trf1/_search'

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Os 4 estados de resultado (2. no pedido)
# ---------------------------------------------------------------------------

def test_cnj_invalido():
    import asyncio
    async def _run():
        r = await diagnosticar_cnj('123')
        assert r['resultado'] == 'cnj_invalido'
        assert 'inválido' in r['proxima_acao'].lower()

    asyncio.run(_run())


def test_tribunal_inferido_dizendo_que_consultou_e_veio_vazio(monkeypatch):
    import asyncio
    import httpx

    class FakeResponse:
        status_code = 200
        def json(self):
            return {'hits': {'hits': []}}
        text = '{}'

    async def fake_post(self, url, headers=None, json=None):
        return FakeResponse()

    async def _run():
        monkeypatch.setattr(httpx.AsyncClient, 'post', fake_post)
        r = await diagnosticar_cnj('0000765-97.2023.5.07.0016')
        assert r['resultado'] == 'vazio'
        assert 'TRT7' in r['proxima_acao']
        assert 'não houve retorno' in r['proxima_acao'].lower()

    asyncio.run(_run())


def test_tribunal_inferido_mas_datajud_falhou(monkeypatch):
    import asyncio
    import httpx

    async def fake_post_falha(self, url, headers=None, json=None):
        raise httpx.TimeoutException('timeout simulado')

    async def _run():
        monkeypatch.setattr(httpx.AsyncClient, 'post', fake_post_falha)
        r = await diagnosticar_cnj('0000765-97.2023.5.07.0016')
        assert r['resultado'] == 'erro'
        assert 'TRT7' in r['proxima_acao']

    asyncio.run(_run())


def test_tribunal_inferido_mas_alias_ausente_no_registry():
    """Simula um tribunal hipotético que a inferência devolveria mas que
    não está no registry — cenário defensivo, não deveria acontecer com o
    registry atual (que é completo), mas o diagnóstico precisa lidar com
    isso sem quebrar."""
    alias, endpoint = _endpoint_e_alias('TRIBUNAL_INEXISTENTE_XYZ')
    assert alias is None
    assert endpoint is None


def test_tribunal_nao_inferido_ainda_ex_eleitoral():
    import asyncio
    async def _run():
        r = await diagnosticar_cnj('0000000-00.2023.6.02.0001')
        assert r['tribunal_inferido'] is None
        assert r['resultado'] == 'tribunal_nao_inferido'

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 5. Endpoint GET /api/datajud/diagnostico/{cnj}
# ---------------------------------------------------------------------------

def test_endpoint_diagnostico_devolve_todos_os_campos_pedidos():
    client = TestClient(app)
    resp = client.get('/api/datajud/diagnostico/5000563-34.2022.4.03.6331')
    assert resp.status_code == 200
    body = resp.json()
    for campo in ['cnj_original', 'cnj_normalizado', 'segmento', 'tribunal_inferido',
                  'alias_datajud', 'endpoint', 'status_http', 'resultado', 'erro', 'proxima_acao']:
        assert campo in body, f'campo {campo} ausente'
    assert body['tribunal_inferido'] == 'TRF3'
    assert body['alias_datajud'] == 'trf3'


def test_endpoint_diagnostico_tjpe():
    client = TestClient(app)
    resp = client.get('/api/datajud/diagnostico/0001013-66.2019.8.17.2670')
    body = resp.json()
    assert body['tribunal_inferido'] == 'TJPE'
    assert body['alias_datajud'] == 'tjpe'


# ---------------------------------------------------------------------------
# 7. Fallback manual por tribunal
# ---------------------------------------------------------------------------

def test_fallback_manual_para_tjpe_e_tjal_e_trt7_e_trf3():
    from app.services.datajud_diagnostico import _fonte_manual_para
    assert 'tjpe' in _fonte_manual_para('TJPE').lower()
    assert 'tjal' in _fonte_manual_para('TJAL').lower()
    assert 'trt7' in _fonte_manual_para('TRT7').lower()
    assert 'trf3' in _fonte_manual_para('TRF3').lower()


def test_fallback_manual_verificado_nao_e_confundido_com_padrao():
    from app.services.datajud_diagnostico import _fonte_manual_para, FONTES_MANUAIS_VERIFICADAS
    # TRF1 e TJPE foram verificados de fato (busca real) — não devem
    # mostrar o aviso de "padrão não verificado"
    assert 'não verificado' not in _fonte_manual_para('TRF1').lower()
    assert 'não verificado' not in _fonte_manual_para('TJPE').lower()
    # um tribunal qualquer fora da lista verificada deve mostrar o aviso
    assert 'não verificado' in _fonte_manual_para('TJAL').lower()
