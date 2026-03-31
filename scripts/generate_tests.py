import os
import requests
import re
import subprocess

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "llama-3.1-8b-instant"


# 🧹 CLEAN OUTPUT
def clean_llm_output(text):
    if not text:
        return None

    # remove markdown
    text = text.replace("```java", "").replace("```", "")

    # keep only from package
    if "package " in text:
        text = text[text.index("package "):]

    # remove anything AFTER last closing brace
    last_brace = text.rfind("}")
    if last_brace != -1:
        text = text[:last_brace + 1]

    return text.strip()


# 🧠 BASIC STRUCTURE VALIDATION
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


# 🤖 LLM CALL
def generate_test(java_code, class_name, layer):

    if layer == "controller":
        extra_rules = """
- Use @WebMvcTest
- Use @MockBean for dependencies
- Use MockMvc for testing endpoints
"""
    elif layer == "service":
        extra_rules = """
- Use @Mock and @InjectMocks
- Mock repository layer
"""
    else:
        extra_rules = """
- Simple unit test
"""

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
            "messages": [{"role": "user", "content": prompt}]
        }
    )

    data = response.json()

    if "choices" not in data:
        print("❌ API Error:", data)
        return None

    raw = data["choices"][0]["message"]["content"]
    return clean_llm_output(raw)

# 🔧 COMPILE CHECK
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

    # Define a set of classes that don't need unit tests
    # Using a set is faster for lookups as your list grows!
    SKIP_LIST = {"DemoApplication", "ServletInitializer"}

    for root, _, files in os.walk(src_dir):
        for file in files:
            if not file.endswith(".java"):
                continue

            # 1. Get the class name first
            class_name = file.replace(".java", "")

            # 2. ❌ Skip useless classes immediately
            if class_name in SKIP_LIST:
                print(f"⏭ Skipping {class_name} (No test needed)")
                continue

            path = os.path.join(root, file)
            print(f"\n🔍 Processing {path}")

            with open(path, "r") as f:
                code = f.read()

            layer = detect_layer(path)

            # 3. Proceed to AI generation
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

            # write temp file
            temp_path = test_path + ".tmp"
            with open(temp_path, "w") as f:
                f.write(test_code)

            # replace and test compile
            os.replace(temp_path, test_path)

            if is_compilable():
                print(f"✅ Valid test saved: {class_name}")
            else:
                if os.path.exists(test_path):
                    os.remove(test_path)
                print(f"❌ Compilation failed, discarded: {class_name}")

                
if __name__ == "__main__":
    process_files()