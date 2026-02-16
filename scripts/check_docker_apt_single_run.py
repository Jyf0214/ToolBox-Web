import sys
import os


def check_apt_single_run(filepath):
    errors = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        apt_run_count = 0
        for line in lines:
            stripped = line.strip()
            # 统计以 RUN 开头且包含 apt 的行
            if stripped.startswith("RUN ") and (
                "apt-get" in stripped or "apt " in stripped
            ):
                apt_run_count += 1

        if apt_run_count > 1:
            errors.append(
                f"Detected {apt_run_count} separate RUN instructions for apt."
            )
            errors.append(
                "All apt commands must be combined into a single RUN instruction using '&&' and '\\'."
            )

    except Exception as e:
        print(f"Error analyzing {filepath}: {e}")
    return errors


def main():
    target_files = ["Dockerfile.base", "Dockerfile"]
    all_errors = {}
    for filename in target_files:
        if os.path.exists(filename):
            errs = check_apt_single_run(filename)
            if errs:
                all_errors[filename] = errs

    if all_errors:
        print("Pre-commit Check Failed: APT commands must be consolidated!")
        for path, errs in all_errors.items():
            print(f"\nFile: {path}")
            for e in errs:
                print(f"  {e}")
        sys.exit(1)
    return 0


if __name__ == "__main__":
    main()
