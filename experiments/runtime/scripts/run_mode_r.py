"""T-008: Mode R (Recall) query — LLM knowledge-based prediction.

Mode R asks the SAME LLM used in the simulation (gpt-4.1-mini) to predict,
from general knowledge alone, what would happen if the approval threshold
were raised from 200k to 5M yen in a mid-size manufacturing company's
purchase approval flow.

The response is structured into discrete event predictions so that each
can be compared against actual Mode S (simulation) observations from exp004.

Usage (from experiments/runtime/ with venv activated):
    python scripts/run_mode_r.py

Outputs:
    - experiments/mode_r_t008/raw_response.txt     (full LLM response)
    - experiments/mode_r_t008/structured_events.json (parsed event list)
    - stderr: summary
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RUNTIME_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME_DIR))

# ---- .env loader ----
def _load_dotenv() -> None:
    env_path = RUNTIME_DIR / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

_load_dotenv()

# ---- Configuration ----
MODEL = "gpt-4.1-mini"
TEMPERATURE = 0.8  # Same as simulation
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "mode_r_t008"

# ---- Mode R Prompt ----
MODE_R_SYSTEM = """あなたは組織論・内部統制の専門家です。中堅製造業の購買承認フローについて、
あなたの知識に基づいて回答してください。シミュレーション結果は参照せず、
一般的な組織行動の知識のみに基づいて回答してください。"""

MODE_R_USER = """中堅製造業の購買承認フローにおいて、承認閾値を20万円から500万円に
引き上げた場合、以下の各観点からどのような影響が考えられますか？
具体的なシナリオを挙げてください。

1. 購買担当者の行動変化
2. 承認者の役割変化
3. 取引先の行動変化
4. 経理部門への影響
5. 統制品質（三者照合等）への影響
6. 予期しない副次効果

【回答形式の指示】
各観点について、予測される具体的なイベント/行動変化を箇条書きで列挙してください。
各イベントには以下の情報を含めてください：
- イベントID（R-001, R-002, ...）
- 観点番号（1〜6）
- 予測内容（1文で簡潔に）
- 確信度（高/中/低）
- 根拠（1文で）

最後に、JSON形式でも同じ情報を出力してください。フォーマット：
```json
[
  {"id": "R-001", "category": 1, "prediction": "...", "confidence": "高", "rationale": "..."},
  ...
]
```"""


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY is not set", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Call OpenAI API ----
    import urllib.request
    import urllib.error

    payload = json.dumps({
        "model": MODEL,
        "temperature": TEMPERATURE,
        "messages": [
            {"role": "system", "content": MODE_R_SYSTEM},
            {"role": "user", "content": MODE_R_USER},
        ],
        "max_tokens": 4096,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    print(f"Sending Mode R query to {MODEL} (temp={TEMPERATURE})...", file=sys.stderr)

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"API ERROR {e.code}: {body}", file=sys.stderr)
        return 1

    # ---- Extract response ----
    content = result["choices"][0]["message"]["content"]
    usage = result.get("usage", {})

    print(f"Response received. Tokens: prompt={usage.get('prompt_tokens', '?')}, "
          f"completion={usage.get('completion_tokens', '?')}", file=sys.stderr)

    # ---- Save raw response ----
    raw_path = OUTPUT_DIR / "raw_response.txt"
    raw_path.write_text(content, encoding="utf-8")
    print(f"Raw response saved: {raw_path}", file=sys.stderr)

    # ---- Extract JSON block ----
    json_start = content.find("```json")
    json_end = content.find("```", json_start + 7) if json_start >= 0 else -1

    if json_start >= 0 and json_end >= 0:
        json_text = content[json_start + 7:json_end].strip()
        try:
            events = json.loads(json_text)
            structured_path = OUTPUT_DIR / "structured_events.json"
            structured_path.write_text(
                json.dumps(events, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            print(f"Structured events saved: {structured_path} ({len(events)} events)",
                  file=sys.stderr)

            # ---- Summary ----
            print("\n--- MODE R PREDICTION SUMMARY ---", file=sys.stderr)
            for ev in events:
                print(f"  {ev['id']} [cat={ev['category']}, conf={ev['confidence']}]: "
                      f"{ev['prediction']}", file=sys.stderr)
            print(f"\nTotal predictions: {len(events)}", file=sys.stderr)

        except json.JSONDecodeError as e:
            print(f"WARNING: Failed to parse JSON block: {e}", file=sys.stderr)
            print(f"JSON text was:\n{json_text[:500]}", file=sys.stderr)
    else:
        print("WARNING: No ```json block found in response", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
