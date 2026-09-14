import json

with open("dataset/sample_eval.json", "r", encoding="utf-8") as f:
    raw = json.load(f)

converted = []
for item in raw:
    expected = item["expected_output"]
    evaluator = "exact_match" if len(expected) <= 15 and "\n" not in expected else "llm_judge"
    converted.append({
        "id": item["id"],
        "question": item["prompt"],
        "expected_answer": expected,
        "evaluator": evaluator,
        "metadata": {"system_prompt": item.get("system_prompt", "")}
    })

with open("dataset/sample_eval.json", "w", encoding="utf-8") as f:
    json.dump(converted, f, indent=2)

print(f"Converted {len(converted)} samples.")
