import json
import math
import os
from pathlib import Path
from time import perf_counter

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE = Path(__file__).resolve().parent
load_dotenv(BASE.parent / '.env')
MODEL = 'jev-1.13.0'
PRICE = 0.042  # USD / million input tokens, verified 2026-09-25
app = FastAPI(title='Jev Guardrail Demo')
app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')
templates = Jinja2Templates(directory=BASE / 'templates')
DEFAULT = (BASE / 'rules.json').read_text(encoding='utf-8')
SAMPLES = json.loads((BASE / 'samples.json').read_text(encoding='utf-8'))


def number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def parse_rules(raw):
    try:
        config = json.loads(raw)
    except ValueError:
        raise ValueError('ルールJSONの構文を確認してください。')
    if not isinstance(config, dict) or set(config) != {'rules'}:
        raise ValueError('JSONのトップレベルは rules のみにしてください。')
    rules = config['rules']
    if not isinstance(rules, dict) or not 1 <= len(rules) <= 10:
        raise ValueError('ルールは1〜10項目にしてください。')
    for key, r in rules.items():
        if not isinstance(r, dict):
            raise ValueError('ルール形式が不正です。')
        kind = r.get('type', 'noul')
        r['type'] = kind
        if kind not in ('noul', 'choice', 'score'):
            raise ValueError('判定形式を選択してください。')
        if any(not isinstance(r.get(x), str) or not r[x].strip() for x in ('label', 'instructions')):
            raise ValueError('表示名・判定指示を入力してください。')
        c = r.get('criteria')
        valid_text = lambda x: isinstance(x, str) and bool(x.strip())
        if kind == 'noul':
            if not isinstance(c, dict) or set(c) != {'true', 'false'} or not all(valid_text(v) for v in c.values()):
                raise ValueError('Noulの該当・非該当の基準を入力してください。')
            if not number(r.get('threshold'), 0, 1):
                raise ValueError('確率の閾値は0〜1です。')
        elif kind == 'choice':
            if not isinstance(c, dict) or not 2 <= len(c) <= 255 or not all(valid_text(k) and valid_text(v) for k, v in c.items()):
                raise ValueError('Choiceには名前と定義が異なる2個以上の選択肢が必要です。')
            blocked = r.get('blocked_choices')
            if not isinstance(blocked, list) or not blocked or any(not isinstance(x, str) or x not in c for x in blocked):
                raise ValueError('ブロック対象の選択肢を1個以上指定してください。')
        else:
            if not isinstance(c, list) or not 2 <= len(c) <= 10 or not all(valid_text(v) for v in c):
                raise ValueError('Scoreには2〜10段階の定義が必要です。')
            if not number(r.get('threshold'), 0, len(c)-1):
                raise ValueError('スコア閾値は0〜最大レベルの範囲で設定してください。')
    return rules


def summarize(data, rules):
    rows = []
    try:
        for key, r in rules.items():
            kind = r.get('type', 'noul')
            answer = data['answers'][key]
            if answer['type'] != kind:
                raise ValueError()
            row = dict(label=r['label'], type=kind)
            if kind == 'noul':
                p = answer['noul']
                if not number(p, 0, 1): raise ValueError()
                row.update(probability=p, triggered=p >= r['threshold'])
            elif kind == 'choice':
                choice, probs = answer['choice'], answer['probabilities']
                if choice not in r['criteria'] or set(probs) != set(r['criteria']) or not all(number(p, 0, 1) for p in probs.values()) or abs(sum(probs.values())-1) > .02:
                    raise ValueError()
                row.update(choice=choice, probabilities=probs, triggered=choice in r['blocked_choices'])
            else:
                score = answer['score']
                if not number(score, 0, len(r['criteria'])-1): raise ValueError()
                row.update(score=score, maximum=len(r['criteria'])-1, triggered=score >= r['threshold'])
            rows.append(row)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError('APIの判定結果が不足しているか、数値が不正です。再実行してください。')
    usage = data.get('usage') or {}
    tokens = usage.get('input_tokens') if isinstance(usage, dict) else None
    if type(tokens) is not int or tokens < 0: tokens = None
    return dict(rows=rows, blocked=any(r['triggered'] for r in rows), tokens=tokens,
                cost=tokens * PRICE / 1_000_000 if tokens is not None else None,
                model=data.get('model', MODEL))


@app.get('/', response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name='index.html', context={'rules': DEFAULT, 'samples': SAMPLES, 'configured': bool(os.getenv('TYPESAFE_API_KEY', '').strip())})


@app.post('/evaluate', response_class=HTMLResponse)
async def evaluate(request: Request, rules: str = Form(''), prompt: str = Form('')):
    context = {}
    try:
        if len(rules) > 50000 or len(prompt) > 20000:
            raise ValueError('ルールは50,000文字、入力文は20,000文字以内にしてください。')
        parsed = parse_rules(rules)
        if not prompt.strip():
            raise ValueError('判定する文章を入力してください。')
        key = os.getenv('TYPESAFE_API_KEY', '').strip()
        if not key:
            raise ValueError('.env に TYPESAFE_API_KEY を設定し、アプリを再起動してください。')
        payload = {'model': MODEL, 'state': prompt, 'questions': {
            k: {'type': r['type'], 'instructions': r['instructions'], 'criteria': r['criteria']}
            for k, r in parsed.items()}}
        async with httpx.AsyncClient(timeout=30.0) as client:
            start = perf_counter()
            response = await client.post('https://api.typesafe.ai/v1/systemone', json=payload, headers={'Authorization': f'Bearer {key}'})
            elapsed = (perf_counter() - start) * 1000
        if response.status_code != 200:
            messages = {401: 'APIキーを確認してください。', 403: 'APIのアクセス権限を確認してください。', 422: 'APIが設定を受け付けませんでした。ルールを確認してください。', 429: '利用制限に達しました。少し待って再実行してください。', 529: 'Jevが混雑しています。少し待って再実行してください。'}
            raise ValueError(f'APIエラー ({response.status_code})：' + messages.get(response.status_code, '時間をおいて再実行してください。'))
        response_data = response.json()
        context = summarize(response_data, parsed)
        context.update(elapsed=elapsed, prompt=prompt,
                       request_json=json.dumps(payload, ensure_ascii=False, indent=2),
                       response_json=json.dumps(response_data, ensure_ascii=False, indent=2))
    except httpx.TimeoutException:
        context = {'error': '30秒以内に応答がありませんでした。再実行してください。'}
    except httpx.RequestError:
        context = {'error': 'Jev APIへ接続できませんでした。通信環境を確認してください。'}
    except ValueError as exc:
        context = {'error': str(exc)}
    return templates.TemplateResponse(request=request, name='result.html', context=context)
