import subprocess
import sys


def main() -> None:
    branch = sys.argv[1] if len(sys.argv) > 1 else "small-fixes"
    cmd = ["git", "push", "-u", "origin", branch]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout)
    if res.stderr:
        print(res.stderr, file=sys.stderr)
    sys.exit(res.returncode)


if __name__ == "__main__":
    main()
