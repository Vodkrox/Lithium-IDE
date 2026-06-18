"""
Run all Lithium IDE tests sequentially and report results.

Usage:
    python run_all.py
"""

import os
import subprocess
import sys


def print_header(text):
    print()
    print("=" * 65)
    print(f"  {text}")
    print("=" * 65)


def main():
    # Project root is the parent of tests/
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    os.chdir(project_root)

    test_files = [
        "tests/test_ai_level.py",
        "tests/test_ai_engine.py",
        "tests/test_ai_skills.py",
        "tests/test_ai_skill_settings.py",
        "tests/test_conversation_manager.py",
        "tests/test_settings.py",
        "tests/test_theme.py",
        "tests/test_syntax_rules.py",
        "tests/test_runner.py",
        "tests/test_utils.py",
        "tests/test_base.py",
    ]

    total_passed = 0
    total_failed = 0
    total_skipped = 0
    all_results = []

    print("=" * 65)
    print("  Lithium IDE - All Tests")
    print("=" * 65)

    for test_file in test_files:
        print_header(f"Running: {test_file}")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Print output
        print(result.stdout)
        if result.stderr:
            print(result.stderr)

        # Parse summary line (e.g. "8 passed, 1 skipped" or "45 passed, 2 failed")
        passed = failed = skipped = 0
        for line in result.stdout.splitlines():
            line = line.strip()
            if "passed" not in line or not any(c.isdigit() for c in line):
                continue
            # Remove leading/trailing === characters used as separators
            clean = line.strip("=")
            parts = clean.replace(",", "").split()
            for i, p in enumerate(parts):
                p_clean = p.strip(",.")
                if p_clean == "passed":
                    passed = int(parts[i - 1])
                elif p_clean == "failed":
                    failed = int(parts[i - 1])
                elif p_clean == "skipped":
                    skipped = int(parts[i - 1])
            break

        total_passed += passed
        total_failed += failed
        total_skipped += skipped
        all_results.append((test_file, passed, failed, skipped, result.returncode == 0))

        if result.returncode != 0:
            print(f"  >>> FAILURES in {test_file} <<<")

    # Summary
    print()
    print("=" * 65)
    print("  FINAL SUMMARY")
    print("=" * 65)
    for test_file, passed, failed, skipped, ok in all_results:
        status = "[OK]" if ok else "[FAIL]"
        print(
            f"  {status} {test_file:45s}  {passed:3d} passed, {failed:3d} failed, {skipped:3d} skipped"
        )
    print()
    print(
        f"  TOTAL:  {total_passed:3d} passed, {total_failed:3d} failed, {total_skipped:3d} skipped"
    )
    print()

    if total_failed > 0:
        print("  [FAIL] Some tests FAILED. Review the output above.")
        sys.exit(1)
    else:
        print("  [OK] All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
