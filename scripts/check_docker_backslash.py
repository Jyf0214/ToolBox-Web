import sys
import os


def check_dockerfile(filepath):
    errors = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for i, line in enumerate(lines):
            stripped_full = line.strip()
            # 1. 检查斜杠前方：如果该行除了斜杠只有空白，则拦截 (包括斜杠前方没有任何内容的情况)
            if stripped_full == "\\":
                errors.append(
                    f"Line {i + 1}: Backslash '\\' must have content before it on the same line."
                )
                continue

            # 2. 检查斜杠后方
            rstrip_line = line.rstrip()
            if rstrip_line.endswith("\\"):
                # 检查斜杠后是否有非空白字符
                trailing = line[len(rstrip_line) :].replace("\n", "").replace("\r", "")
                if trailing.strip():
                    errors.append(
                        f"Line {i + 1}: Trailing characters found after backslash."
                    )

                # 检查后续行是否有有效内容 (排除注释和空行)
                has_next_content = False
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if next_line and not next_line.startswith("#"):
                        has_next_content = True
                        break

                if not has_next_content:
                    errors.append(
                        f"Line {i + 1}: Dangling backslash with no subsequent valid instruction."
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
        print("Pre-commit Check Failed: Dockerfile format issues!")
        for path, errors in all_errors.items():
            print(f"\nFile: {path}")
            for err in errors:
                print(f"  {err}")
        sys.exit(1)
    return 0


if __name__ == "__main__":
    main()
