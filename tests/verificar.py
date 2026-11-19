#!/usr/bin/env python3
"""
verificar.py -- Verificación automática del Punto 3.2
---------------------------------------------------------------------------
Ejecutar desde la raíz del proyecto (tras `make`):   python3 tests/verificar.py

Grupos de pruebas:
  1. Integración: ejecuta tests/entrada_prueba.txt y comprueba contadores,
     mensajes de error y contenido real de la base de datos.
  2. Léxico: casos puntuales (palabra reservada vs identificador, etc.).
  3. AFD léxicos vs Flex: los autómatas formales de herramientas/automatas.py
     deben aceptar exactamente las mismas cadenas que el escáner generado.
  4. AFD sintáctico vs Bison: el autómata a nivel de tokens debe aceptar
     exactamente los mismos programas que el parser generado.
"""
import itertools
import os
import random
import re
import sqlite3
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import automatas as A                                           # noqa: E402

BIN = os.path.join(RAIZ, "build", "sqlparser")
ENTRADA = os.path.join(RAIZ, "tests", "entrada_prueba.txt")

fallos = 0


def comprobar(condicion, descripcion):
    """Imprime PASS/FAIL y cuenta los fallos."""
    global fallos
    if condicion:
        print(f"  [PASS] {descripcion}")
    else:
        print(f"  [FAIL] {descripcion}")
        fallos += 1


def ejecutar(args, entrada=None):
    r = subprocess.run([BIN] + args, input=entrada, capture_output=True,
                       text=True, encoding="utf-8")
    return r.returncode, r.stdout, r.stderr


# ---------------------------------------------------------------------------
# Utilidades para leer la tabla de tokens (modo -t)
# ---------------------------------------------------------------------------
RE_TOKEN = re.compile(r"^\s*(\d+):(\d+)\s+(\S+)\s+(.*)$")


def tokens_por_linea(salida):
    """Devuelve {línea: [(categoría, lexema), ...]} a partir de la salida -t."""
    res = {}
    for linea in salida.splitlines():
        m = RE_TOKEN.match(linea)
        if not m or m.group(3) in ("CATEGORIA",):
            continue
        lexema = m.group(4).split("  ->  ")[0]
        res.setdefault(int(m.group(1)), []).append((m.group(3), lexema))
    return res


def tokens_de(texto):
    _, out, _ = ejecutar(["-t", "-e", texto])
    return [t for ts in tokens_por_linea(out).values() for t in ts]


