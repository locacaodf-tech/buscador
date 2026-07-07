"""Testes de cobertura NACIONAL do IntakeBot (v31c). Importante: Ceará/TRT7
e Pará/TRF3 foram só os exemplos originais dos prints — as tabelas de
inferência (TRF1-6, TRT1-24, todos os 27 TJs) sempre foram construídas de
forma genérica e nacional desde a v31 original, usando o mesmo código pra
qualquer região. Este arquivo prova isso com uma matriz ampla, e cobre um
gap real que a auditoria nacional revelou: Justiça Estadual (TJs) ainda
não tinha mapa de UF pra checagem de divergência — só Federal e
Trabalhista tinham."""
from app.services.whatsapp_intake import analisar_cnj, processar_mensagem


def _cnj(segmento: str, tr: str) -> str:
    """Monta um CNJ sintético válido em formato (dígito verificador e
    número de origem não importam pra inferência, só ano/segmento/tr)."""
    return f'0000000-00.2023.{segmento}.{tr}.0001'


# ---------------------------------------------------------------------------
# A-L do pedido (mistura TRF/TRT/TJ por região)
# ---------------------------------------------------------------------------

def test_a_ceara_trt7():
    a = analisar_cnj(_cnj('5', '07'))
    assert a['tribunal_provavel'] == 'TRT7'
    assert a['ufs_cobertas'] == ['CE']


def test_b_sao_paulo_trf3():
    a = analisar_cnj(_cnj('4', '03'))
    assert a['tribunal_provavel'] == 'TRF3'
    assert 'SP' in a['ufs_cobertas']


def test_c_para_trf1():
    a = analisar_cnj(_cnj('4', '01'))
    assert a['tribunal_provavel'] == 'TRF1'
    assert 'PA' in a['ufs_cobertas']


def test_d_distrito_federal_tjdft_e_trf1():
    a_tj = analisar_cnj(_cnj('8', '07'))
    assert a_tj['tribunal_provavel'] == 'TJDFT'
    assert a_tj['ufs_cobertas'] == ['DF']
    a_trf = analisar_cnj(_cnj('4', '01'))
    assert 'DF' in a_trf['ufs_cobertas']


def test_e_rio_de_janeiro_trt1_e_tjrj():
    a_trt = analisar_cnj(_cnj('5', '01'))
    assert a_trt['tribunal_provavel'] == 'TRT1'
    assert a_trt['ufs_cobertas'] == ['RJ']
    a_tj = analisar_cnj(_cnj('8', '19'))
    assert a_tj['tribunal_provavel'] == 'TJRJ'
    assert a_tj['ufs_cobertas'] == ['RJ']


def test_f_minas_gerais_tjmg_e_trt3():
    a_tj = analisar_cnj(_cnj('8', '13'))
    assert a_tj['tribunal_provavel'] == 'TJMG'
    assert a_tj['ufs_cobertas'] == ['MG']
    a_trt = analisar_cnj(_cnj('5', '03'))
    assert a_trt['tribunal_provavel'] == 'TRT3'
    assert a_trt['ufs_cobertas'] == ['MG']


def test_g_rio_grande_do_sul_trf4_e_trt4():
    a_trf = analisar_cnj(_cnj('4', '04'))
    assert a_trf['tribunal_provavel'] == 'TRF4'
    assert 'RS' in a_trf['ufs_cobertas']
    a_trt = analisar_cnj(_cnj('5', '04'))
    assert a_trt['tribunal_provavel'] == 'TRT4'
    assert a_trt['ufs_cobertas'] == ['RS']


def test_h_pernambuco_trf5_e_trt6():
    a_trf = analisar_cnj(_cnj('4', '05'))
    assert a_trf['tribunal_provavel'] == 'TRF5'
    assert 'PE' in a_trf['ufs_cobertas']
    a_trt = analisar_cnj(_cnj('5', '06'))
    assert a_trt['tribunal_provavel'] == 'TRT6'
    assert a_trt['ufs_cobertas'] == ['PE']


def test_i_bahia_trt5_e_tjba():
    a_trt = analisar_cnj(_cnj('5', '05'))
    assert a_trt['tribunal_provavel'] == 'TRT5'
    assert a_trt['ufs_cobertas'] == ['BA']
    a_tj = analisar_cnj(_cnj('8', '05'))
    assert a_tj['tribunal_provavel'] == 'TJBA'


