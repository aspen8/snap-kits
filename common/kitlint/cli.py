"""kitlint: check a kit 3MF before it costs a print.

    python common/tools/kitlint.py halifax/kit/halifax_kit.3mf            # all checks
    python common/tools/kitlint.py KIT.3mf --only plate,solid
    python common/tools/kitlint.py KIT.3mf --write-sig                    # accept the current state

Rules and accepted exceptions come from <kit>/lint.toml (the folder above kit/), the signature from
KIT.sig.json beside the 3MF. Exit code 1 on any FAIL (or WARN with --strict).
See common/briefs/kit-lint-design.md.
"""
import argparse
import json
import os
import sys
import time
import tomllib

from . import checks, sig
from .checks import FAIL, INFO, WARN
from .load import load

ORDER = {FAIL: 0, WARN: 1, INFO: 2}


def rules_path(kit_path):
    d = os.path.dirname(os.path.abspath(kit_path))
    return os.path.join(os.path.dirname(d) if os.path.basename(d) == "kit" else d, "lint.toml")


def read_rules(path):
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return tomllib.load(f)
    return {}


def _match(a, f):
    if a.get("check") != f.check:
        return False
    part = a.get("part", "")
    if part and not (f.part == part or f.part.startswith(part)):
        return False
    if a.get("match") and a["match"] not in f.msg:
        return False
    if "limit" in a and (f.value is None or f.value > a["limit"]):
        return False
    return True


def apply_accepts(findings, rules):
    accepts = rules.get("accept", [])
    used = [False] * len(accepts)
    for f in findings:
        if f.level == INFO:
            continue
        for i, a in enumerate(accepts):
            if _match(a, f):
                used[i] = True
                f.accepted = a.get("reason", "accepted")
                f.level = INFO
                break
    return [a for a, u in zip(accepts, used) if not u and a.get("check") in checks.CHECKS]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kitlint", description=__doc__.splitlines()[0])
    ap.add_argument("kit")
    ap.add_argument("--only", help="comma-separated checks: diff," + ",".join(checks.CHECKS))
    ap.add_argument("--rules", help="lint.toml (default: <kit>/lint.toml)")
    ap.add_argument("--sig", help="signature (default: KIT.sig.json beside the 3MF)")
    ap.add_argument("--write-sig", action="store_true", help="write the signature from this 3MF")
    ap.add_argument("--strict", action="store_true", help="exit 1 on WARN too")
    ap.add_argument("--report", help="also write the findings as JSON here")
    ap.add_argument("-q", "--quiet", action="store_true", help="hide info lines")
    a = ap.parse_args(argv)

    t0 = time.time()
    kit = load(a.kit)
    rpath = a.rules or rules_path(a.kit)
    rules = read_rules(rpath)
    spath = a.sig or sig.sig_path(a.kit)
    want = a.only.split(",") if a.only else ["diff", *checks.CHECKS]

    findings, skipped = [], []
    for name in want:
        if name == "diff":
            if a.write_sig:
                continue
            if os.path.exists(spath):
                with open(spath) as f:
                    findings += sig.diff(kit, json.load(f))
            else:
                skipped.append("diff (no signature: run with --write-sig)")
        elif name in checks.CHECKS:
            findings += checks.CHECKS[name](kit, rules)
        else:
            ap.error(f"unknown check {name!r}")
    stale = apply_accepts(findings, rules)
    findings.sort(key=lambda f: (ORDER[f.level], f.check, f.part))

    s_date = "none"
    if os.path.exists(spath):
        with open(spath) as f:
            s_date = json.load(f).get("written", "?")
    print(f"kitlint {os.path.basename(a.kit)}   {len(kit.objects)} objects, {len(kit.plates)} plates   "
          f"rules: {'yes' if rules else 'none'}   signature: {s_date}   sidecar: no")
    w = max([len(f.part) for f in findings] + [10])
    for f in findings:
        if a.quiet and f.level == INFO:
            continue
        tail = f"   accepted: {f.accepted}" if f.accepted else ""
        print(f"{f.level:4s} {f.check:6s} {f.part:{w}s}  {f.msg}{tail}")
    for s in stale:
        print(f"stale accept   {s.get('part', '*')} / {s['check']} / {s.get('match', '')}   (no longer reported)")
    n = {lv: sum(f.level == lv for f in findings) for lv in ORDER}
    acc = sum(1 for f in findings if f.accepted)
    print(f"{n[FAIL]} FAIL, {n[WARN]} WARN, {acc} accepted, {len(stale)} stale.   "
          f"Skipped: {'; '.join(skipped + ['overhang, clash, paint, slice, fits (not built yet)']) }.   "
          f"{time.time() - t0:.0f} s")
    if a.write_sig:
        print("signature written:", sig.write(kit, spath))
    if a.report:
        with open(a.report, "w") as f:
            json.dump([f.__dict__ for f in findings], f, indent=1)
    return 1 if n[FAIL] or (a.strict and n[WARN]) else 0


if __name__ == "__main__":
    sys.exit(main())