# ---------------------------------------------------------------------------
# 1. Integración
# ---------------------------------------------------------------------------
def prueba_integracion():
    print("\n1. Integración: tests/entrada_prueba.txt")
    with tempfile.TemporaryDirectory() as tmp:
        bd = os.path.join(tmp, "t.db")
        rc, out, err = ejecutar(["-l", "-q", "-d", bd, ENTRADA])
        todo = out + err

        def num(etiqueta):
            return int(re.search(re.escape(etiqueta) + r" \.+ (\d+)", out).group(1))

        comprobar(rc == 1, "código de salida 1 (hay sentencias rechazadas)")
        comprobar(num("Sentencias insertadas") == 10, "10 sentencias insertadas")
        comprobar(num("Sentencias rechazadas (léxico/sintaxis)") == 13,
                  "13 sentencias rechazadas por léxico/sintaxis")
        comprobar(num("Sentencias rechazadas (semántica/BD)") == 9,
                  "9 sentencias rechazadas por semántica/BD")
        comprobar(num("Diagnósticos léxicos") == 5, "5 diagnósticos léxicos")
        comprobar(num("Diagnósticos sintácticos") == 9, "9 diagnósticos sintácticos")

        mensajes = [
            "carácter no reconocido '@'",
            "las cadenas se delimitan con comilla simple",
            "cadena sin cerrar",
            "entero fuera del rango de 64 bits",
            "se esperaba 'fin' o ','",
            "se esperaba ':'",
            "se esperaba '='",
            "se esperaba fin de archivo o 'insertar'",
            "la tabla 'ventas' no existe",
            "el campo 'apellido' no existe en la tabla 'clientes'",
            "el campo 'stock' es de tipo INTEGER y no admite un valor CADENA",
            "el campo 'activo' es de tipo BOOLEAN y no admite un valor ENTERO",
            "el campo 'nombre' aparece más de una vez",
            "falta el campo obligatorio 'nombre' de la tabla 'clientes'",
            "UNIQUE constraint failed: clientes.id",
            "FOREIGN KEY constraint failed",
            "la tabla 'sqlite_master' es reservada del sistema",
        ]
        for m in mensajes:
            comprobar(m in todo, f"mensaje presente: {m}")

        con = sqlite3.connect(bd)
        cuenta = lambda t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        comprobar(cuenta("clientes") == 4, "BD: 4 filas en clientes")
        comprobar(cuenta("productos") == 4, "BD: 4 filas en productos")
        comprobar(cuenta("pedidos") == 2, "BD: 2 filas en pedidos")
        fila = con.execute("SELECT nombre FROM clientes WHERE id = 4").fetchone()
        comprobar(fila == ("O'Brien; fin",), "BD: cadena con '' y ';' almacenada como O'Brien; fin")
        fila = con.execute("SELECT nombre, activo FROM clientes WHERE id = 3").fetchone()
        comprobar(fila == ("María Gómez", 1), "BD: acentos y booleano TRUE -> 1")
        fila = con.execute("SELECT stock FROM productos WHERE codigo = 5000").fetchone()
        comprobar(fila == (9223372036854775807,), "BD: entero máximo de 64 bits")
        comprobar(con.execute("SELECT COUNT(*) FROM clientes WHERE id IN (20,21,22,26,27)")
                  .fetchone()[0] == 0, "BD: ninguna sentencia sintácticamente inválida se almacenó")
        con.close()

        # Los diagnósticos van por stderr y los resultados por stdout.
        comprobar("Error" not in out.split("RESUMEN")[0],
                  "los errores no se mezclan con la salida estándar")


# ---------------------------------------------------------------------------
# 2. Casos léxicos puntuales
# ---------------------------------------------------------------------------
def prueba_lexica_puntual():
    print("\n2. Léxico: casos puntuales")
    PK, ID, EN_, CA, BO, PU, ER = ("PALABRA_CLAVE", "IDENTIFICADOR", "ENTERO",
                                   "CADENA", "BOOLEANO", "PUNTUACION", "ERROR_LEXICO")
    casos = [
        ("insertar",   [(PK, "insertar")]),
        ("INSERTAR",   [(PK, "INSERTAR")]),
        ("fin",        [(PK, "fin")]),
        ("Fin",        [(PK, "Fin")]),
        ("final",      [(ID, "final")]),
        ("fin2",       [(ID, "fin2")]),
        ("fin_",       [(ID, "fin_")]),
        ("entero",     [(ID, "entero")]),
        ("en",         [(PK, "en")]),
        ("verdadero",  [(BO, "verdadero")]),
        ("TRUE",       [(BO, "TRUE")]),
        ("falso",      [(BO, "falso")]),
        ("truex",      [(ID, "truex")]),
        ("_x1",        [(ID, "_x1")]),
        ("2campo",     [(EN_, "2"), (ID, "campo")]),
        ("-5",         [(EN_, "-5")]),
        ("5-3",        [(EN_, "5"), (EN_, "-3")]),
        ("- 5",        [(ER, "-"), (EN_, "5")]),
        ("'a''b'",     [(CA, "'a''b'")]),
        ("''",         [(CA, "''")]),
        ("'ñandú'",    [(CA, "'ñandú'")]),
        ("'a;fin'",    [(CA, "'a;fin'")]),
        ("-- hola fin", []),
        ("x -- hola",  [(ID, "x")]),
        ("@",          [(ER, "@")]),
        ("ñ",          [(ER, "ñ")]),
        ('"a"',        [(ER, '"'), (ID, "a"), (ER, '"')]),
        ("a:b;c,d=e",  [(ID, "a"), (PU, ":"), (ID, "b"), (PU, ";"), (ID, "c"),
                        (PU, ","), (ID, "d"), (PU, "="), (ID, "e")]),
    ]
    for texto, esperado in casos:
        obtenido = tokens_de(texto)
        comprobar(obtenido == esperado,
                  f"{texto!r:14} -> {[c for c, _ in esperado]}"
                  + ("" if obtenido == esperado else f"   (obtenido: {obtenido})"))


