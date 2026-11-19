/*
 * lexer.l  --  Analizador léxico (Flex) del lenguaje de inserción
 * ---------------------------------------------------------------------------
 * Reconoce los tokens de sentencias como:
 *
 *   insertar en tabla clientes valores: id = 1, nombre = 'Ana' fin;
 *
 * Familias de tokens:
 *   1. Palabras reservadas : insertar, en, tabla, valores, fin
 *   2. Booleanos           : verdadero, falso, true, false
 *   3. Identificadores     : [A-Za-z_][A-Za-z0-9_]*
 *   4. Enteros             : -?[0-9]+
 *   5. Cadenas             : '...' con '' como comilla escapada
 *   6. Puntuación          : :  ;  ,  =
 *   7. Se ignoran          : espacios, tabuladores, saltos de línea y
 *                            comentarios de línea que empiezan con --
 *
 * Flex compila todas las reglas en UN solo autómata finito determinista
 * (AFD) y lo ejecuta con la política "coincidencia más larga; en empate,
 * la regla escrita primero". Por eso las palabras reservadas están ANTES
 * que la regla de identificadores: "fin" coincide con ambas con la misma
 * longitud y gana la primera; en cambio "final" es más largo para la regla
 * de identificadores y gana esta.
 * ---------------------------------------------------------------------------
 */

/* ---- Opciones de Flex ----------------------------------------------------
 *  noyywrap  : no se encadenan varios archivos de entrada.
 *  nounput / noinput : evita funciones auxiliares sin usar (silencia avisos).
 *  yylineno  : Flex mantiene el número de línea actual en la variable yylineno.
 *  caseless  : las palabras reservadas no distinguen mayúsculas de minúsculas
 *              (INSERTAR = insertar), como es habitual en SQL.
 *  8bit      : el escáner trabaja con bytes 0-255 (permite acentos dentro de
 *              las cadenas, codificadas en UTF-8).
 */
%option noyywrap nounput noinput yylineno caseless 8bit

%{
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include "tipos.h"
#include "parser.tab.h"      /* códigos de token y YYSTYPE generados por Bison */

/* ---- Seguimiento de la columna ------------------------------------------
 * Flex lleva la línea (yylineno) pero no la columna. Se calcula aquí y se
 * deposita en yylloc, que Bison usa para ubicar los errores (@1, @$, ...).
 */
static int columna = 1;

/* YY_USER_ACTION se ejecuta antes de la acción de CADA regla. */
#define YY_USER_ACTION                                   \
    yylloc.first_line   = yylineno;                      \
    yylloc.first_column = columna;                       \
    yylloc.last_line    = yylineno;                      \
    yylloc.last_column  = columna + yyleng - 1;          \
    columna += yyleng;

/* Bandera consultada por yyerror() para no reportar dos veces el mismo
 * problema: un error léxico ya fue informado por el escáner y el parser
 * solo debe recuperarse, sin emitir un segundo mensaje. */
int ultimo_token_fue_error_lexico = 0;

/* Devuelve un token "normal" y limpia la bandera. */
#define DEVOLVER(t)  do { ultimo_token_fue_error_lexico = 0; return (t); } while (0)

/* Informa un error léxico y devuelve el token especial ERROR_LEXICO. */
#define ERROR_LEX(...)                                                     \
    do {                                                                   \
        fprintf(stderr, "Error léxico [línea %d, col %d]: ",               \
                yylloc.first_line, yylloc.first_column);                   \
        fprintf(stderr, __VA_ARGS__);                                      \
        fputc('\n', stderr);                                               \
        estadisticas.errores_lexicos++;                                    \
        ultimo_token_fue_error_lexico = 1;                                 \
        return ERROR_LEXICO;                                               \
    } while (0)

/* Copia una cadena en memoria dinámica (strdup no es ISO C estricto). */
static char *copiar(const char *s, size_t n)
{
    char *p = malloc(n + 1);
    if (p == NULL) { fprintf(stderr, "Error fatal: memoria insuficiente.\n"); exit(2); }
    memcpy(p, s, n);
    p[n] = '\0';
    return p;
}

/* Quita las comillas externas de un literal y convierte '' en '.
 * Entrada: 'O''Brien'   ->   Salida: O'Brien  */
static char *desescapar_cadena(const char *lexema, size_t largo)
{
    char *res = malloc(largo);           /* el resultado nunca es más largo */
    size_t j = 0;
    if (res == NULL) { fprintf(stderr, "Error fatal: memoria insuficiente.\n"); exit(2); }
    for (size_t i = 1; i + 1 < largo; i++) {      /* salta ' inicial y final */
        res[j++] = lexema[i];
        if (lexema[i] == '\'' ) i++;              /* '' -> ' (salta la 2.ª) */
    }
    res[j] = '\0';
    return res;
}
%}

