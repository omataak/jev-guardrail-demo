import json
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from app import main

@pytest.fixture(autouse=True)
def isolated_network_env(monkeypatch):
    for key in ('ALL_PROXY', 'HTTPS_PROXY', 'HTTP_PROXY', 'all_proxy', 'https_proxy', 'http_proxy'):
        monkeypatch.delenv(key, raising=False)


client = TestClient(main.app)
rules = main.parse_rules(main.DEFAULT)


def response(p=0.1):
    return {'model': main.MODEL, 'answers': {k: {'type': 'noul', 'noul': p} for k in rules}, 'usage': {'input_tokens': 1000}}


def test_threshold_and_cost():
    data = response()
    data['answers']['injection']['noul'] = .5
    result = main.summarize(data, rules)
    assert result['blocked']
    assert result['cost'] == pytest.approx(.000042)
    data['answers']['injection']['noul'] = .499999
    assert not main.summarize(data, rules)['blocked']


@pytest.mark.parametrize('p', [float('nan'), -0.1, 1.1, True, '0.9'])
def test_invalid_response(p):
    with pytest.raises(ValueError):
        main.summarize(response(p), rules)


def test_missing_answer_and_usage():
    data = response()
    data.pop('usage')
    assert main.summarize(data, rules)['cost'] is None
    del data['answers']['violence']
    with pytest.raises(ValueError):
        main.summarize(data, rules)


@pytest.mark.parametrize('threshold', [True, -1, 2, float('nan')])
def test_invalid_threshold(threshold):
    config = json.loads(main.DEFAULT)
    config['rules']['injection']['threshold'] = threshold
    with pytest.raises(ValueError):
        main.parse_rules(json.dumps(config))


def test_home_and_missing_key(monkeypatch):
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    assert 'Jev Guardrail Demo' in client.get('/').text
    result = client.post('/evaluate', data={'rules': main.DEFAULT, 'prompt': '点検'})
    assert 'TYPESAFE_API_KEY' in result.text
    assert 'Passed' not in result.text


def test_roundtrip(monkeypatch):
    monkeypatch.setenv('TYPESAFE_API_KEY', 'test-key')
    async def post(self, url, **kwargs):
        assert url == 'https://api.typesafe.ai/v1/systemone'
        assert len(kwargs['json']['questions']) == 4
        assert 'threshold' not in kwargs['json']['questions']['injection']
        assert kwargs['json']['state'] == '<script>alert(1)</script>'
        return httpx.Response(200, json=response(.5))
    with patch.object(httpx.AsyncClient, 'post', post):
        result = client.post('/evaluate', data={'rules': main.DEFAULT, 'prompt': '<script>alert(1)</script>'})
    assert result.status_code == 200
    assert 'Blocked' in result.text
    assert '$0.00004200' in result.text
    assert '<script>alert(1)</script>' not in result.text
    assert '&lt;script&gt;' in result.text
    assert 'Request JSON' in result.text and 'Response JSON' in result.text
    assert 'is-triggered' in result.text
    assert 'test-key' not in result.text
    assert 'input_tokens' in result.text


@pytest.mark.parametrize('code', [401, 429, 529])
def test_api_error(monkeypatch, code):
    monkeypatch.setenv('TYPESAFE_API_KEY', 'test-key')
    async def post(*args, **kwargs):
        return httpx.Response(code, text='secret provider detail')
    with patch.object(httpx.AsyncClient, 'post', post):
        result = client.post('/evaluate', data={'rules': main.DEFAULT, 'prompt': '点検'})
    assert f'({code})' in result.text
    assert 'Passed' not in result.text
    assert 'secret provider detail' not in result.text


def test_mixed_rules():
    config = {'rules': {
        'choice': {'type': 'choice', 'label': '分類', 'instructions': '分類する', 'criteria': {'allow': '許可', 'block': '拒否'}, 'blocked_choices': ['block']},
        'score': {'type': 'score', 'label': '重大度', 'instructions': '評価する', 'criteria': ['なし', '軽度', '重大'], 'threshold': 1.5}
    }}
    parsed = main.parse_rules(json.dumps(config))
    data = {'answers': {'choice': {'type': 'choice', 'choice': 'allow', 'probabilities': {'allow': .8, 'block': .2}}, 'score': {'type': 'score', 'score': 1.5}}}
    assert main.summarize(data, parsed)['blocked']
    data['answers']['score']['score'] = 1.49
    assert not main.summarize(data, parsed)['blocked']
    data['answers']['choice'].update(choice='block', probabilities={'allow': .1, 'block': .9})
    assert main.summarize(data, parsed)['blocked']
    html = main.templates.get_template('result.html').render(**main.summarize(data, parsed), elapsed=42, prompt='test')
    assert 'block' in html and '1.49' in html
    config['rules']['choice']['blocked_choices'] = ['missing']
    with pytest.raises(ValueError):
        main.parse_rules(json.dumps(config))


def test_invalid_score():
    config={'rules':{'s':{'type':'score','label':'評価','instructions':'評価','criteria':['低','高'],'threshold':2}}}
    with pytest.raises(ValueError): main.parse_rules(json.dumps(config))
    config['rules']['s']['threshold']=.5
    parsed=main.parse_rules(json.dumps(config))
    with pytest.raises(ValueError): main.summarize({'answers':{'s':{'type':'score','score':2}}},parsed)