# ---------------------------------------------------------------------------
# 3. AFD léxicos formales vs. Flex
# ---------------------------------------------------------------------------
def candidatos():
    alfabeto = ["a", "Z", "_", "7", "-", "'", " ", '"']
    lista = {""}
    for n in range(1, 4):                                   # exhaustivo hasta 3
        lista.update("".join(p) for p in itertools.product(alfabeto, repeat=n))
    rnd = random.Random(2024)                               # muestra hasta 8
    for _ in range(4000):
        n = rnd.randint(4, 8)
        lista.add("".join(rnd.choice(alfabeto) for _ in range(n)))
    lista.update(["fin", "FIN", "Fin", "final", "fina", "fi", "en", "EN", "entero",
                  "tabla", "tablas", "valores", "valor", "insertar", "insertarx",
                  "verdadero", "falso", "true", "false", "TRUE", "truex", "e", "f",
                  "_fin", "fin_", "'a'''", "'a''b'", "'''", "--", "---", "--a-b",
                  "-0", "-00", "007", "-", "--'", "'--'", "x'", "'x"])
    return sorted(c for c in lista if c.strip(" ") != "")


def prueba_afd_vs_flex():
    print("\n3. AFD léxicos formales vs. escáner Flex")
    cand = candidatos()
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write("\n".join(cand) + "\n")
        ruta = f.name
    try:
        _, out, _ = ejecutar(["-t", ruta])
    finally:
        os.unlink(ruta)
    por_linea = tokens_por_linea(out)

    L = A.AFD_LEXICOS
    reservadas = A.PALABRAS_RESERVADAS
    malos = {"IDENT": [], "ENTERO": [], "CADENA": [], "COMENTARIO": []}

    for i, s in enumerate(cand, 1):
        toks = por_linea.get(i, [])

        # --- IDENT (el AFD acepta también las reservadas; el trie las separa)
        acepta = A.aceptar_lexico(L["IDENT"], s)
        if acepta and s.lower() in reservadas:
            ok = (len(toks) == 1 and toks[0][1] == s
                  and toks[0][0] in ("PALABRA_CLAVE", "BOOLEANO"))
        elif acepta:
            ok = toks == [("IDENTIFICADOR", s)]
        else:
            ok = toks != [("IDENTIFICADOR", s)]
        if not ok: malos["IDENT"].append((s, toks))

        # --- ENTERO
        acepta = A.aceptar_lexico(L["ENTERO"], s)
        ok = (toks == [("ENTERO", s)]) == acepta
        if not ok: malos["ENTERO"].append((s, toks))

        # --- CADENA
        acepta = A.aceptar_lexico(L["CADENA"], s)
        ok = (toks == [("CADENA", s)]) == acepta
        if not ok: malos["CADENA"].append((s, toks))

        # --- COMENTARIO: si el AFD acepta la cadena completa, el escáner no
        #     produce tokens. Si no la acepta, solo puede no producir tokens
        #     cuando la cadena es "espacios + (nada | comentario)", porque los
        #     espacios iniciales los consume otra regla (espacios en blanco).
        acepta = A.aceptar_lexico(L["COMENTARIO"], s)
        resto = s.lstrip(" ")
        if acepta:
            ok = toks == []
        else:
            ok = toks != [] or resto == "" or resto.startswith("--")
        if not ok: malos["COMENTARIO"].append((s, toks))

    print(f"  ({len(cand)} cadenas candidatas analizadas por Flex en una sola ejecución)")
    for nombre, lista in malos.items():
        comprobar(not lista,
                  f"AFD {nombre} coincide con Flex"
                  + ("" if not lista else f"  (discrepancias: {lista[:3]})"))


# ---------------------------------------------------------------------------
# 4. AFD sintáctico vs. Bison
# ---------------------------------------------------------------------------
TEXTO = {"INSERTAR": "insertar", "EN": "en", "TABLA": "tabla", "IDENT": "x",
         "VALORES": "valores", "':'": ":", "'='": "=", "','": ",",
         "FIN": "fin", "';'": ";"}
VALORES = ["1", "'a'", "verdadero"]


