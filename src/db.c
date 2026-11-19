/*
 * db.c  --  Capa de base de datos (SQLite)
 * ---------------------------------------------------------------------------
 * Responsabilidades:
 *   1. Crear la base de datos relacional local con TRES tablas de CUATRO
 *      campos cada una.
 *   2. Validar semánticamente cada sentencia contra el esquema REAL de la BD
 *      (consultando el catálogo de SQLite, no una lista fija en el código):
 *        - la tabla existe,
 *        - cada campo existe y no se repite,
 *        - el tipo del literal coincide con el tipo declarado de la columna,
 *        - están presentes los campos obligatorios (NOT NULL sin valor por
 *          defecto).
 *   3. Insertar la fila con una sentencia preparada y parámetros enlazados.
 *
 * SEGURIDAD (inyección SQL):
 *   Los VALORES nunca se concatenan al texto SQL: se enlazan con
 *   sqlite3_bind_*. Los NOMBRES de tabla y columna no pueden enlazarse, por lo
 *   que se toman del catálogo de SQLite (no del texto del usuario) y se
 *   escapan con el especificador %w de sqlite3_str_appendf.
 * ---------------------------------------------------------------------------
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>      /* strcasecmp, strncasecmp */
#include <stdarg.h>
#include <sqlite3.h>
#include "db.h"

static sqlite3 *bd = NULL;

/* Tablas predefinidas (se usan para mostrar el resultado final). */
static const char *const TABLAS[] = { "clientes", "productos", "pedidos" };
#define NUM_TABLAS ((int)(sizeof TABLAS / sizeof TABLAS[0]))

/* Esquema: 3 tablas x 4 campos. BOOLEAN se almacena como 0/1.
 * pedidos.cliente_id tiene clave foránea hacia clientes.id. */
static const char *const ESQUEMA =
    "CREATE TABLE IF NOT EXISTS clientes ("
    "  id      INTEGER PRIMARY KEY,"
    "  nombre  TEXT    NOT NULL,"
    "  ciudad  TEXT,"
    "  activo  BOOLEAN"
    ");"
    "CREATE TABLE IF NOT EXISTS productos ("
    "  codigo      INTEGER PRIMARY KEY,"
    "  nombre      TEXT    NOT NULL,"
    "  stock       INTEGER,"
    "  disponible  BOOLEAN"
    ");"
    "CREATE TABLE IF NOT EXISTS pedidos ("
    "  id          INTEGER PRIMARY KEY,"
    "  cliente_id  INTEGER NOT NULL REFERENCES clientes(id),"
    "  total       INTEGER,"
    "  pagado      BOOLEAN"
    ");";

#define MAX_COLUMNAS 64

/* Metadatos de una columna, leídos del catálogo de SQLite. */
typedef struct {
    char nombre[64];
    char tipo[32];
    int  obligatoria;   /* NOT NULL, sin DEFAULT y que no es clave primaria */
} Columna;

/* ---------------------------------------------------------------------------
 * Utilidades de mensajes
 * ------------------------------------------------------------------------- */
static void error_semantico(int linea, int col, const char *fmt, ...)
{
    va_list ap;
    fprintf(stderr, "Error semántico [línea %d, col %d]: ", linea, col);
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fputc('\n', stderr);
}

/* ---------------------------------------------------------------------------
 * Apertura y cierre
 * ------------------------------------------------------------------------- */
int db_abrir(const char *ruta)
{
    char *msg = NULL;

    if (sqlite3_open(ruta, &bd) != SQLITE_OK) {
        fprintf(stderr, "No se pudo abrir la base de datos '%s': %s\n",
                ruta, sqlite3_errmsg(bd));
        return -1;
    }
    if (sqlite3_exec(bd, ESQUEMA, NULL, NULL, &msg) != SQLITE_OK) {
        fprintf(stderr, "No se pudo crear el esquema: %s\n", msg);
        sqlite3_free(msg);
        return -1;
    }
    /* PRAGMA foreign_keys debe ejecutarse FUERA de una transacción.
     * Luego se abre una sola transacción para toda la sesión: confirmar
     * miles de filas con un único COMMIT es mucho más rápido que un COMMIT
     * (y su sincronización a disco) por fila. Un INSERT que falle solo
     * revierte esa sentencia, no la transacción completa. */
    if (sqlite3_exec(bd, "PRAGMA foreign_keys = ON; BEGIN;", NULL, NULL, &msg)
            != SQLITE_OK) {
        fprintf(stderr, "No se pudo iniciar la transacción: %s\n", msg);
        sqlite3_free(msg);
        return -1;
    }
    return 0;
}

