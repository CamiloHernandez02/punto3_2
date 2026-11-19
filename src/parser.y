/*
 * parser.y  --  Analizador sintáctico (Bison) del lenguaje de inserción
 * ---------------------------------------------------------------------------
 * GRAMÁTICA (BNF). Los terminales van en MAYÚSCULAS o entre comillas:
 *
 *   <programa>      ::= ε
 *                     | <programa> <sentencia>
 *
 *   <sentencia>     ::= INSERTAR EN TABLA IDENT VALORES ':' <lista_asig> FIN ';'
 *                     | error ';'                       (recuperación de errores)
 *
 *   <lista_asig>    ::= <asignacion>
 *                     | <lista_asig> ',' <asignacion>
 *
 *   <asignacion>    ::= IDENT '=' <valor>
 *
 *   <valor>         ::= ENTERO | CADENA | BOOLEANO
 *
 * Es una gramática LALR(1) sin conflictos (se exige con %expect 0). Como no
 * hay anidamiento, el lenguaje que genera es REGULAR (Tipo 3 de Chomsky);
 * Bison lo procesa igualmente con su autómata de pila LALR(1).
 *
 * La recursión es por la IZQUIERDA (<lista_asig> ',' <asignacion>) porque en
 * un analizador ascendente consume pila constante, en lugar de O(n).
 * ---------------------------------------------------------------------------
 */

/* Este bloque se copia también en parser.tab.h: tipos que necesita %union. */
%code requires {
    #include "tipos.h"
}

%{
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "tipos.h"
#include "db.h"

int  yylex(void);                       /* la define Flex (lexer.l)   */
void yyerror(const char *mensaje);      /* se define al final         */

extern int ultimo_token_fue_error_lexico;   /* ver lexer.l */

/* Asignaciones acumuladas de la sentencia que se está analizando. Se vacía
 * (a) al terminar de ejecutar una sentencia válida y (b) al recuperarse de
 * un error, por lo que siempre está vacía al empezar una sentencia nueva. */
static ListaCampos campos_actuales;

/* Reserva inicial de la lista; se invoca desde main antes de yyparse(). */
void parser_iniciar(void)  { lista_campos_iniciar(&campos_actuales); }

/* Libera lo que haya quedado si el análisis terminó de forma abrupta. */
void parser_liberar(void)  { lista_campos_vaciar(&campos_actuales); }
%}

/* ---- Opciones de Bison ---------------------------------------------------
 *  %locations           : activa @1, @$, ... (línea y columna de cada símbolo)
 *  parse.error verbose  : los mensajes de error indican token hallado y esperados
 *  %expect 0            : si Bison detecta algún conflicto shift/reduce o
 *                         reduce/reduce, la compilación FALLA. Garantiza que la
 *                         gramática es LALR(1) pura.
 */
%locations
%define parse.error verbose
%expect 0

/* ---- Tipos de los valores semánticos ------------------------------------ */
%union {
    char      *cadena;     /* IDENT y CADENA: texto en memoria dinámica */
    long long  entero;     /* ENTERO                                    */
    int        booleano;   /* BOOLEANO: 0 o 1                           */
    Valor     *valor;      /* no terminal <valor>                       */
}

/* ---- Tokens -------------------------------------------------------------
 * El texto entre comillas es un alias: se usa en los mensajes de error.
 * A las palabras clave se les pone comillas simples dentro del alias para
 * que el mensaje las muestre como 'fin', igual que los símbolos ';' y ','. */
%token END 0 "fin de archivo"
%token INSERTAR "'insertar'"
%token EN       "'en'"
%token TABLA    "'tabla'"
%token VALORES  "'valores'"
%token FIN      "'fin'"
%token <cadena>   IDENT    "identificador"
%token <cadena>   CADENA   "cadena"
%token <entero>   ENTERO   "entero"
%token <booleano> BOOLEANO "booleano"
%token ERROR_LEXICO "símbolo inválido"

%type <valor> valor

/* Si la recuperación de errores descarta un símbolo de la pila, se libera la
 * memoria dinámica que lleva (evita fugas). */
%destructor { free($$); }          <cadena>
%destructor { valor_liberar($$); } <valor>

%%

programa
    : %empty
    | programa sentencia
    ;

sentencia
    : INSERTAR EN TABLA IDENT[tabla] VALORES ':' lista_asignaciones FIN ';'
        {
            /* Sentencia sintácticamente correcta: pasa a la validación
             * semántica y a la inserción en la base de datos. */
            if (db_insertar($tabla, &campos_actuales,
                            @$.first_line, @$.first_column) == 0)
                estadisticas.insertadas++;
            else
                estadisticas.rechazadas_semantica++;

            free($tabla);                       /* la posesión era nuestra */
            lista_campos_vaciar(&campos_actuales);
        }
    | error ';'
        {
            /* Recuperación en "modo pánico": tras un error se descartan
             * tokens hasta el siguiente ';' y se continúa con la sentencia
             * que sigue. */
            lista_campos_vaciar(&campos_actuales);
            estadisticas.rechazadas_sintaxis++;
            yyerrok;     /* permite reportar un nuevo error inmediatamente */
        }
    ;

lista_asignaciones
    : asignacion
    | lista_asignaciones ',' asignacion
    ;

asignacion
    : IDENT '=' valor
        {
            /* Se guarda "campo = valor" en la sentencia actual. La posesión
             * de $1 y $3 pasa a la lista. */
            lista_campos_agregar(&campos_actuales, $1, $3,
                                 @1.first_line, @1.first_column);
        }
    ;

valor
    : ENTERO     { $$ = valor_crear_entero($1);   }
    | CADENA     { $$ = valor_crear_cadena($1);   }
    | BOOLEANO   { $$ = valor_crear_booleano($1); }
    ;

%%

/* Traduce al español las partes fijas de los mensajes de Bison. Se hace
 * sustituyendo fragmentos de la cadena original (solo cosmético). */
static void traducir(const char *origen, char *destino, size_t cap)
{
    static const char *const par[][2] = {
        { "syntax error, ", ""                 },
        { "syntax error",   "error de sintaxis" },
        { "unexpected ",    "se encontró "     },
        { ", expecting ",   "; se esperaba "   },
        { " or ",           " o "              },
        /* Los alias de palabras clave llevan comillas simples ('fin'); Bison
         * los rodea además de comillas dobles, que aquí se eliminan. */
        { "\"'",            "'"                },
        { "'\"",            "'"                },
    };
    char tmp[512];
    snprintf(tmp, sizeof tmp, "%s", origen);

    for (size_t k = 0; k < sizeof par / sizeof par[0]; k++) {
        char *pos;
        while ((pos = strstr(tmp, par[k][0])) != NULL) {
            char resto[512];
            snprintf(resto, sizeof resto, "%s", pos + strlen(par[k][0]));
            *pos = '\0';
            size_t n = strlen(tmp);
            snprintf(tmp + n, sizeof tmp - n, "%s%s", par[k][1], resto);
        }
    }
    snprintf(destino, cap, "%s", tmp);
}

/* Bison invoca yyerror() al detectar un error sintáctico. */
void yyerror(const char *mensaje)
{
    /* Si el culpable es un símbolo que el escáner ya reportó, no se repite. */
    if (ultimo_token_fue_error_lexico)
        return;

    char texto[512];
    traducir(mensaje, texto, sizeof texto);
    fprintf(stderr, "Error sintáctico [línea %d, col %d]: %s\n",
            yylloc.first_line, yylloc.first_column, texto);
    estadisticas.errores_sintacticos++;
}
