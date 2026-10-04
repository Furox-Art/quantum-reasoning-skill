"""Debug why a false claim sentence is not rejected."""
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("g", ROOT / "bin" / "check_release_integrity.py")
g = importlib.util.module_from_spec(spec)
sys.modules["g"] = g
spec.loader.exec_module(g)

FAKE = "Release `1.1.1` is attested."
real = (ROOT / "README.md").read_text(encoding="utf-8")
anchor = [
    line for line in real.splitlines() if "was published through the long-lived-token path" in line
][0]
patched = real.replace(anchor, FAKE, 1)
print("patch applied:", patched != real)

for chunk in g.sentences(patched):
    if g.ATTESTATION_MENTION.search(chunk):
        v = g.version_mentions(chunk) & g.KNOWN_UNATTESTED_NPM
        if v:
            print("SENT:", repr(chunk[:140]))
            print("  unattr:", v)
            print("  is_prose:", g.is_prose(chunk))
            print("  claim:", bool(g.TIGHT_CLAIM.search(chunk)))
            print("  denial:", bool(g.TIGHT_DENIAL.search(chunk)))

with tempfile.TemporaryDirectory() as tmp:
    tree = Path(tmp) / "t"
    shutil.copytree(ROOT, tree, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    (tree / "README.md").write_text(patched, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(tree / "bin" / "check_release_integrity.py"), "--attested-npm", "1.1.0"],
        capture_output=True, text=True, cwd=tree, check=False,
    )
    print("rc:", proc.returncode)
    print((proc.stdout + proc.stderr)[-500:])
