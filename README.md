# Jev Guardrail Demo

JevをLLMガードレールの判定器として使い、ルールに沿った判定と応答時間・費用を確認する小さなWebアプリです。架空の製造業「デモ精機」のAIアシスタントへの入力チェックを想定しています。

- UIでルールを追加・削除・編集し、確認用JSONを自動更新
- サンプル選択・自由入力
- プロンプトインジェクション／暴力／個人情報／競合批判の4項目を1回のAPIリクエストで評価
- 総合結果（Blocked / Passed）、項目別の該当確率を大きな数値（%）とバーで表示
- 通信込みの応答時間と推定費用を表示

LLM比較、文章生成、実際のLLMへの転送、履歴保存、人への振り分けはありません。Blocked / Passedは、このデモ内の判定表示です。

## セットアップ・起動（WSL2 / Linux / macOS）

Python 3.11以上、[uv](https://docs.astral.sh/uv/getting-started/installation/)、TypeSafe APIキー、インターネット接続を用意してください。

```bash
cd jev-guardrail-demo
uv sync
cp .env.example .env
```

`.env`をエディタで開いて設定します。

```dotenv
TYPESAFE_API_KEY=取得したAPIキー
```

```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

ブラウザで http://localhost:8000 を開きます。WSL2でもWindows側のブラウザからアクセスできます。終了はCtrl+Cです。キー変更後はアプリを再起動してください。

キーは[TypeSafe Console](https://console.typesafe.ai/)で取得します。キーはサーバー側のみで使用し、ブラウザには渡しません。キーがなくても初期画面は開けますが判定はできません。API利用には料金が発生します。

Windows PowerShellではコピー操作を `Copy-Item .env.example .env` に置き換えてください。

## 使い方

1. 左のルールを開き、判定形式・判定指示・基準・Blocked条件を設定します。「＋ ルール追加」で追加できます。下部のJSONは読み取り専用です。
2. サンプルボタンを押すか、文章を入力します。選択後も文章は自由に編集できます。
3. 「Jevで判定する」を押します。
4. 結果を確認し、ルールや閾値を変えて再実行します。

「初期値に戻す」はルール設定全体を戻します。入力文と判定基準はTypeSafe APIへ送信されます。画面での編集内容は保存されず、ページ再読み込みで初期化されます。既定値を恒久変更する場合は `app/rules.json` を編集し、再起動してください。サンプルは `app/samples.json` にあります。会社・個人名、連絡先は架空です。

## ルール設定とJSON

各ルールを開き、表示名・形式・指示・定義を編集します。変更は即座にJSONへ反映されます。JSONは確認用で直接編集できません。ルールは1〜10個です。

| 形式 | 定義 | Blocked条件 | 結果表示 |
| --- | --- | --- | --- |
| Noul | 該当・非該当の基準 | 確率が閾値以上（0〜1） | 該当確率の%・バー |
| Choice | 選択肢名と定義。追加・削除可能 | 選ばれた選択肢がBlocked対象 | 選択結果・各選択肢の確率 |
| Score | 0から始まる順序付きレベルの定義。追加・削除可能 | スコアが閾値以上 | スコア・バー |

Choiceは2個以上の選択肢と1個以上のBlocked対象、Scoreは2〜10レベルを設定します。Scoreは整数ラベルではなく確率加重スコアのため小数になり得ます。形式を変更すると、その形式の基準とBlocked条件は初期化されます。

各ルールの条件をORで結合し、1個でも該当すればBlocked、すべて非該当ならPassedです。初期閾値0.5はデモ用です。確率は正解率を保証する値ではありません。比較は丸め前の数値で行います。

JSONはトップレベルの `rules` にルールIDをキーとして格納します。共通フィールドは `label`, `type`, `instructions`, `criteria`。Noul／Scoreは `threshold`、Choiceは `blocked_choices` を持ちます。APIには `type`, `instructions`, `criteria` を送り、Blocked条件はアプリ側で適用します。複数形式を一度のリクエストで評価します。

## 応答時間・費用

モデルは `jev-1.13.0` に固定しています。

- 応答時間：サーバーからHTTPリクエストを開始して応答本文を受信するまで。DNS/TLS・ネットワークを含み、ブラウザ描画やJSON検証は含みません。モデル内部の推論時間だけではありません。
- 毎回APIを呼び出し、キャッシュや自動再試行は行いません。エラー時は結果を表示せず、再実行を案内します。
- 推定費用（USD）：API応答の `usage.input_tokens × 0.042 / 1,000,000`。入力文だけでなく、APIが報告した課金対象入力全体を使用します。
- 単価：2026-09-25確認時点で入力100万トークンあたり$0.042、出力無料。入力1,000トークンなら$0.000042です。

単価は `app/main.py` の `PRICE`、画面フッターとこのREADMEに記載しています。モデルや料金を更新する際は公式料金を再確認して併せて更新してください。

## 構成

uv / FastAPI / Jinja2 / htmx / HTTPX。htmx 2.0.4とCodeMirror 5.65.16はCDNから読み込みます。エディタを読み込めない場合も、通常の読み取り専用欄でJSONを確認できます。Jevは公式REST APIをHTTPXから呼び出します。

```text
app/main.py          API呼び出し・検証・閾値判定
app/rules.json       初期ルール
app/samples.json     サンプル文章
app/templates/       初期画面・結果部分のHTML
app/static/          CSS・画面操作
tests/              APIを呼ばない自動テスト
```

## 検証

```bash
uv run pytest
```

自動テストはHTTP通信を置き換え、閾値の境界、費用計算、異常応答、画面/API連携を検証します。Jevの分類精度・速度や実際の認証成功を検証するものではありません。実APIは設定したキーで画面から確認してください。


## 参考資料

- [公式ガードレール実装例](https://docs.typesafe.ai/cookbooks/llm_guardrails)
- [APIリファレンス](https://docs.typesafe.ai/api)
- [Noul](https://docs.typesafe.ai/primitives/noul)
- [モデル・料金](https://docs.typesafe.ai/models)