def a_texto(simbolos, rnd):
    partes = []
    for s in simbolos:
        partes.append(rnd.choice(VALORES) if s == "VALOR" else TEXTO[s])
    return " ".join(partes)


def prueba_afd_sintactico_vs_bison():
    print("\n4. AFD sintáctico (a nivel de tokens) vs. parser Bison")
    rnd = random.Random(7)
    sentencia = ["INSERTAR", "EN", "TABLA", "IDENT", "VALORES", "':'", "IDENT", "'='",
                 "VALOR", "FIN", "';'"]
    con_coma = ["INSERTAR", "EN", "TABLA", "IDENT", "VALORES", "':'", "IDENT", "'='",
                "VALOR", "','", "IDENT", "'='", "VALOR", "FIN", "';'"]
    vocabulario = A.AFD_SINTACTICO["alfabeto"]

    def asignacion():
        return ["IDENT", "'='", "VALOR"]

    def sentencia_con(k):
        """Sentencia válida con k asignaciones separadas por comas."""
        cuerpo = asignacion()
        for _ in range(k - 1):
            cuerpo += ["','"] + asignacion()
        return (["INSERTAR", "EN", "TABLA", "IDENT", "VALORES", "':'"]
                + cuerpo + ["FIN", "';'"])

    # Programas VÁLIDOS: de 0 a 3 sentencias con 1 a 4 asignaciones cada una.
    base = [[]]
    for _ in range(40):
        prog = []
        for _ in range(rnd.randint(1, 3)):
            prog += sentencia_con(rnd.randint(1, 4))
        base.append(prog)
    base += [sentencia, con_coma]

    muestras = []
    for b in base:
        muestras.append(list(b))
        for _ in range(12):                                  # mutaciones
            m = list(b)
            op = rnd.choice(["borrar", "insertar", "cambiar", "truncar"])
            if m and op == "borrar":
                del m[rnd.randrange(len(m))]
            elif op == "insertar":
                m.insert(rnd.randint(0, len(m)), rnd.choice(vocabulario))
            elif m and op == "cambiar":
                m[rnd.randrange(len(m))] = rnd.choice(vocabulario)
            elif m and op == "truncar":
                m = m[:rnd.randrange(len(m))]
            muestras.append(m)

    # Se vuelve a un conjunto sin duplicados para no repetir ejecuciones.
    unicas = {tuple(m) for m in muestras}
    discrepancias = []
    aceptadas = 0
    with tempfile.TemporaryDirectory() as tmp:
        bd = os.path.join(tmp, "s.db")
        for m in sorted(unicas):
            texto = a_texto(m, rnd)
            esperado = A.aceptar_tokens(list(m))
            aceptadas += esperado
            rc, out, err = ejecutar(["-q", "-l", "-d", bd, "-e", texto])
            # "Aceptado por la sintaxis" = ningún error léxico/sintáctico y
            # ninguna sentencia rechazada por sintaxis (la semántica no cuenta:
            # 'x' no es una tabla real y se rechazará después, y eso es correcto).
            r = lambda e: int(re.search(re.escape(e) + r" \.+ (\d+)", out).group(1))
            sintaxis_ok = (r("Sentencias rechazadas (léxico/sintaxis)") == 0
                           and r("Diagnósticos sintácticos") == 0
                           and r("Diagnósticos léxicos") == 0)
            if sintaxis_ok != esperado:
                discrepancias.append((texto, esperado, sintaxis_ok))
    print(f"  ({len(unicas)} programas distintos; {aceptadas} aceptados por el AFD)")
    comprobar(not discrepancias,
              "AFD sintáctico y Bison aceptan exactamente los mismos programas"
              + ("" if not discrepancias else f"  (discrepancias: {discrepancias[:3]})"))


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not os.path.exists(BIN):
        sys.exit("No existe build/sqlparser: ejecute `make` primero.")
    prueba_integracion()
    prueba_lexica_puntual()
    prueba_afd_vs_flex()
    prueba_afd_sintactico_vs_bison()
    print()
    if fallos:
        print(f"RESULTADO: {fallos} comprobación(es) fallida(s).")
        sys.exit(1)
    print("RESULTADO: todas las comprobaciones pasaron.")
