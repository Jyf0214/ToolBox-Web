import re
import sys
import os

# 定义废话注释的正则模式
BAD_COMMENT_PATTERNS = [
    r"^#\s*(todo|fix|test|comment|code|logic|update|temporary|changed|asdf|check|debug)$",
    r"^#\s*this is a (variable|function|class|line|method|code)$",
    r"^#\s*do (something|it|logic|work)$",
    r"^#\s*ok(ay)?$",
    r"^#\s*\.+$",
    r"^#\s*[-=]{3,}$",
]


def check_file(filepath):
    errors = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                clean_line = line.strip().lower()
                if clean_line.startswith("#"):
                    for pattern in BAD_COMMENT_PATTERNS:
                        if re.match(pattern, clean_line):
                            errors.append(
                                f"Line {i}: Meaningless comment found: '{clean_line}'"
                            )
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
    return errors


def main():
    all_errors = {}
    app_dir = "app"

    if not os.path.exists(app_dir):
        return 0

    for root, _, files in os.walk(app_dir):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                errors = check_file(path)
                if errors:
                    all_errors[path] = errors

    if all_errors:
        print("Pre-commit Check Failed: Meaningless comments detected!")
        for path, errors in all_errors.items():
            print(f"\nFile: {path}")
            for err in errors:
                print(f"  {err}")
        return 1

    print("Comment check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
