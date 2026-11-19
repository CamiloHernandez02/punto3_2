#!/usr/bin/env python3
"""
automatas.py -- Definición formal de los autómatas del Punto 3.2
---------------------------------------------------------------------------
Este módulo es la ÚNICA fuente de verdad de los autómatas finitos
deterministas (AFD) del informe. A partir de aquí se generan:
    * las tablas de transición  (tabla_markdown)
    * las trazas con la función extendida δ*  (traza)
    * los diagramas Graphviz  (a_dot)
    * la verificación contra el analizador Flex real (tests/verificar.py)

Cada AFD es una 5-tupla  M = (Q, Σ, δ, q0, F)  donde Σ se expresa como una
partición en CLASES de símbolos (p. ej. L = [A-Za-z_]). Las transiciones no
definidas llevan implícitamente a un estado trampa (⊥) no representado.
"""

# ---------------------------------------------------------------------------
# Clases de símbolos del analizador léxico (cada AFD usa un subconjunto
# DISJUNTO de ellas).  clase -> (descripción, predicado sobre un carácter)
# ---------------------------------------------------------------------------
def _es_letra(c):  return c.isascii() and (c.isalpha() or c == "_")
def _es_digito(c): return c in "0123456789"

CLASES = {
    "L": ("[A-Za-z_]  letra o guion bajo",           _es_letra),
    "D": ("[0-9]  dígito",                           _es_digito),
    "M": ("'-'  signo menos",                        lambda c: c == "-"),
    "Q": ("'  comilla simple (apóstrofo)",            lambda c: c == "'"),
    "C": ("[^'\\n]  cualquier símbolo salvo ' y salto de línea",
                                                      lambda c: c not in "'\n"),
    "N": ("[^\\n-]  cualquier símbolo salvo salto de línea y '-'",
                                                      lambda c: c not in "\n-"),
}

# ---------------------------------------------------------------------------
# AFD léxicos
# ---------------------------------------------------------------------------
AFD_LEXICOS = {
    "IDENT": {
        "titulo": "AFD de identificadores  (IDENT = L (L | D)*)",
        "regex": "[A-Za-z_][A-Za-z0-9_]*",
        "estados": ["q0", "q1"],
        "inicial": "q0",
        "finales": ["q1"],
        "clases": ["L", "D"],
        "delta": {("q0", "L"): "q1", ("q1", "L"): "q1", ("q1", "D"): "q1"},
    },
    "ENTERO": {
        "titulo": "AFD de enteros  (ENTERO = (ε | -) D D*)",
        "regex": "-?[0-9]+",
        "estados": ["q0", "q1", "q2"],
        "inicial": "q0",
        "finales": ["q2"],
        "clases": ["M", "D"],
        "delta": {("q0", "M"): "q1", ("q0", "D"): "q2",
                  ("q1", "D"): "q2", ("q2", "D"): "q2"},
    },
    "CADENA": {
        "titulo": "AFD de literales de cadena  (CADENA = ' (C | '')* ')",
        "regex": "'([^'\\n]|'')*'",
        "estados": ["q0", "q1", "q2"],
        "inicial": "q0",
        "finales": ["q2"],
        "clases": ["Q", "C"],
        "delta": {("q0", "Q"): "q1", ("q1", "C"): "q1",
                  ("q1", "Q"): "q2", ("q2", "Q"): "q1"},
    },
    "COMENTARIO": {
        "titulo": "AFD de comentarios de línea  (COMENTARIO = -- (M | N)*)",
        "regex": "--[^\\n]*",
        "estados": ["q0", "q1", "q2"],
        "inicial": "q0",
        "finales": ["q2"],
        "clases": ["M", "N"],
        "delta": {("q0", "M"): "q1", ("q1", "M"): "q2",
                  ("q2", "M"): "q2", ("q2", "N"): "q2"},
    },
}

# Palabras reservadas (no distinguen mayúsculas) y su token.
PALABRAS_RESERVADAS = {
    "insertar": "INSERTAR", "en": "EN", "tabla": "TABLA",
    "valores": "VALORES", "fin": "FIN",
    "verdadero": "BOOLEANO", "falso": "BOOLEANO",
    "true": "BOOLEANO", "false": "BOOLEANO",
}