void db_cerrar(void)
{
    if (bd == NULL) return;
    sqlite3_exec(bd, "COMMIT;", NULL, NULL, NULL);
    sqlite3_close(bd);
    bd = NULL;
}

/* ---------------------------------------------------------------------------
 * Catálogo: columnas de una tabla
 *
 * pragma_table_info(?1) es una función de tabla que acepta el nombre como
 * PARÁMETRO enlazado (no se concatena). Devuelve cero filas si la tabla no
 * existe.
 * ------------------------------------------------------------------------- */
static int cargar_columnas(const char *tabla, Columna cols[], int *n)
{
    static const char *const SQL =
        "SELECT name, type, \"notnull\", dflt_value IS NOT NULL, pk "
        "FROM pragma_table_info(?1)";
    sqlite3_stmt *st = NULL;

    *n = 0;
    if (sqlite3_prepare_v2(bd, SQL, -1, &st, NULL) != SQLITE_OK) {
        fprintf(stderr, "Error interno al consultar el catálogo: %s\n",
                sqlite3_errmsg(bd));
        return -1;
    }
    sqlite3_bind_text(st, 1, tabla, -1, SQLITE_TRANSIENT);

    while (sqlite3_step(st) == SQLITE_ROW) {
        if (*n >= MAX_COLUMNAS) {
            fprintf(stderr, "Error interno: la tabla supera %d columnas.\n",
                    MAX_COLUMNAS);
            sqlite3_finalize(st);
            return -1;
        }
        Columna *c = &cols[(*n)++];
        snprintf(c->nombre, sizeof c->nombre, "%s",
                 (const char *)sqlite3_column_text(st, 0));
        snprintf(c->tipo, sizeof c->tipo, "%s",
                 (const char *)sqlite3_column_text(st, 1));
        int notnull     = sqlite3_column_int(st, 2);
        int tiene_deflt = sqlite3_column_int(st, 3);
        int es_pk       = sqlite3_column_int(st, 4);
        c->obligatoria  = notnull && !tiene_deflt && !es_pk;
    }
    sqlite3_finalize(st);
    return 0;
}

/* ¿El literal es compatible con el tipo SQL declarado de la columna?
 *   INTEGER -> ENTERO     TEXT -> CADENA     BOOLEAN -> BOOLEANO        */
static int tipo_compatible(const char *tipo_sql, TipoValor v)
{
    if (strcasecmp(tipo_sql, "INTEGER") == 0 || strcasecmp(tipo_sql, "INT") == 0)
        return v == V_ENTERO;
    if (strcasecmp(tipo_sql, "TEXT") == 0)
        return v == V_CADENA;
    if (strcasecmp(tipo_sql, "BOOLEAN") == 0)
        return v == V_BOOLEANO;
    return 0;   /* tipo de columna no soportado por el lenguaje */
}

/* ---------------------------------------------------------------------------
 * db_insertar: validación semántica + INSERT
 * ------------------------------------------------------------------------- */
