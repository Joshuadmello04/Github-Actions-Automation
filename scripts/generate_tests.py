#!/usr/bin/env python3
"""
Groq AI Test Generator + Auto-Fixer (Free)
-------------------------------------------
1. Finds all Service and Controller Java files
2. Generates JUnit 5 + Mockito tests via Groq AI
3. Runs mvn test
4. If errors — sends errors back to Groq to fix the test files
5. Fixes pom.xml if missing dependencies
6. Repeats until all tests pass or max retries reached
"""

import os
import re
import glob
import json
import urllib.request
import urllib.error
import sys
import subprocess


MAX_FIX_RETRIES = 3
SRC_ROOT        = "src/main/java"
TEST_ROOT       = "src/test/java"
GROQ_API_URL    = "https://api.groq.com/openai/v1/chat/completions"
MODEL           = "llama-3.3-70b-versatile"


# ─────────────────────────────────────────────
#  Load .env
# ─────────────────────────────────────────────

def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())
        print("✅ Loaded .env file")
    else:
        print("⚠️  No .env file found — using environment variables")


load_env()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")


# ─────────────────────────────────────────────
#  Pretty printing
# ─────────────────────────────────────────────

def banner(msg):
    print(f"\n{'═' * 60}")
    print(f"  {msg}")
    print(f"{'═' * 60}")


def step(msg):
    print(f"\n── {msg}")


def success(msg):
    print(f"   ✅ {msg}")


def warn(msg):
    print(f"   ⚠️  {msg}")


def error(msg):
    print(f"   ❌ {msg}")


# ─────────────────────────────────────────────
#  Install groq SDK if missing
# ─────────────────────────────────────────────

def ensure_groq_sdk():
    try:
        import groq
        success("groq SDK already installed")
    except ImportError:
        print("📦 Installing groq SDK...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "groq", "-q"])
        success("groq SDK installed")


# ─────────────────────────────────────────────
#  Groq API call
# ─────────────────────────────────────────────

def call_groq(system_prompt, user_prompt):
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=4096,
        )
        return response.choices[0].message.content.strip()
    except ImportError:
        pass
    except Exception as e:
        warn(f"SDK error: {e} — trying HTTP...")

    # HTTP fallback
    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
    }).encode("utf-8")

    req = urllib.request.Request(
        GROQ_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type":  "application/json",
            "User-Agent":    "groq-python/0.11.0",
            "Accept":        "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        error(f"HTTP {e.code}: {body}")
        return None
    except Exception as e:
        error(f"Request failed: {e}")
        return None


# ─────────────────────────────────────────────
#  Java file utilities
# ─────────────────────────────────────────────

def find_java_files():
    pattern   = os.path.join(SRC_ROOT, "**", "*.java")
    all_files = glob.glob(pattern, recursive=True)
    targets   = []

    for f in all_files:
        name = os.path.basename(f)
        if (name.endswith("Service.java") or name.endswith("Controller.java")):
            if not name.endswith("Test.java"):
                targets.append(f)

    return targets


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def extract_package(content):
    m = re.search(r"^package\s+([\w.]+);", content, re.MULTILINE)
    return m.group(1) if m else ""


def extract_class_name(content):
    m = re.search(r"public\s+class\s+(\w+)", content)
    return m.group(1) if m else ""


def clean_code(content):
    content = re.sub(r"^```java\s*", "", content, flags=re.MULTILINE)
    content = re.sub(r"^```\s*$",    "", content, flags=re.MULTILINE)
    return content.strip()


# ─────────────────────────────────────────────
#  STEP 1: Generate tests
# ─────────────────────────────────────────────

def generate_test(java_path):
    filename   = os.path.basename(java_path)
    content    = read_file(java_path)
    package    = extract_package(content)
    class_name = extract_class_name(content)
    is_ctrl    = "Controller" in filename

    mock_note = (
        "Use @WebMvcTest and MockMvc for controller tests. Use @MockBean for dependencies."
        if is_ctrl else
        "Use @ExtendWith(MockitoExtension.class) with @Mock and @InjectMocks."
    )

    system = (
        "You are an expert Java developer specializing in JUnit 5 and Mockito. "
        "Output ONLY raw Java code. No markdown, no code fences, no explanation."
    )

    user = f"""Generate a complete JUnit 5 test class for this Java file.

Rules:
- JUnit 5 annotations only (@Test, @BeforeEach, @DisplayName)
- {mock_note}
- ALWAYS include ALL necessary imports explicitly, including:
  import org.mockito.InjectMocks;
  import org.mockito.Mock;
  import org.mockito.junit.jupiter.MockitoExtension;
  import org.junit.jupiter.api.extension.ExtendWith;
  import org.junit.jupiter.api.Test;
  import org.junit.jupiter.api.BeforeEach;
  import static org.mockito.Mockito.*;
  import static org.junit.jupiter.api.Assertions.*;
- Test every public method — happy path + edge cases
- Meaningful camelCase test names
- Assertions on every test
- Package must be: {package}
- Class name must be: {class_name}Test
- Output ONLY the raw Java starting from the package line

Source ({filename}):
{content}"""

    result = call_groq(system, user)
    if not result:
        return None, None

    result = clean_code(result)
    pkg    = extract_package(result)
    cname  = extract_class_name(result)

    if not cname:
        warn(f"Could not extract class name from generated test for {filename}")
        return None, None

    if pkg:
        dest_dir = os.path.join(TEST_ROOT, pkg.replace(".", os.sep))
    else:
        rel      = java_path.replace(SRC_ROOT + os.sep, "").replace(SRC_ROOT + "/", "")
        dest_dir = os.path.join(TEST_ROOT, os.path.dirname(rel))

    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, f"{cname}.java")
    write_file(dest_path, result)
    success(f"Generated: {dest_path}")
    return dest_path, result


