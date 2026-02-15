import sys
import os


def check_dockerfile(filepath):
    errors = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for i, line in enumerate(lines):
            stripped = line.rstrip()
            # 检查是否以反斜杠结尾
            if stripped.endswith("\\"):
                # 检查斜杠后是否有非空白字符
                trailing = line[len(stripped) :].replace("\n", "").replace("\r", "")
                if trailing.strip():
                    errors.append(
                        f"Line {i + 1}: Trailing characters found after backslash."
                    )

                # 检查后续行是否有有效内容
                has_next_content = False
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    # 忽略空行和注释行
                    if next_line and not next_line.startswith("#"):
                        has_next_content = True
                        break

                if not has_next_content:
                    errors.append(
                        f"Line {i + 1}: Dangling backslash with no subsequent valid content."
                    )

    except Exception as e:
        print(f"Error reading {filepath}: {e}")
    return errors


def main():
    target_files = ["Dockerfile", "Dockerfile.base"]
    all_errors = {}

    for filename in target_files:
        if os.path.exists(filename):
            errors = check_dockerfile(filename)
            if errors:
                all_errors[filename] = errors

    if all_errors:
        print("Pre-commit Check Failed: Dockerfile backslash issues detected!")
        for path, errors in all_errors.items():
            print(f"\nFile: {path}")
            for err in errors:
                print(f"  {err}")
        print("\nPlease ensure all backslashes are followed by valid instructions.")
        return 1

    print("Dockerfile backslash check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
