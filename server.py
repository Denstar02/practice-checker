from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import os
import json
import re

app = Flask(__name__, static_folder="static")
CORS(app)

IO_API_URL = "https://api.intelligence.io.solutions/api/v1/chat/completions"
IO_API_KEY = os.environ.get(
    "IO_API_KEY",
    "io-v2-eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJvd25lciI6ImIyNjI2Mzc0LTQ0NDEtNGU0NC04MTA4LTRhZjc5MGNkMTgzZCIsImV4cCI6NDkyNjY4MjMwOH0.pbY8BRGPzxpldajiQBki1Pm1WqKWotkFs9zvcN5N0aEkmavB7JgNT-YyAPzGTTh_yTM9dSyDLLoE6N4QP5Wt5w",
)
DEFAULT_MODEL = "meta-llama/Llama-3.3-70B-Instruct"

def build_prompt(criteria_list):
    crit_text = ""
    for i, c in enumerate(criteria_list, 1):
        title = c.get("title", f"Критерий {i}")
        desc = c.get("description", "")
        crit_text += f"\n{i}. {title.upper()}\n{desc}\n"

    return f"""Ты — экспертный анализатор отчётов по педагогической практике для студентов педагогических вузов. Твоя задача — провести детальный анализ загруженного отчёта по следующим {len(criteria_list)} критериям и выдать по каждому структурированную оценку.

КРИТЕРИИ ОЦЕНКИ:
{crit_text}
ФОРМАТ ОТВЕТА (строго JSON):
{{
  "overall_score": число от 0 до 100,
  "overall_summary": "Общее заключение по отчёту (2-3 предложения)",
  "criteria": [
    {{
      "id": 1,
      "score": число от 0 до 100,
      "status": "выполнено" | "частично" | "не выполнено",
      "found_elements": ["список найденных элементов"],
      "missing_elements": ["список отсутствующих элементов"],
      "comment": "Подробный комментарий",
      "recommendations": ["рекомендации по доработке"]
    }}
  ]
}}

ВАЖНО: в массиве criteria должно быть ровно {len(criteria_list)} объектов — по одному на каждый критерий, в том же порядке.
Отвечай ТОЛЬКО валидным JSON без markdown-разметки, без ```json, без пояснений до и после JSON.
КРИТИЧЕСКИ ВАЖНО: внутри строковых значений JSON НЕЛЬЗЯ использовать неэкранированные кавычки, переносы строк и спецсимволы. Используй только простой текст без кавычек."""


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/models", methods=["GET"])
def get_models():
    try:
        resp = requests.get(
            "https://api.intelligence.io.solutions/api/v1/models",
            headers={"Authorization": f"Bearer {IO_API_KEY}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("data", [])
            result = [{"id": m.get("id"), "name": m.get("id", "").split("/")[-1]} for m in models if m.get("id")]
            print(f"[INFO] Доступные модели: {[m['id'] for m in result[:5]]}...")
            return jsonify(result)
        else:
            print(f"[WARN] Не удалось получить модели: {resp.status_code}")
    except Exception as e:
        print(f"[WARN] Ошибка при получении моделей: {e}")

    return jsonify([
        {"id": "meta-llama/Llama-3.3-70B-Instruct", "name": "Llama 3.3 70B"},
        {"id": "deepseek-ai/DeepSeek-V3", "name": "DeepSeek V3"},
        {"id": "Qwen/Qwen2.5-72B-Instruct", "name": "Qwen 2.5 72B"},
        {"id": "mistralai/Mistral-Small-24B-Instruct-2501", "name": "Mistral Small 24B"},
    ])


@app.route("/api/test", methods=["GET"])
def test_api():
    try:
        resp = requests.post(
            IO_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {IO_API_KEY}",
            },
            json={
                "model": DEFAULT_MODEL,
                "messages": [{"role": "user", "content": "Ответь одним словом: привет"}],
                "max_completion_tokens": 20,
                "stream": False,
            },
            timeout=30,
        )
        print(f"[TEST] status={resp.status_code}, body={resp.text[:200]}")
        return jsonify({"status": resp.status_code, "body": resp.json() if resp.status_code == 200 else resp.text[:300]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    text = data.get("text", "")
    model = data.get("model", DEFAULT_MODEL)
    criteria = data.get("criteria", None)

    if not criteria:
        criteria = [
            {"title": "Анализ нормативной и учебно-программной документации",
             "description": "Проверь наличие и качество анализа: ФГОС СПО, ОПОП, учебного плана, рабочих программ дисциплин, профессиональных модулей, МДК."},
            {"title": "Место дисциплины в подготовке специалиста",
             "description": "Проверь: определено ли место дисциплины в подготовке студента, вклад в компетенции, курс, объём нагрузки, таблица."},
            {"title": "Междисциплинарные связи",
             "description": "Проверь: определены ли предшествующие, сопутствующие и последующие связи, схема."},
            {"title": "Внутридисциплинарные связи",
             "description": "Проверь: проведён ли анализ КТП, связи темы, схема."},
        ]

    system_prompt = build_prompt(criteria)

    if not text.strip():
        return jsonify({"error": "Текст отчёта пуст"}), 400

    if len(text) > 12000:
        text = text[:12000] + "\n\n[...текст обрезан до 12000 символов...]"

    try:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Проанализируй отчёт по педагогической практике:\n\n{text}",
                },
            ],
            "temperature": 0.3,
            "max_completion_tokens": 4000,
            "stream": False,
        }

        print(f"[INFO] Запрос к API: model={model}, text_len={len(text)}, criteria_count={len(criteria)}")

        resp = requests.post(
            IO_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {IO_API_KEY}",
            },
            json=payload,
            timeout=120,
        )

        if resp.status_code != 200:
            print(f"[ERROR] API status={resp.status_code}, body={resp.text[:500]}")
            return jsonify({
                "error": f"Ошибка API ({resp.status_code}): {resp.text[:300]}"
            }), 502

        result = resp.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        if not content:
            return jsonify({"error": "Пустой ответ от API"}), 502

        content_clean = re.sub(r"```json\s*", "", content)
        content_clean = re.sub(r"```\s*", "", content_clean).strip()

        parsed = None

        try:
            parsed = json.loads(content_clean)
        except json.JSONDecodeError:
            pass

        if parsed is None:
            m = re.search(r"\{[\s\S]*\}", content)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass

        if parsed is None:
            try:
                fixed = content_clean
                fixed = re.sub(r'[\x00-\x1f]', ' ', fixed)
                m = re.search(r'\{[\s\S]*\}', fixed)
                if m:
                    block = m.group(0)
                    block = re.sub(r',\s*([}\]])', r'\1', block)
                    parsed = json.loads(block)
            except json.JSONDecodeError:
                pass

        if parsed is None:
            print(f"[WARN] JSON не распознан, пробуем повторный запрос для починки...")
            try:
                fix_resp = requests.post(
                    IO_API_URL,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {IO_API_KEY}",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "Ты получаешь сломанный JSON. Исправь его и верни ТОЛЬКО валидный JSON. Не добавляй ничего кроме JSON."},
                            {"role": "user", "content": f"Исправь этот JSON:\n{content[:3000]}"},
                        ],
                        "temperature": 0.1,
                        "max_completion_tokens": 4000,
                        "stream": False,
                    },
                    timeout=60,
                )
                if fix_resp.status_code == 200:
                    fix_content = fix_resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                    fix_clean = re.sub(r"```json\s*", "", fix_content)
                    fix_clean = re.sub(r"```\s*", "", fix_clean).strip()
                    try:
                        parsed = json.loads(fix_clean)
                    except json.JSONDecodeError:
                        m = re.search(r'\{[\s\S]*\}', fix_clean)
                        if m:
                            parsed = json.loads(m.group(0))
            except Exception as fix_err:
                print(f"[WARN] Повторный запрос тоже не удался: {fix_err}")

        if parsed is None:
            return jsonify({
                "error": "Не удалось распознать JSON из ответа модели. Попробуйте другую модель.",
                "raw": content[:500]
            }), 502

        return jsonify(parsed)

    except requests.exceptions.Timeout:
        return jsonify({"error": "Таймаут запроса к API (120с)"}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Ошибка запроса к API: {str(e)}"}), 502
    except json.JSONDecodeError as e:
        return jsonify({"error": f"Ошибка парсинга JSON: {str(e)}"}), 502


if __name__ == "__main__":
    print("=" * 50)
    print("  Анализатор отчётов по педпрактике")
    print("  Откройте в браузере: http://localhost:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True)