# ---------------------------------------------------------------------------
# AFD a nivel de TOKENS (estructura de una sentencia)
# El alfabeto son los tokens; VALOR agrupa ENTERO | CADENA | BOOLEANO.
# Se acepta en q0: el lenguaje es  (sentencia)*  (programa vacío incluido).
# ---------------------------------------------------------------------------
AFD_SINTACTICO = {
    "titulo": "AFD sintáctico a nivel de tokens: estructura de un programa",
    "estados": ["q0", "q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9", "q10"],
    "inicial": "q0",
    "finales": ["q0"],
    "alfabeto": ["INSERTAR", "EN", "TABLA", "IDENT", "VALORES", "':'",
                 "'='", "VALOR", "','", "FIN", "';'"],
    "delta": {
        ("q0", "INSERTAR"): "q1",
        ("q1", "EN"):       "q2",
        ("q2", "TABLA"):    "q3",
        ("q3", "IDENT"):    "q4",
        ("q4", "VALORES"):  "q5",
        ("q5", "':'"):      "q6",
        ("q6", "IDENT"):    "q7",
        ("q7", "'='"):      "q8",
        ("q8", "VALOR"):    "q9",
        ("q9", "','"):      "q6",
        ("q9", "FIN"):      "q10",
        ("q10", "';'"):     "q0",
    },
    "significado": {
        "q0": "inicio de sentencia (estado de aceptación)",
        "q1": "leído 'insertar'",
        "q2": "leído 'en'",
        "q3": "leído 'tabla'",
        "q4": "leído el nombre de la tabla",
        "q5": "leído 'valores'",
        "q6": "leído ':' o ',' (se espera un campo)",
        "q7": "leído el nombre de un campo",
        "q8": "leído '='",
        "q9": "leído un valor (se espera ',' o 'fin')",
        "q10": "leído 'fin'",
    },
}

# Tokens -> símbolo del AFD sintáctico
def simbolo_sintactico(token):
    return "VALOR" if token in ("ENTERO", "CADENA", "BOOLEANO") else token


# ---------------------------------------------------------------------------
# Simulación
# ---------------------------------------------------------------------------
def clase_de(afd, c):
    """Clase del símbolo c dentro de las clases del AFD, o None."""
    for nombre in afd["clases"]:
        if CLASES[nombre][1](c):
            return nombre
    return None


def aceptar_lexico(afd, cadena):
    """¿El AFD léxico acepta la cadena completa?"""
    q = afd["inicial"]
    for c in cadena:
        k = clase_de(afd, c)
        q = afd["delta"].get((q, k)) if k else None
        if q is None:
            return False
    return q in afd["finales"]


def traza_lexica(afd, cadena):
    """Lista de pasos de δ*.  Cada paso: (i, prefijo, símbolo, clase, estado).
    Si se llega al estado trampa, el último estado es '⊥'."""
    filas = [(0, "ε", "—", "—", afd["inicial"])]
    q = afd["inicial"]
    for i, c in enumerate(cadena, 1):
        k = clase_de(afd, c)
        q = afd["delta"].get((q, k)) if k else None
        filas.append((i, cadena[:i], c, k or "—", q if q else "⊥"))
        if q is None:
            break
    return filas


def aceptar_tokens(tokens):
    """AFD sintáctico sobre una lista de símbolos del alfabeto de tokens."""
    q = AFD_SINTACTICO["inicial"]
    for t in tokens:
        q = AFD_SINTACTICO["delta"].get((q, t))
        if q is None:
            return False
    return q in AFD_SINTACTICO["finales"]


def traza_sintactica(tokens):
    filas = [(0, "ε", "—", AFD_SINTACTICO["inicial"])]
    q = AFD_SINTACTICO["inicial"]
    for i, t in enumerate(tokens, 1):
        q = AFD_SINTACTICO["delta"].get((q, t))
        filas.append((i, t, "", q if q else "⊥"))
        if q is None:
            break
    return filas


# ---------------------------------------------------------------------------
# Tablas en Markdown
# ---------------------------------------------------------------------------
def tabla_markdown_lexica(afd):
    cab = "| δ | " + " | ".join(afd["clases"]) + " |"
    sep = "|---|" + "|".join(["---"] * len(afd["clases"])) + "|"
    filas = [cab, sep]
    for q in afd["estados"]:
        marca = ""
        if q == afd["inicial"]:
            marca += "→"
        if q in afd["finales"]:
            marca += "\\*"
        celdas = [afd["delta"].get((q, k), "⊥") for k in afd["clases"]]
        filas.append(f"| {marca}{q} | " + " | ".join(celdas) + " |")
    return "\n".join(filas)


def tabla_markdown_sintactica():
    a = AFD_SINTACTICO
    cab = "| δ | " + " | ".join(a["alfabeto"]) + " |"
    sep = "|---|" + "|".join(["---"] * len(a["alfabeto"])) + "|"
    filas = [cab, sep]
    for q in a["estados"]:
        marca = ("→" if q == a["inicial"] else "") + ("\\*" if q in a["finales"] else "")
        celdas = [a["delta"].get((q, s), "⊥") for s in a["alfabeto"]]
        filas.append(f"| {marca}{q} | " + " | ".join(celdas) + " |")
    return "\n".join(filas)


# ---------------------------------------------------------------------------
# Graphviz
# ---------------------------------------------------------------------------
_ESTILO = ('rankdir=LR; bgcolor="white"; pad=0.3; nodesep=0.5; ranksep=0.7;\n'
           'node [shape=circle, fontname="Helvetica", fontsize=13, width=0.55, fixedsize=false];\n'
           'edge [fontname="Helvetica", fontsize=12];\n')


