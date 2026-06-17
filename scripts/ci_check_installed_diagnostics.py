from ci_check_diagnostics import run_diagnostics


def main():
    return run_diagnostics(["magic-debug", "--check", "--json"])


if __name__ == "__main__":
    raise SystemExit(main())
