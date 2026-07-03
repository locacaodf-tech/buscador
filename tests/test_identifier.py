from app.services.identifier import infer_identifier
from app.schemas import SearchRequest


def test_infer_cnj():
    resolved = infer_identifier('0000832-35.2018.4.01.3202')
    assert resolved.search_type == 'cnj'
    assert resolved.search_key == '00008323520184013202'


def test_explicit_precatorio_number():
    req = SearchRequest(search_type='precatorio_number', search_key='PRC-2027-000000')
    assert req.resolved_type_and_key() == ('precatorio_number', 'PRC-2027-000000')


def test_alias_numero_precatorio():
    req = SearchRequest(search_type='precatorio', search_key='PRC-2027-000000')
    assert req.resolved_type_and_key() == ('precatorio_number', 'PRC-2027-000000')


def test_alias_numero_processo_field():
    req = SearchRequest(numero_processo='0000832-35.2018.4.01.3202')
    assert req.resolved_type_and_key() == ('cnj', '00008323520184013202')