def _esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _leyenda(lineas):
    """Une líneas con el salto alineado a la izquierda de Graphviz (\\l),
    escapando cada línea por separado."""
    return "".join(_esc(l) + "\\l" for l in lineas)


def dot_lexico(afd):
    lineas = [f"{k} = {CLASES[k][0]}" for k in afd["clases"]]
    lineas.append("Las transiciones no mostradas conducen al estado trampa ⊥.")
    out = ['digraph AFD {', _ESTILO,
           f'labelloc=b; fontname="Helvetica"; fontsize=12; label="{_leyenda(lineas)}";',
           '__ini [shape=point, width=0.08, label=""];']
    for q in afd["estados"]:
        forma = "doublecircle" if q in afd["finales"] else "circle"
        out.append(f'{q} [shape={forma}];')
    out.append(f'__ini -> {afd["inicial"]};')
    agrupadas = {}
    for (q, k), r in afd["delta"].items():
        agrupadas.setdefault((q, r), []).append(k)
    for (q, r), ks in agrupadas.items():
        out.append(f'{q} -> {r} [label="{_esc(", ".join(ks))}"];')
    out.append("}")
    return "\n".join(out)


def dot_sintactico():
    a = AFD_SINTACTICO
    lineas = ["VALOR = ENTERO | CADENA | BOOLEANO",
              "IDENT, ENTERO, CADENA y BOOLEANO son tokens del analizador léxico.",
              "Las transiciones no mostradas conducen al estado trampa ⊥."]
    out = ['digraph SINT {', _ESTILO,
           f'labelloc=b; fontname="Helvetica"; fontsize=12; label="{_leyenda(lineas)}";',
           '__ini [shape=point, width=0.08, label=""];']
    for q in a["estados"]:
        forma = "doublecircle" if q in a["finales"] else "circle"
        out.append(f'{q} [shape={forma}];')
    out.append(f'__ini -> {a["inicial"]};')
    for (q, s), r in a["delta"].items():
        out.append(f'{q} -> {r} [label="{_esc(s)}"];')
    out.append("}")
    return "\n".join(out)


def dot_trie():
    """Trie de las palabras reservadas, con sus categorías de token."""
    nodos, aristas, finales = {"": "q0"}, [], {}
    for palabra, token in PALABRAS_RESERVADAS.items():
        pref = ""
        for ch in palabra:
            nuevo = pref + ch
            if nuevo not in nodos:
                nodos[nuevo] = f"t{len(nodos)}"
                aristas.append((nodos[pref], nodos[nuevo], ch))
            pref = nuevo
        finales[pref] = token
    lineas = ["Cada ruta que termina en un estado doble verde es una palabra reservada.",
              "No se distinguen mayúsculas de minúsculas (opción caseless de Flex).",
              "Desde CUALQUIER estado del árbol, un símbolo de [A-Za-z0-9_] que no continúe",
              "una palabra reservada conduce a q_ID (identificador). Desde un estado final,",
              "cualquier L o D adicional también (p. ej. 'final' o 'fin2' son identificadores).",
              "L = [A-Za-z_]   D = [0-9]"]
    out = ['digraph TRIE {', _ESTILO,
           f'labelloc=b; fontname="Helvetica"; fontsize=12; label="{_leyenda(lineas)}";',
           '__ini [shape=point, width=0.08, label=""];',
           'q0 [label="q0"];',
           'qid [shape=doublecircle, label="q_ID\\nIDENT", style=filled, fillcolor="#e8e8e8"];',
           'qid -> qid [label="L, D"];']
    for pref, nid in nodos.items():
        if pref == "":
            continue
        if pref in finales:
            out.append(f'{nid} [shape=doublecircle, style=filled, fillcolor="#cfe8cf", '
                       f'label="{pref}\\n{finales[pref]}"];')
        else:
            out.append(f'{nid} [label="", width=0.25, height=0.25];')
    out.append("__ini -> q0;")
    for a, b, ch in aristas:
        out.append(f'{a} -> {b} [label="{ch}"];')
    out.append("}")
    return "\n".join(out)


if __name__ == "__main__":
    # Autoprueba mínima.
    assert aceptar_lexico(AFD_LEXICOS["IDENT"], "clientes")
    assert not aceptar_lexico(AFD_LEXICOS["IDENT"], "2campo")
    assert aceptar_lexico(AFD_LEXICOS["ENTERO"], "-42")
    assert not aceptar_lexico(AFD_LEXICOS["ENTERO"], "-")
    assert aceptar_lexico(AFD_LEXICOS["CADENA"], "'O''Brien'")
    assert not aceptar_lexico(AFD_LEXICOS["CADENA"], "'abc")
    assert aceptar_lexico(AFD_LEXICOS["COMENTARIO"], "-- hola")
    print("automatas.py: autoprueba OK")