def test_j_goias_trt18_e_tjgo():
    a_trt = analisar_cnj(_cnj('5', '18'))
    assert a_trt['tribunal_provavel'] == 'TRT18'
    assert a_trt['ufs_cobertas'] == ['GO']
    a_tj = analisar_cnj(_cnj('8', '09'))
    assert a_tj['tribunal_provavel'] == 'TJGO'


def test_k_mato_grosso_x_mato_grosso_do_sul_trts():
    a_mt = analisar_cnj(_cnj('5', '23'))
    assert a_mt['tribunal_provavel'] == 'TRT23'
    assert a_mt['ufs_cobertas'] == ['MT']
    a_ms = analisar_cnj(_cnj('5', '24'))
    assert a_ms['tribunal_provavel'] == 'TRT24'
    assert a_ms['ufs_cobertas'] == ['MS']


def test_l_sao_paulo_trt2_x_trt15():
    a_capital = analisar_cnj(_cnj('5', '02'))
    assert a_capital['tribunal_provavel'] == 'TRT2'
    assert a_capital['ufs_cobertas'] == ['SP']
    a_interior = analisar_cnj(_cnj('5', '15'))
    assert a_interior['tribunal_provavel'] == 'TRT15'
    assert a_interior['ufs_cobertas'] == ['SP']
    assert a_capital['tribunal_provavel'] != a_interior['tribunal_provavel']  # nunca confundir os dois


# ---------------------------------------------------------------------------
# Lista específica de TRTs pedida (complemento)
# ---------------------------------------------------------------------------

def test_todos_os_trts_da_lista_pedida():
    esperado = {
        '01': ('TRT1', {'RJ'}), '02': ('TRT2', {'SP'}), '03': ('TRT3', {'MG'}), '04': ('TRT4', {'RS'}),
        '07': ('TRT7', {'CE'}), '08': ('TRT8', {'PA', 'AP'}), '10': ('TRT10', {'DF', 'TO'}),
        '15': ('TRT15', {'SP'}), '18': ('TRT18', {'GO'}), '23': ('TRT23', {'MT'}), '24': ('TRT24', {'MS'}),
    }
    for tr, (tribunal_esperado, ufs_esperadas) in esperado.items():
        a = analisar_cnj(_cnj('5', tr))
        assert a['tribunal_provavel'] == tribunal_esperado, f'TR={tr}'
        assert set(a['ufs_cobertas']) == ufs_esperadas, f'TR={tr}'


# ---------------------------------------------------------------------------
# TRFs (1 a 6) com UF compatível
# ---------------------------------------------------------------------------

def test_todos_os_trfs_com_ufs_corretas():
    esperado = {
        '01': ('TRF1', {'AC', 'AM', 'AP', 'BA', 'DF', 'GO', 'MA', 'MT', 'PA', 'PI', 'RO', 'RR', 'TO'}),
        '02': ('TRF2', {'ES', 'RJ'}),
        '03': ('TRF3', {'MS', 'SP'}),
        '04': ('TRF4', {'PR', 'RS', 'SC'}),
        '05': ('TRF5', {'AL', 'CE', 'PB', 'PE', 'RN', 'SE'}),
        '06': ('TRF6', {'MG'}),
    }
    for tr, (tribunal_esperado, ufs_esperadas) in esperado.items():
        a = analisar_cnj(_cnj('4', tr))
        assert a['tribunal_provavel'] == tribunal_esperado, f'TR={tr}'
        assert set(a['ufs_cobertas']) == ufs_esperadas, f'TR={tr}'


# ---------------------------------------------------------------------------
# TJs (Justiça Estadual) — TJSP, TJDFT, TJPA, TJMG
# ---------------------------------------------------------------------------

def test_tjsp():
    a = analisar_cnj(_cnj('8', '26'))
    assert a['tribunal_provavel'] == 'TJSP'
    assert a['ufs_cobertas'] == ['SP']


def test_tjdft():
    a = analisar_cnj(_cnj('8', '07'))
    assert a['tribunal_provavel'] == 'TJDFT'
    assert a['ufs_cobertas'] == ['DF']