int db_insertar(const char *tabla, const ListaCampos *campos,
                int linea, int columna)
{
    Columna cols[MAX_COLUMNAS];
    int     ncols = 0;
    int     usado[MAX_COLUMNAS] = { 0 };   /* ¿la columna j ya fue asignada? */
    int    *destino = NULL;                /* destino[i] = columna del campo i */
    int     ok = 1;

    /* 1. Tablas internas de SQLite: nunca se pueden modificar. */
    if (strncasecmp(tabla, "sqlite_", 7) == 0) {
        error_semantico(linea, columna,
                        "la tabla '%s' es reservada del sistema", tabla);
        return -1;
    }

    /* 2. La tabla debe existir. */
    if (cargar_columnas(tabla, cols, &ncols) != 0)
        return -1;
    if (ncols == 0) {
        error_semantico(linea, columna, "la tabla '%s' no existe", tabla);
        return -1;
    }

    /* 3. Validar cada campo: existencia, unicidad y tipo. */
    destino = malloc((campos->cantidad + 1) * sizeof *destino);
    if (destino == NULL) { fprintf(stderr, "Error fatal: memoria insuficiente.\n"); exit(2); }

    for (size_t i = 0; i < campos->cantidad; i++) {
        const Campo *c = &campos->items[i];
        int j;

        destino[i] = -1;
        for (j = 0; j < ncols; j++)                     /* búsqueda lineal: las  */
            if (strcasecmp(cols[j].nombre, c->nombre) == 0)   /* tablas son pequeñas */
                break;

        if (j == ncols) {
            error_semantico(c->linea, c->columna,
                            "el campo '%s' no existe en la tabla '%s'",
                            c->nombre, tabla);
            ok = 0;
            continue;
        }
        if (usado[j]) {
            error_semantico(c->linea, c->columna,
                            "el campo '%s' aparece más de una vez", c->nombre);
            ok = 0;
            continue;
        }
        usado[j]   = 1;
        destino[i] = j;

        if (!tipo_compatible(cols[j].tipo, c->valor->tipo)) {
            error_semantico(c->linea, c->columna,
                            "el campo '%s' es de tipo %s y no admite un valor %s",
                            cols[j].nombre, cols[j].tipo,
                            tipo_valor_nombre(c->valor->tipo));
            ok = 0;
        }
    }

    /* 4. Campos obligatorios que no se suministraron. */
    for (int j = 0; j < ncols; j++) {
        if (cols[j].obligatoria && !usado[j]) {
            error_semantico(linea, columna,
                            "falta el campo obligatorio '%s' de la tabla '%s'",
                            cols[j].nombre, tabla);
            ok = 0;
        }
    }

    if (!ok) { free(destino); return -1; }

    /* 5. Construir "INSERT INTO "t" ("c1","c2",...) VALUES (?,?,...)".
     *    Los nombres salen del catálogo (cols[j].nombre) y se escapan con %w. */
    sqlite3_str *s = sqlite3_str_new(bd);
    sqlite3_str_appendf(s, "INSERT INTO \"%w\" (", tabla);
    for (size_t i = 0; i < campos->cantidad; i++)
        sqlite3_str_appendf(s, "%s\"%w\"", i ? "," : "", cols[destino[i]].nombre);
    sqlite3_str_appendall(s, ") VALUES (");
    for (size_t i = 0; i < campos->cantidad; i++)
        sqlite3_str_appendall(s, i ? ",?" : "?");
    sqlite3_str_appendall(s, ")");
    char *sql = sqlite3_str_finish(s);

    sqlite3_stmt *st = NULL;
    int rc = sqlite3_prepare_v2(bd, sql, -1, &st, NULL);
    sqlite3_free(sql);
    if (rc != SQLITE_OK) {
        fprintf(stderr, "Error de base de datos [línea %d, col %d]: %s\n",
                linea, columna, sqlite3_errmsg(bd));
        free(destino);
        return -1;
    }

    /* 6. Enlazar los valores (los índices de bind empiezan en 1). */
    for (size_t i = 0; i < campos->cantidad; i++) {
        const Valor *v = campos->items[i].valor;
        int idx = (int)i + 1;
        switch (v->tipo) {
            case V_ENTERO:
                sqlite3_bind_int64(st, idx, v->dato.entero);
                break;
            case V_CADENA:
                sqlite3_bind_text(st, idx, v->dato.cadena, -1, SQLITE_TRANSIENT);
                break;
            case V_BOOLEANO:
                sqlite3_bind_int(st, idx, v->dato.booleano);
                break;
        }
    }

    /* 7. Ejecutar. SQLITE_DONE = éxito. Aquí pueden aparecer errores que solo
     *    la BD conoce: clave primaria repetida, clave foránea inexistente... */
    rc = sqlite3_step(st);
    free(destino);
    if (rc != SQLITE_DONE) {
        fprintf(stderr, "Error de base de datos [línea %d, col %d]: %s\n",
                linea, columna, sqlite3_errmsg(bd));
        sqlite3_finalize(st);
        return -1;
    }
    sqlite3_finalize(st);

    printf("[OK] línea %d: 1 fila insertada en '%s' (rowid=%lld)\n",
           linea, tabla, (long long)sqlite3_last_insert_rowid(bd));
    return 0;
}

