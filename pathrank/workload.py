"""Build a real command-invocation distribution from on-disk shell history.

Nothing here invents numbers.  Every weight comes from a command this machine
actually ran, read from PSReadLine history, bash history, or recorded agent
tool calls.  Names that do not resolve on the current PATH are discarded.
"""

from __future__ import annotations

import collections
import glob
import json
import os

_SPLIT = str.maketrans({"|": " ", ";": " ", "&": " ", "(": " ", ")": " ", "\n": " "})
_STRIP = "\"'`,"


def _tokens(line: str):
    for tok in line.translate(_SPLIT).split():
        tok = tok.strip(_STRIP).lower()
        if not tok or "=" in tok or tok.startswith("-"):
            continue
        yield os.path.splitext(os.path.basename(tok))[0]


def _psreadline_path():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return os.path.join(
        appdata, "Microsoft", "Windows", "PowerShell", "PSReadLine", "ConsoleHost_history.txt"
    )


def from_history_file(path, counter, known):
    if not path or not os.path.exists(path):
        return 0
    seen = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            for name in _tokens(line):
                if name in known:
                    counter[name] += 1
                    seen += 1
    return seen


def from_agent_transcripts(root, counter, known, limit=None):
    """Read Bash and PowerShell tool calls out of recorded agent transcripts."""
    if not root or not os.path.isdir(root):
        return 0
    seen = 0
    files = sorted(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True))
    for fname in files[:limit]:
        try:
            fh = open(fname, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"Bash"' not in line and '"PowerShell"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                message = rec.get("message") or {}
                blocks = message.get("content")
                if not isinstance(blocks, list):
                    continue
                for block in blocks:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    if block.get("name") not in ("Bash", "PowerShell"):
                        continue
                    command = (block.get("input") or {}).get("command", "")
                    for name in _tokens(command):
                        if name in known:
                            counter[name] += 1
                            seen += 1
    return seen


def collect(inv, extra_history=(), transcript_root=None, transcript_limit=None):
    """Return (weights, provenance) for the commands this machine really runs."""
    known = set(inv.commands)
    counter = collections.Counter()
    provenance = {}

    n = from_history_file(_psreadline_path(), counter, known)
    if n:
        provenance["powershell_history"] = n
    n = from_history_file(os.path.expanduser("~/.bash_history"), counter, known)
    if n:
        provenance["bash_history"] = n
    for path in extra_history:
        n = from_history_file(path, counter, known)
        if n:
            provenance[os.path.basename(path)] = n

    if transcript_root is None:
        transcript_root = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    n = from_agent_transcripts(transcript_root, counter, known, transcript_limit)
    if n:
        provenance["agent_transcripts"] = n

    return dict(counter), provenance


def uniform(inv):
    """Fallback distribution: every resolvable command equally likely."""
    return {stem: 1.0 for stem in inv.commands}