def test_tjpa():
    a = analisar_cnj(_cnj('8', '14'))
    assert a['tribunal_provavel'] == 'TJPA'
    assert a['ufs_cobertas'] == ['PA']


def test_tjmg():
    a = analisar_cnj(_cnj('8', '13'))
    assert a['tribunal_provavel'] == 'TJMG'
    assert a['ufs_cobertas'] == ['MG']


# ---------------------------------------------------------------------------
# Divergências nacionais (não só Pará/TRF3)
# ---------------------------------------------------------------------------

def test_divergencia_ceara_vs_outro_tribunal():
    """Se o CNJ é de outro tribunal (não TRT7/CE) mas a pessoa menciona
    Ceará, tem que alertar — não só no sentido contrário (Pará/TRF3)."""
    texto = f'Processo {_cnj("5", "01").replace(chr(45), chr(46), 1)}. O processo é de Fortaleza, Ceará.'
    r = processar_mensagem(f'Processo {"".join(c for c in _cnj("5", "01") if c.isdigit())}. Fortaleza, Ceará.')
    assert len(r['divergencias']) == 1
    assert 'CE' in r['divergencias'][0]
    assert 'TRT1' in r['divergencias'][0]


def test_divergencia_tjsp_vs_outro_estado_mencionado():
    cnj_tjsp_digitos = ''.join(c for c in _cnj('8', '26') if c.isdigit())
    r = processar_mensagem(f'Processo {cnj_tjsp_digitos}. Isso é no Rio Grande do Sul.')
    assert len(r['divergencias']) == 1
    assert 'RS' in r['divergencias'][0]
    assert 'TJSP' in r['divergencias'][0]


def test_sem_divergencia_quando_uf_bate_com_tjsp():
    cnj_tjsp_digitos = ''.join(c for c in _cnj('8', '26') if c.isdigit())
    r = processar_mensagem(f'Processo {cnj_tjsp_digitos}. É em São Paulo mesmo.')
    assert r['divergencias'] == []


# ---------------------------------------------------------------------------
# Normalização nacional sem pontuação — trabalhista, federal, estadual
# ---------------------------------------------------------------------------

def test_normaliza_trabalhista_sem_pontuacao_generico():
    digitos = ''.join(c for c in _cnj('5', '12') if c.isdigit())  # TRT12/SC, nao TRT7
    r = processar_mensagem(digitos)
    p = r['processos_detectados'][0]
    assert p['tribunal_provavel'] == 'TRT12'
    assert p['ufs_cobertas'] == ['SC']


def test_normaliza_federal_sem_pontuacao_generico():
    digitos = ''.join(c for c in _cnj('4', '02') if c.isdigit())  # TRF2, nao TRF3
    r = processar_mensagem(digitos)
    p = r['processos_detectados'][0]
    assert p['tribunal_provavel'] == 'TRF2'


def test_normaliza_estadual_sem_pontuacao_generico():
    digitos = ''.join(c for c in _cnj('8', '21') if c.isdigit())  # TJRS
    r = processar_mensagem(digitos)
    p = r['processos_detectados'][0]
    assert p['tribunal_provavel'] == 'TJRS'
    assert p['ufs_cobertas'] == ['RS']


# ---------------------------------------------------------------------------
# fonte_recomendada usa o registry real do DataJud (nacional)
# ---------------------------------------------------------------------------

def test_fonte_recomendada_usa_registry_real_do_datajud():
    from app.connectors.tribunal_registry import TRIBUNAL_ALIASES

    for tr, tribunal_esperado in [('01', 'TRT1'), ('07', 'TRT7'), ('24', 'TRT24')]:
        a = analisar_cnj(_cnj('5', tr))
        assert tribunal_esperado in TRIBUNAL_ALIASES
        assert 'Consulta automática disponível' in a['fonte_recomendada']
        assert tribunal_esperado in a['fonte_recomendada']


def test_segmento_nao_inferivel_ainda_diz_isso_claramente():
    a = analisar_cnj(_cnj('6', '02'))  # eleitoral, ainda nao inferido a tribunal especifico
    assert a['tribunal_provavel'] is None
    assert 'Não foi possível inferir' in a['fonte_recomendada']