/* ---- Definiciones (macros de expresiones regulares) --------------------- */
LETRA       [A-Za-z_]
DIGITO      [0-9]
IDENT       {LETRA}({LETRA}|{DIGITO})*
ENTERO      -?{DIGITO}+
/* Cuerpo de una cadena: cualquier byte excepto ' y salto de línea, o bien
 * dos comillas seguidas ('') que representan una comilla literal.          */
CUERPO      ([^'\n]|'')*
CADENA_OK   '{CUERPO}'
CADENA_ABIERTA  '{CUERPO}
COMENTARIO  "--"[^\n]*

%%

 /* ------------------------------------------------------------------------
  * REGLAS. El orden importa solo en caso de empate de longitud.
  * ------------------------------------------------------------------------ */

 /* 1. Palabras reservadas (deben ir antes que IDENT). */
"insertar"      { DEVOLVER(INSERTAR); }
"en"            { DEVOLVER(EN); }
"tabla"         { DEVOLVER(TABLA); }
"valores"       { DEVOLVER(VALORES); }
"fin"           { DEVOLVER(FIN); }

 /* 2. Literales booleanos: el token lleva su valor en yylval.booleano. */
"verdadero"|"true"  { yylval.booleano = 1; DEVOLVER(BOOLEANO); }
"falso"|"false"     { yylval.booleano = 0; DEVOLVER(BOOLEANO); }

 /* 3. Identificadores: el token lleva una copia dinámica del lexema. */
{IDENT}         { yylval.cadena = copiar(yytext, (size_t)yyleng); DEVOLVER(IDENT); }

 /* 4. Enteros con signo opcional. strtoll detecta el desbordamiento. */
{ENTERO}        {
                    errno = 0;
                    long long n = strtoll(yytext, NULL, 10);
                    if (errno == ERANGE)
                        ERROR_LEX("entero fuera del rango de 64 bits: %s", yytext);
                    yylval.entero = n;
                    DEVOLVER(ENTERO);
                }

 /* 5. Cadenas. La regla "OK" es más larga que la "ABIERTA" cuando la cadena
  *    está cerrada, por lo que la coincidencia más larga elige la correcta. */
{CADENA_OK}     {
                    yylval.cadena = desescapar_cadena(yytext, (size_t)yyleng);
                    DEVOLVER(CADENA);
                }
{CADENA_ABIERTA} {
                    ERROR_LEX("cadena sin cerrar (falta la comilla ' final)");
                }

 /* 6. Puntuación: se devuelve el propio carácter como código de token. */
":"|";"|","|"="  { DEVOLVER(yytext[0]); }

 /* 7. Elementos que se ignoran. */
{COMENTARIO}    { /* comentario de línea: se descarta */ }
[ \t\r]+        { /* espacios en blanco: se descartan */ }
\n              { columna = 1; }            /* nueva línea: reinicia columna */

 /* 8. Errores léxicos: cualquier otro símbolo. */
[\x80-\xFF]+    { ERROR_LEX("carácter no ASCII fuera de una cadena"); }
.               {
                    if (yytext[0] == '"')
                        ERROR_LEX("las cadenas se delimitan con comilla simple ('), no doble (\")");
                    else
                        ERROR_LEX("carácter no reconocido '%c'", yytext[0]);
                }

%%

/* Reinicia el contador de columna (se usa al empezar a analizar otro texto). */
void lexer_reiniciar_posicion(void)
{
    columna = 1;
    yylineno = 1;
}
