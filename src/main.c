/*
 * main.c  --  Programa principal
 * ---------------------------------------------------------------------------
 * Uso:
 *   sqlparser [opciones] [archivo]
 *
 *   archivo      archivo con sentencias (si se omite o es '-', lee la entrada
 *                estándar)
 *   -e "texto"   analiza el texto dado en lugar de un archivo
 *   -d ruta      archivo de la base de datos SQLite (por defecto taller.db)
 *   -l           limpia: borra la base de datos antes de empezar
 *   -t           solo análisis léxico: imprime la tabla de tokens y termina
 *   -q           no imprime el contenido de las tablas al final
 *   -h           muestra esta ayuda
 *
 * Código de salida: 0 = todo correcto; 1 = hubo sentencias rechazadas o
 * errores léxicos; 2 = error de uso, de archivo o de base de datos.
 * ---------------------------------------------------------------------------
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>          /* getopt */
#include "tipos.h"
#include "db.h"
#include "parser.tab.h"      /* códigos de token, yyparse, yylloc, YYSTYPE */
#include "lexer.h"           /* yyin, yylex, yytext, yy_scan_string, ...   */

Estadisticas estadisticas = { 0, 0, 0, 0, 0 };

/* Definidas en parser.y y lexer.l */
void parser_iniciar(void);
void parser_liberar(void);
void lexer_reiniciar_posicion(void);

static void ayuda(const char *prog)
{
    fprintf(stderr,
        "Uso: %s [opciones] [archivo]\n"
        "  -e \"texto\"  analiza el texto dado en lugar de un archivo\n"
        "  -d ruta     base de datos SQLite (por defecto: taller.db)\n"
        "  -l          borra la base de datos antes de empezar\n"
        "  -t          solo análisis léxico (imprime la tabla de tokens)\n"
        "  -q          no muestra el contenido de las tablas al final\n"
        "  -h          esta ayuda\n", prog);
}

/* ---------------------------------------------------------------------------
 * Modo -t: solo análisis léxico.
 * Muestra, para cada token, su posición, su categoría y su lexema/valor.
 * ------------------------------------------------------------------------- */
static const char *categoria(int tok)
{
    switch (tok) {
        case INSERTAR: case EN: case TABLA: case VALORES: case FIN:
                          return "PALABRA_CLAVE";
        case IDENT:       return "IDENTIFICADOR";
        case ENTERO:      return "ENTERO";
        case CADENA:      return "CADENA";
        case BOOLEANO:    return "BOOLEANO";
        case ':': case ';': case ',': case '=':
                          return "PUNTUACION";
        case ERROR_LEXICO:return "ERROR_LEXICO";
    }
    return "?";
}

static int modo_tokens(void)
{
    int tok, total = 0;

    printf("%-8s %-15s %s\n", "LIN:COL", "CATEGORIA", "LEXEMA  ->  VALOR");
    printf("-------- --------------- ----------------------------------\n");

    while ((tok = yylex()) != 0) {
        total++;
        printf("%3d:%-4d %-15s %s", yylloc.first_line, yylloc.first_column,
               categoria(tok), yytext);

        /* Los tokens con valor semántico muestran ese valor ya procesado. */
        switch (tok) {
            case IDENT:
                free(yylval.cadena);
                break;
            case CADENA:
                printf("  ->  \"%s\"", yylval.cadena);   /* sin comillas ni '' */
                free(yylval.cadena);
                break;
            case ENTERO:
                printf("  ->  %lld", yylval.entero);
                break;
            case BOOLEANO:
                printf("  ->  %s", yylval.booleano ? "verdadero" : "falso");
                break;
        }
        putchar('\n');
    }
    printf("\nTotal de tokens: %d   Errores léxicos: %d\n",
           total, estadisticas.errores_lexicos);
    return estadisticas.errores_lexicos ? 1 : 0;
}

/* ---------------------------------------------------------------------------
 * main
 * ------------------------------------------------------------------------- */
int main(int argc, char **argv)
{
    const char *ruta_bd   = "taller.db";
    const char *texto     = NULL;     /* valor de -e */
    int limpiar = 0, solo_tokens = 0, silencioso = 0, opt;
    int codigo = 0;

    /* Salida por líneas: así stdout y stderr se intercalan en el orden
     * correcto incluso cuando se redirigen al mismo archivo (2>&1). */
    setvbuf(stdout, NULL, _IOLBF, 0);

    while ((opt = getopt(argc, argv, "e:d:ltqh")) != -1) {
        switch (opt) {
            case 'e': texto = optarg;       break;
            case 'd': ruta_bd = optarg;     break;
            case 'l': limpiar = 1;          break;
            case 't': solo_tokens = 1;      break;
            case 'q': silencioso = 1;       break;
            case 'h': ayuda(argv[0]);       return 0;
            default:  ayuda(argv[0]);       return 2;
        }
    }

    /* --- Fuente de entrada: texto (-e), archivo o entrada estándar ------- */
    YY_BUFFER_STATE buffer_texto = NULL;
    FILE *entrada = NULL;

    if (texto != NULL) {
        buffer_texto = yy_scan_string(texto);
    } else if (optind < argc && strcmp(argv[optind], "-") != 0) {
        entrada = fopen(argv[optind], "r");
        if (entrada == NULL) {
            perror(argv[optind]);
            return 2;
        }
        yyin = entrada;
    } else {
        yyin = stdin;
    }

    /* --- Base de datos --------------------------------------------------- */
    if (!solo_tokens) {
        if (limpiar) remove(ruta_bd);
        if (db_abrir(ruta_bd) != 0) return 2;
    }

    parser_iniciar();
    lexer_reiniciar_posicion();

    /* --- Análisis -------------------------------------------------------- */
    if (solo_tokens) {
        codigo = modo_tokens();
    } else {
        int rc = yyparse();               /* 0 = terminó; 1 = abortó (EOF) */
        if (rc != 0)
            estadisticas.rechazadas_sintaxis++;   /* sentencia incompleta */

        printf("\n================ RESUMEN ================\n");
        printf("Sentencias insertadas ..................... %d\n",
               estadisticas.insertadas);
        printf("Sentencias rechazadas (léxico/sintaxis) ... %d\n",
               estadisticas.rechazadas_sintaxis);
        printf("Sentencias rechazadas (semántica/BD) ...... %d\n",
               estadisticas.rechazadas_semantica);
        printf("Diagnósticos léxicos ...................... %d\n",
               estadisticas.errores_lexicos);
        printf("Diagnósticos sintácticos .................. %d\n",
               estadisticas.errores_sintacticos);

        if (!silencioso)
            db_mostrar_tablas();

        if (estadisticas.rechazadas_sintaxis || estadisticas.rechazadas_semantica
                || estadisticas.errores_lexicos)
            codigo = 1;
    }

    /* --- Liberación de recursos ------------------------------------------ */
    parser_liberar();
    if (!solo_tokens) db_cerrar();
    if (buffer_texto != NULL) yy_delete_buffer(buffer_texto);
    if (entrada != NULL) fclose(entrada);
    return codigo;
}
