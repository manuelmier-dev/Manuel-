"""Mira la ESTRUCTURA del acceso a TradeStation sin mostrar ninguna clave.

Uso:  python -m bot.ts_probe <ts_tokens.json> [<script_del_token.py>]
Imprime: antigüedad del archivo, nombre/tipo/largo de cada campo (el valor solo si NO es secreto: números, banderas y textos cortos
de campos que no se llamen token/secret/key/password/code) y, del script, solo líneas def/import/from y las direcciones web sin parámetros.
"""
import json
import re
import sys
import time
from pathlib import Path

SECRET_WORDS = ("token", "secret", "key", "password", "code", "pass", "auth")
URL = re.compile(r"https?://[^\s'\"?]+")


def describe_json(path) -> list[str]:
    p = Path(path)
    age_h = (time.time() - p.stat().st_mtime) / 3600
    lines = [f"Archivo: {p.name} | modificado hace {age_h:.1f} horas"]
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return lines + [f"No es un objeto JSON sino {type(data).__name__}"]
    for k, v in data.items():
        secret = any(w in k.lower() for w in SECRET_WORDS)
        show = isinstance(v, (int, float, bool)) or (isinstance(v, str) and len(v) <= 40 and not secret)
        shown = f" = {v!r}" if show and not secret else ""
        lines.append(f"  {k}: {type(v).__name__}, largo {len(str(v))}{shown}")
    return lines


def describe_script(path) -> list[str]:
    out = [f"Script: {Path(path).name}"]
    for n, ln in enumerate(Path(path).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        s = ln.strip()
        if s.startswith(("def ", "import ", "from ", "class ")):
            out.append(f"  {n}: {s[:120]}")
        for u in URL.findall(ln):
            out.append(f"  {n}: URL {u[:120]}")
    return out


if __name__ == "__main__":
    print("\n".join(describe_json(sys.argv[1])))
    if len(sys.argv) > 2:
        print("\n".join(describe_script(sys.argv[2])))