# ─────────────────────────────────────────────
#  STEP 2: Run mvn test
# ─────────────────────────────────────────────

def run_maven_test():
    step("Running: mvn test")
    result = subprocess.run(
        "mvn test",
        shell=True,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    print(output[-3000:])
    return result.returncode == 0, output


# ─────────────────────────────────────────────
#  STEP 3: Parse errors from mvn output
# ─────────────────────────────────────────────

def parse_errors(mvn_output):
    errors = {}

    # Compilation errors pointing to a test file
    comp_errors = re.findall(
        r"\[ERROR\].*?(src[\\/]test[\\/]java[\\/][^\s:\[\]]+\.java)[:\[](\d+)[,\]]?(.*)",
        mvn_output,
    )
    for filepath, line, msg in comp_errors:
        filepath = filepath.replace("\\", os.sep).replace("/", os.sep)
        errors.setdefault(filepath, []).append(f"Line {line}: {msg.strip()}")

    # Test failures
    failures = re.findall(
        r"\[ERROR\]\s+([\w.]+)\s*[>\-–]\s*(.*)",
        mvn_output,
    )
    for test_class, reason in failures:
        short   = test_class.split(".")[-1]
        pattern = os.path.join(TEST_ROOT, "**", f"{short}.java")
        matches = glob.glob(pattern, recursive=True)
        for m in matches:
            errors.setdefault(m, []).append(reason.strip())

    # Fallback: general errors
    if "BUILD FAILURE" in mvn_output and not errors:
        lines = [l for l in mvn_output.splitlines() if "[ERROR]" in l]
        errors["__general__"] = lines[:20]

    return errors


# ─────────────────────────────────────────────
#  STEP 4: Fix a test file via Groq
# ─────────────────────────────────────────────

def fix_test_file(test_path, error_msgs, original_source):
    if test_path == "__general__":
        warn("General build error — trying pom.xml fix only")
        return False

    if not os.path.exists(test_path):
        warn(f"Test file not found: {test_path}")
        return False

    current_test = read_file(test_path)
    errors_text  = "\n".join(error_msgs)

    step(f"Fixing: {os.path.basename(test_path)}")
    print(f"   Errors: {errors_text[:300]}")

    system = (
        "You are an expert Java developer. Fix the broken JUnit 5 test file. "
        "Output ONLY the corrected raw Java code. No markdown, no explanation."
    )

    user = f"""Fix this JUnit 5 test file. It has compile/runtime errors.

ERRORS TO FIX:
{errors_text}

CURRENT BROKEN TEST FILE:
{current_test}

ORIGINAL SOURCE FILE (for reference):
{original_source}

Rules:
- Keep the same package and class name
- Fix ALL listed errors
- Do not remove working tests
- Output ONLY corrected raw Java code starting from package declaration"""

    fixed = call_groq(system, user)
    if not fixed:
        error("Groq returned no fix")
        return False

    fixed = clean_code(fixed)
    if not extract_class_name(fixed):
        error("Fixed code has no class name — skipping")
        return False

    write_file(test_path, fixed)
    success(f"Fixed: {test_path}")
    return True


# ─────────────────────────────────────────────
#  STEP 5: Fix pom.xml dependencies
# ─────────────────────────────────────────────

REQUIRED_DEPS = {
    "mockito-core": """        <dependency>
            <groupId>org.mockito</groupId>
            <artifactId>mockito-core</artifactId>
            <scope>test</scope>
        </dependency>""",

    "spring-boot-starter-test": """        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>""",

    "junit-jupiter": """        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>""",
}


def fix_pom_if_needed(mvn_output):
    if not os.path.exists("pom.xml"):
        warn("pom.xml not found")
        return

    pom     = read_file("pom.xml")
    changed = False

    for artifact, dep_xml in REQUIRED_DEPS.items():
        if artifact not in pom:
            pom     = pom.replace("</dependencies>", f"{dep_xml}\n    </dependencies>", 1)
            changed = True
            success(f"Added to pom.xml: {artifact}")

    if changed:
        write_file("pom.xml.bak", read_file("pom.xml"))
        write_file("pom.xml", pom)
        success("pom.xml updated (backup: pom.xml.bak)")
    else:
        success("pom.xml already has all required dependencies")


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────

def main():
    banner("🤖 Groq AI — Generate → Run → Fix → Repeat")

    if not GROQ_API_KEY:
        error("GROQ_API_KEY not set! Add it to your .env file: GROQ_API_KEY=gsk_...")
        sys.exit(1)

    if not GROQ_API_KEY.startswith("gsk_"):
        warn(f"Key doesn't look like a Groq key: {GROQ_API_KEY[:10]}...")

    print(f"   🔑 Key: {GROQ_API_KEY[:8]}...{GROQ_API_KEY[-4:]}")

    ensure_groq_sdk()

    # ── Find source files ────────────────────────────
    step("Finding Service and Controller files...")
    java_files = find_java_files()

    if not java_files:
        warn("No Service or Controller files found in src/main/java")
        sys.exit(0)

    print(f"   Found {len(java_files)} file(s):")
    for f in java_files:
        print(f"   • {f}")

    source_map = {f: read_file(f) for f in java_files}

    # ── STEP 1: Generate tests ───────────────────────
    banner("STEP 1 — Generating Tests")
    generated = {}

    for java_path in java_files:
        step(f"Generating: {os.path.basename(java_path)}")
        test_path, _ = generate_test(java_path)
        if test_path:
            generated[test_path] = java_path

    if not generated:
        error("No tests were generated. Check your Groq API key.")
        sys.exit(1)

    print(f"\n   Generated {len(generated)} test file(s):")
    for t in generated:
        print(f"   • {t}")

    # ── STEP 2: Fix pom.xml before running ──────────
    banner("STEP 2 — Checking pom.xml")
    fix_pom_if_needed("")

    # ── STEP 3: Run → Fix loop ───────────────────────
    banner("STEP 3 — Run → Fix → Repeat")

    for attempt in range(1, MAX_FIX_RETRIES + 2):
        label = "First run" if attempt == 1 else f"Re-run after fix #{attempt - 1}"
        print(f"\n🧪 {label} (attempt {attempt} of {MAX_FIX_RETRIES + 1})...")

        passed, mvn_output = run_maven_test()

        if passed:
            banner("✅ ALL TESTS PASSED!")
            break

        if attempt > MAX_FIX_RETRIES:
            banner("❌ Max retries reached — manual review needed")
            sys.exit(1)

        print(f"\n🔧 Auto-fixing errors (round {attempt}/{MAX_FIX_RETRIES})...")
        errors_map = parse_errors(mvn_output)

        if not errors_map:
            warn("Could not parse specific errors — trying pom.xml fix only")
            fix_pom_if_needed(mvn_output)
            continue

        # Fix pom if dependency errors
        dep_keywords = ["cannot find symbol", "package does not exist", "classnotfoundexception"]
        if any(kw in mvn_output.lower() for kw in dep_keywords):
            fix_pom_if_needed(mvn_output)

        # Fix each broken test file
        any_fixed = False
        for test_path, err_msgs in errors_map.items():
            if test_path == "__general__":
                fix_pom_if_needed(mvn_output)
                continue
            src_path    = generated.get(test_path, "")
            src_content = source_map.get(src_path, "")
            if fix_test_file(test_path, err_msgs, src_content):
                any_fixed = True

        if not any_fixed:
            warn("Nothing was fixed this round — stopping loop")
            break

    # ── Final summary ────────────────────────────────
    banner("Summary")
    print(f"  Source files : {len(java_files)}")
    print(f"  Tests created: {len(generated)}")
    print(f"\n  📂 Test files:")
    all_tests = glob.glob(os.path.join(TEST_ROOT, "**", "*.java"), recursive=True)
    for t in sorted(all_tests):
        print(f"     • {t}")


if __name__ == "__main__":
    main()