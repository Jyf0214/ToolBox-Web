import json
import subprocess
import sys


def run_security_check():
    # 运行 bandit 并获取 JSON 结果
    # --ignore-nosec: 忽略代码中的 #nosec 注释
    # -l: 报告所有级别的漏洞 (LOW 及以上)
    command = ["bandit", "-r", "app", "--ignore-nosec", "-f", "json", "-l"]

    result = subprocess.run(command, capture_output=True, text=True)

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        # 如果没有发现漏洞，bandit 可能不会输出有效的 JSON 或输出为空
        # 或者如果有严重错误，我们需要查看 stderr
        if result.returncode == 0:
            print("Security check passed: No issues found.")
            return 0
        else:
            print("Error running bandit:")
            print(result.stderr)
            return 1

    results = data.get("results", [])
    total_issues = len(results)

    medium_issues = [r for r in results if r.get("issue_severity") == "MEDIUM"]
    high_issues = [r for r in results if r.get("issue_severity") == "HIGH"]
    low_issues = [r for r in results if r.get("issue_severity") == "LOW"]

    print("Bandit Scan Results:")
    print(f"  Total issues found: {total_issues}")
    print(f"  - High: {len(high_issues)}")
    print(f"  - Medium: {len(medium_issues)}")
    print(f"  - Low: {len(low_issues)}")

    # 逻辑 1: 拦截中风险或高风险错误
    if len(high_issues) > 0 or len(medium_issues) > 0:
        print("\nError: Intercepted commit due to MEDIUM or HIGH risk security issues.")
        return 1

        # 逻辑 2: 低风险漏洞上限调整为 20

        if total_issues > 20:
            print(
                f"\nError: Security check failed: Found {total_issues} issues, which exceeds the limit of 20."
            )

            return 1

    print("\nSecurity check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(run_security_check())
