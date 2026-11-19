#!/usr/bin/env python3
"""
generar_figuras.py -- Genera los diagramas del Punto 3.2 (requiere Graphviz)
---------------------------------------------------------------------------
Uso (desde la raíz del proyecto):   python3 herramientas/generar_figuras.py

Los autómatas se dibujan a partir de las definiciones de automatas.py, de modo
que los diagramas y las tablas de transición nunca se contradicen.
Escribe  figuras/*.dot  y  figuras/*.png.
"""
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import automatas as A                                            # noqa: E402

FIG = os.path.join(RAIZ, "figuras")
os.makedirs(FIG, exist_ok=True)

FUENTE = 'fontname="Helvetica"'


def renderizar(nombre, dot, dpi=160):
    ruta_dot = os.path.join(FIG, nombre + ".dot")
    ruta_png = os.path.join(FIG, nombre + ".png")
    with open(ruta_dot, "w", encoding="utf-8") as f:
        f.write(dot)
    subprocess.run(["dot", "-Tpng", f"-Gdpi={dpi}", ruta_dot, "-o", ruta_png],
                   check=True)
    print("  generada", os.path.relpath(ruta_png, RAIZ))


def arquitectura():
    return f'''digraph ARQ {{
  rankdir=LR; bgcolor="white"; pad=0.3; nodesep=0.45; ranksep=0.55;
  node [shape=box, style="rounded,filled", fillcolor="#f4f4f4", {FUENTE}, fontsize=12, margin="0.18,0.10"];
  edge [{FUENTE}, fontsize=11];

  entrada [label="Entrada\\n(archivo, texto o stdin)", fillcolor="#ffffff"];
  lexer   [label="Analizador léxico\\nFlex · lexer.l\\nAFD de 61 estados", fillcolor="#dbe8f7"];
  parser  [label="Analizador sintáctico\\nBison · parser.y\\nLALR(1) de 24 estados", fillcolor="#dbe8f7"];
  sem     [label="Validación semántica\\ndb.c · catálogo de SQLite\\n(tabla, campos, tipos)", fillcolor="#e3f1dc"];
  ins     [label="INSERT preparado\\nparámetros enlazados\\n(sqlite3_bind_*)", fillcolor="#e3f1dc"];
  bd      [label="Base de datos\\nSQLite · taller.db\\n3 tablas × 4 campos", shape=cylinder, fillcolor="#fff2cc"];
  err     [label="Diagnósticos\\n(stderr): línea, columna\\ny tipo de error", fillcolor="#fbe0e0"];

  entrada -> lexer  [label="caracteres"];
  lexer   -> parser [label="tokens"];
  parser  -> sem    [label="sentencia\\nválida"];
  sem     -> ins    [label="esquema\\ncorrecto"];
  ins     -> bd;
  lexer   -> err [style=dashed, color="#b04040"];
  parser  -> err [style=dashed, color="#b04040"];
  sem     -> err [style=dashed, color="#b04040"];
}}'''


def arbol_derivacion():
    """Árbol de derivación de:
       insertar en tabla clientes valores: id = 1, nombre = 'Ana' fin;"""
    return f'''digraph ARBOL {{
  bgcolor="white"; pad=0.3; nodesep=0.25; ranksep=0.45; ordering=out;
  node [shape=ellipse, style=filled, fillcolor="#dbe8f7", {FUENTE}, fontsize=12];
  edge [arrowhead=none];

  P0  [label="programa"];
  P1  [label="programa"];  eps [label="ε", shape=plaintext, style=""];
  S   [label="sentencia"];
  LA  [label="lista_asignaciones"];
  LA1 [label="lista_asignaciones"];
  AS1 [label="asignacion"];
  AS2 [label="asignacion"];
  V1  [label="valor"];
  V2  [label="valor"];

  t1 [shape=box, fillcolor="#fff2cc", label="INSERTAR\\ninsertar"];
  t2 [shape=box, fillcolor="#fff2cc", label="EN\\nen"];
  t3 [shape=box, fillcolor="#fff2cc", label="TABLA\\ntabla"];
  t4 [shape=box, fillcolor="#fff2cc", label="IDENT\\nclientes"];
  t5 [shape=box, fillcolor="#fff2cc", label="VALORES\\nvalores"];
  t6 [shape=box, fillcolor="#fff2cc", label="':'"];
  t7 [shape=box, fillcolor="#fff2cc", label="FIN\\nfin"];
  t8 [shape=box, fillcolor="#fff2cc", label="';'"];
  c1 [shape=box, fillcolor="#fff2cc", label="IDENT\\nid"];
  e1 [shape=box, fillcolor="#fff2cc", label="'='"];
  n1 [shape=box, fillcolor="#fff2cc", label="ENTERO\\n1"];
  co [shape=box, fillcolor="#fff2cc", label="','"];
  c2 [shape=box, fillcolor="#fff2cc", label="IDENT\\nnombre"];
  e2 [shape=box, fillcolor="#fff2cc", label="'='"];
  s1 [shape=box, fillcolor="#fff2cc", label="CADENA\\n'Ana'"];

  P0 -> P1; P0 -> S;
  P1 -> eps;
  S -> t1; S -> t2; S -> t3; S -> t4; S -> t5; S -> t6; S -> LA; S -> t7; S -> t8;
  LA -> LA1; LA -> co; LA -> AS2;
  LA1 -> AS1;
  AS1 -> c1; AS1 -> e1; AS1 -> V1; V1 -> n1;
  AS2 -> c2; AS2 -> e2; AS2 -> V2; V2 -> s1;
}}'''


