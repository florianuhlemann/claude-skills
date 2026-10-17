"""Minimal S-expression reader/writer for KiCad files."""
import re

class Sym(str):
    """Unquoted atom."""

_tok = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)

def parse(text):
    stack, cur, pos = [], [], 0
    while True:
        m = _tok.match(text, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        lp, rp, s, a = m.groups()
        if lp:
            stack.append(cur); cur = []
        elif rp:
            done = cur; cur = stack.pop(); cur.append(done)
        elif s is not None:
            cur.append(s.replace('\\"', '"').replace('\\\\', '\\'))
        elif a is not None:
            cur.append(Sym(a))
    return cur[0] if len(cur) == 1 else cur

def dump(e, indent=0):
    if isinstance(e, list):
        if not e:
            return "()"
        simple = all(not isinstance(x, list) for x in e)
        if simple and len(e) < 12:
            return "(" + " ".join(dump(x) for x in e) + ")"
        out = "(" + dump(e[0])
        for x in e[1:]:
            if isinstance(x, list):
                out += "\n" + "\t" * (indent + 1) + dump(x, indent + 1)
            else:
                out += " " + dump(x)
        return out + "\n" + "\t" * indent + ")"
    if isinstance(e, Sym):
        return str(e)
    if isinstance(e, (int, float)):
        return fmt(e)
    return '"' + str(e).replace('\\', '\\\\').replace('"', '\\"') + '"'

def fmt(v):
    if isinstance(v, float):
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    return str(v)

def find(e, key):
    return [x for x in e if isinstance(x, list) and x and x[0] == key]

def first(e, key):
    r = find(e, key)
    return r[0] if r else None
