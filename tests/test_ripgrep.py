import gzip
import os
import re
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

from deepwick_spec.ansi import style_of
from deepwick_spec.check_port import check_port
from deepwick_spec.palette import load_palette

REPO = Path(__file__).resolve().parents[1]
PALETTE = load_palette()
C = PALETTE.colors
CONFIG = REPO / "deepwick.ripgreprc"


def tiny_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
    header = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"\x00\x00")) + chunk(b"IEND", b"")


def make_tree(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("def main():\n    return 0\n")
    (root / "run.sh").write_text("#!/bin/sh\necho run\n")
    (root / "run.sh").chmod(0o755)
    (root / "app.py").write_text("print('hi')\n")
    (root / "link").symlink_to("app.py")
    (root / "broken").symlink_to("missing")
    os.mkfifo(root / "pipe")
    (root / "bundle.tar.gz").write_bytes(gzip.compress(b"deepwick"))
    (root / "photo.png").write_bytes(tiny_png())
    (root / "notes.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    (root / "old.bak").write_text("old\n")
    return root


def rgb(name):
    return ",".join(str(int(C[name][i : i + 2], 16)) for i in (1, 3, 5))


EXPECTED = [
    "--colors=path:none", f"--colors=path:fg:{rgb('blue')}",
    "--colors=line:none", f"--colors=line:fg:{rgb('muted')}",
    "--colors=column:none", f"--colors=column:fg:{rgb('muted')}",
    "--colors=match:none", f"--colors=match:fg:{rgb('gold')}", f"--colors=match:bg:{rgb('selection')}",
    "--colors=match:style:bold",
]


def arguments():
    assert CONFIG.is_file(), "deepwick.ripgreprc missing"
    lines = [line.strip() for line in CONFIG.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def test_config_arguments():
    assert arguments() == EXPECTED


def test_env_snippets_point_at_config():
    assert re.search(r'^export RIPGREP_CONFIG_PATH=".*deepwick\.ripgreprc"$', (REPO / "deepwick.sh").read_text(), re.M)
    assert re.search(r'^set -gx RIPGREP_CONFIG_PATH ".*deepwick\.ripgreprc"$', (REPO / "deepwick.fish").read_text(), re.M)


@pytest.mark.skipif(shutil.which("rg") is None, reason="requires rg")
def test_rg_renders_roles(tmp_path):
    tree = make_tree(tmp_path / "tree")
    (tree / "app.py").write_text("print('deepwick')\n")
    env = {"PATH": "/usr/bin:/bin:" + str(Path(shutil.which("rg")).parent), "RIPGREP_CONFIG_PATH": str(CONFIG)}
    out = subprocess.run(
        ["rg", "--color=always", "--heading", "--with-filename", "--line-number", "--column", "deepwick", "app.py"],
        cwd=tree, env=env, capture_output=True, text=True, check=True,
    ).stdout
    assert style_of(out, "app.py")["fg"] == C["blue"].lower()
    assert not style_of(out, "app.py")["bold"]
    match = style_of(out, "deepwick")
    assert (match["fg"], match["bg"], match["bold"]) == (C["gold"].lower(), C["selection"].lower(), True)
    assert style_of(out, "1")["fg"] == C["muted"].lower()
    assert style_of(out, "8")["fg"] == C["muted"].lower(), "column"


def test_port_conventions():
    assert check_port(REPO, PALETTE.allowed_hex()) == []