def esquema_bd():
    return f'''digraph BD {{
  rankdir=LR; bgcolor="white"; pad=0.3; nodesep=0.7; ranksep=1.0;
  node [shape=plaintext, {FUENTE}, fontsize=12];
  edge [{FUENTE}, fontsize=11];

  clientes [label=<
    <TABLE BORDER="1" CELLBORDER="1" CELLSPACING="0" CELLPADDING="5">
      <TR><TD COLSPAN="2" BGCOLOR="#dbe8f7"><B>clientes</B></TD></TR>
      <TR><TD PORT="id" ALIGN="LEFT">id</TD><TD ALIGN="LEFT">INTEGER · PK</TD></TR>
      <TR><TD ALIGN="LEFT">nombre</TD><TD ALIGN="LEFT">TEXT · NOT NULL</TD></TR>
      <TR><TD ALIGN="LEFT">ciudad</TD><TD ALIGN="LEFT">TEXT</TD></TR>
      <TR><TD ALIGN="LEFT">activo</TD><TD ALIGN="LEFT">BOOLEAN</TD></TR>
    </TABLE>>];

  pedidos [label=<
    <TABLE BORDER="1" CELLBORDER="1" CELLSPACING="0" CELLPADDING="5">
      <TR><TD COLSPAN="2" BGCOLOR="#dbe8f7"><B>pedidos</B></TD></TR>
      <TR><TD ALIGN="LEFT">id</TD><TD ALIGN="LEFT">INTEGER · PK</TD></TR>
      <TR><TD PORT="cid" ALIGN="LEFT">cliente_id</TD><TD ALIGN="LEFT">INTEGER · NOT NULL · FK</TD></TR>
      <TR><TD ALIGN="LEFT">total</TD><TD ALIGN="LEFT">INTEGER</TD></TR>
      <TR><TD ALIGN="LEFT">pagado</TD><TD ALIGN="LEFT">BOOLEAN</TD></TR>
    </TABLE>>];

  productos [label=<
    <TABLE BORDER="1" CELLBORDER="1" CELLSPACING="0" CELLPADDING="5">
      <TR><TD COLSPAN="2" BGCOLOR="#dbe8f7"><B>productos</B></TD></TR>
      <TR><TD ALIGN="LEFT">codigo</TD><TD ALIGN="LEFT">INTEGER · PK</TD></TR>
      <TR><TD ALIGN="LEFT">nombre</TD><TD ALIGN="LEFT">TEXT · NOT NULL</TD></TR>
      <TR><TD ALIGN="LEFT">stock</TD><TD ALIGN="LEFT">INTEGER</TD></TR>
      <TR><TD ALIGN="LEFT">disponible</TD><TD ALIGN="LEFT">BOOLEAN</TD></TR>
    </TABLE>>];

  pedidos:cid -> clientes:id [label="REFERENCES"];
  productos [group=g2];
}}'''


def main():
    print("Generando figuras...")
    renderizar("fig_01_arquitectura", arquitectura())
    renderizar("fig_02_afd_identificador", A.dot_lexico(A.AFD_LEXICOS["IDENT"]))
    renderizar("fig_03_afd_entero", A.dot_lexico(A.AFD_LEXICOS["ENTERO"]))
    renderizar("fig_04_afd_cadena", A.dot_lexico(A.AFD_LEXICOS["CADENA"]))
    renderizar("fig_05_afd_comentario", A.dot_lexico(A.AFD_LEXICOS["COMENTARIO"]))
    renderizar("fig_06_trie_palabras_reservadas", A.dot_trie())
    renderizar("fig_08_afd_sintactico", A.dot_sintactico())
    renderizar("fig_07_arbol_derivacion", arbol_derivacion())
    renderizar("fig_09_esquema_bd", esquema_bd())


if __name__ == "__main__":
    main()