/* ---------------------------------------------------------------------------
 * Presentación del contenido de las tablas
 * ------------------------------------------------------------------------- */

/* Longitud en caracteres de una cadena UTF-8 (no en bytes), para alinear
 * columnas con acentos y eñes. Los bytes de continuación son 10xxxxxx. */
static size_t largo_utf8(const char *s)
{
    size_t n = 0;
    for (; *s; s++)
        if (((unsigned char)*s & 0xC0) != 0x80) n++;
    return n;
}

/* Texto con el que se muestra la celda c de la fila actual.
 * Las columnas BOOLEAN (almacenadas como 0/1) se muestran como
 * verdadero/falso para que coincidan con el lenguaje de entrada. */
static const char *texto_celda(sqlite3_stmt *st, int c)
{
    if (sqlite3_column_type(st, c) == SQLITE_NULL)
        return "NULL";
    const char *decl = sqlite3_column_decltype(st, c);
    if (decl != NULL && strcasecmp(decl, "BOOLEAN") == 0)
        return sqlite3_column_int(st, c) ? "verdadero" : "falso";
    return (const char *)sqlite3_column_text(st, c);
}

static void imprimir_fila(sqlite3_stmt *st, int nc, const size_t ancho[],
                          int es_encabezado)
{
    for (int c = 0; c < nc; c++) {
        const char *t = es_encabezado ? sqlite3_column_name(st, c)
                                      : texto_celda(st, c);
        int relleno = (int)(ancho[c] - largo_utf8(t));
        printf("| %s%*s ", t, relleno, "");
    }
    printf("|\n");
}

static void mostrar_tabla(const char *nombre)
{
    char sql[128];
    sqlite3_stmt *st = NULL;
    size_t ancho[MAX_COLUMNAS] = { 0 };
    int nc, filas = 0;

    snprintf(sql, sizeof sql, "SELECT * FROM \"%s\"", nombre);
    if (sqlite3_prepare_v2(bd, sql, -1, &st, NULL) != SQLITE_OK) return;
    nc = sqlite3_column_count(st);
    if (nc > MAX_COLUMNAS) nc = MAX_COLUMNAS;

    /* Pasada 1: anchura de cada columna = máximo entre encabezado y celdas. */
    for (int c = 0; c < nc; c++)
        ancho[c] = largo_utf8(sqlite3_column_name(st, c));
    while (sqlite3_step(st) == SQLITE_ROW) {
        filas++;
        for (int c = 0; c < nc; c++) {
            size_t l = largo_utf8(texto_celda(st, c));
            if (l > ancho[c]) ancho[c] = l;
        }
    }
    sqlite3_reset(st);

    /* Pasada 2: impresión. */
    printf("\nTabla %s (%d fila%s)\n", nombre, filas, filas == 1 ? "" : "s");
    imprimir_fila(st, nc, ancho, 1);     /* encabezado (nombres de columna) */

    for (int c = 0; c < nc; c++) {
        printf("+");
        for (size_t k = 0; k < ancho[c] + 2; k++) putchar('-');
    }
    printf("+\n");

    while (sqlite3_step(st) == SQLITE_ROW)
        imprimir_fila(st, nc, ancho, 0);
    sqlite3_finalize(st);
}

void db_mostrar_tablas(void)
{
    for (int i = 0; i < NUM_TABLAS; i++)
        mostrar_tabla(TABLAS[i]);
}
