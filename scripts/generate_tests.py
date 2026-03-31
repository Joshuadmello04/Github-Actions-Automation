import os
import requests
import subprocess

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"

# 🧹 CLEAN OUTPUT
def clean_llm_output(text):
    if not text:
        return None

    text = text.replace("```java", "").replace("```", "")

    if "package " in text:
        text = text[text.index("package "):]

    last_brace = text.rfind("}")
    if last_brace != -1:
        text = text[:last_brace + 1]

    return text.strip()


# 🧠 BASIC VALIDATION
def is_valid_java_test(code):
    if not code:
        return False

    return (
        "class " in code and
        "@Test" in code and
        code.count("{") >= code.count("}")
    )


# 🧱 LAYER DETECTION
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


# 🤖 LLM GENERATION (SMART PROMPTS)
def generate_test(java_code, class_name, layer):

    if layer == "controller":
        extra_rules = """
- Use @WebMvcTest
- Use @MockBean for service layer
- Use MockMvc
- DO NOT mock primitive or wrapper types (Long, String, Integer)
"""
    elif layer == "service":
        extra_rules = """
- Use @Mock and @InjectMocks
- Mock ONLY repository dependencies
- DO NOT mock primitive or wrapper types
"""
    else:
        extra_rules = ""

    prompt = f"""
You are a senior Java backend engineer.

Generate STRICTLY VALID JUnit 5 + Mockito test class.

STRICT RULES:
- ONLY Java code
- NO explanations
- NO markdown
- EXACTLY one public class
- Must compile
- Class name MUST be {class_name}Test
- Package: com.example.demo.{layer}
- Include necessary imports

{extra_rules}

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


# 🔧 COMPILE CHECK (VERY IMPORTANT)
def is_compilable():
    result = subprocess.run(
        ["mvn", "-q", "-DskipTests", "test-compile"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return result.returncode == 0


# 🔁 MAIN PROCESS
def process_files():
    src_dir = "src/main/java/com/example/demo"
    test_base_dir = "src/test/java/com/example/demo"

    for root, _, files in os.walk(src_dir):
        for file in files:
            if not file.endswith(".java"):
                continue

            path = os.path.join(root, file)
            print(f"\n🔍 Processing {path}")

            class_name = file.replace(".java", "")
            layer = detect_layer(path)

            # 🚫 SKIP BAD TARGETS (CRITICAL FIX)
            if layer in ["entity", "repository"] or class_name == "DemoApplication":
                print(f"⏭ Skipping {class_name} ({layer})")
                continue

            with open(path, "r") as f:
                code = f.read()

            test_code = generate_test(code, class_name, layer)

            if not test_code:
                print(f"❌ LLM failed for {class_name}")
                continue

            if not is_valid_java_test(test_code):
                print(f"❌ Invalid structure: {class_name}")
                continue

            test_path = os.path.join(
                test_base_dir,
                layer,
                f"{class_name}Test.java"
            )

            os.makedirs(os.path.dirname(test_path), exist_ok=True)

            temp_path = test_path + ".tmp"

            # write temp file
            with open(temp_path, "w") as f:
                f.write(test_code)

            # replace and compile check
            os.replace(temp_path, test_path)

            if is_compilable():
                print(f"✅ Valid test saved: {class_name}")
            else:
                os.remove(test_path)
                print(f"❌ Compilation failed, discarded: {class_name}")


if __name__ == "__main__":
    process_files()