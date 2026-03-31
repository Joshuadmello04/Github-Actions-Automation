import os
import requests

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.1-8b-instant"


def clean_llm_output(text):
    if not text:
        return None

    text = text.replace("```java", "").replace("```", "")

    if "package " in text:
        text = text[text.index("package "):]

    return text.strip()


def detect_layer(path):
    if "controller" in path:
        return "controller"
    elif "service" in path:
        return "service"
    elif "repository" in path:
        return "repository"
    elif "entity" in path:
        return "entity"
    else:
        return "misc"


def generate_test(java_code, class_name, layer):
    prompt = f"""
You are a senior Java backend engineer.

Generate STRICTLY VALID JUnit 5 + Mockito test class.

Rules:
- NO markdown
- NO explanation
- ONLY pure Java code
- Must include correct package
- Package must be: com.example.demo.{layer}
- Class name: {class_name}Test
- Include necessary imports
- Cover basic + edge cases

Layer: {layer}

Class:
{java_code}
"""

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
    )

    data = response.json()

    if "choices" not in data:
        print("❌ API Error:", data)
        return None

    raw = data["choices"][0]["message"]["content"]
    return clean_llm_output(raw)


def process_files():
    src_dir = "src/main/java/com/example/demo"
    test_base_dir = "src/test/java/com/example/demo"

    for root, _, files in os.walk(src_dir):
        for file in files:
            if not file.endswith(".java"):
                continue

            path = os.path.join(root, file)
            print(f"🔍 Processing {path}")

            with open(path, "r") as f:
                code = f.read()

            class_name = file.replace(".java", "")
            layer = detect_layer(path)

            test_code = generate_test(code, class_name, layer)

            if not test_code:
                print(f"❌ Failed for {class_name}")
                continue

            test_path = os.path.join(
                test_base_dir,
                layer,
                f"{class_name}Test.java"
            )

            os.makedirs(os.path.dirname(test_path), exist_ok=True)

            # 🔥 ALWAYS overwrite (as you requested full regen)
            with open(test_path, "w") as f:
                f.write(test_code)

            print(f"✅ Generated {test_path}")


if __name__ == "__main__":
    process_files()