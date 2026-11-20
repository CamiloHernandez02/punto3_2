# Makefile -- Punto 3.2 (Flex + Bison + SQLite)
#
# Objetivos:
#   make            compila el ejecutable build/sqlparser
#   make test       compila y ejecuta las pruebas automáticas
#   make demo       ejecuta el archivo de prueba completo con BD limpia
#   make tokens     muestra la tabla de tokens de una sentencia de ejemplo
#   make clean      borra los archivos generados
#
# Dependencias (Debian/Ubuntu):  sudo apt install flex bison libsqlite3-dev gcc make

CC      = gcc
CFLAGS  = -Wall -Wextra -O2 -std=gnu11 -Isrc -Ibuild
LDLIBS  = -lsqlite3
BUILD   = build
BIN     = $(BUILD)/sqlparser
OBJS    = $(BUILD)/main.o $(BUILD)/tipos.o $(BUILD)/db.o \
          $(BUILD)/parser.tab.o $(BUILD)/lex.yy.o

all: $(BIN)

$(BUILD):
	mkdir -p $(BUILD)

# --- Bison: genera parser.tab.c y parser.tab.h; --report=all escribe el
#     autómata LALR(1) completo (estados, conflictos) en parser.output.
$(BUILD)/parser.tab.c $(BUILD)/parser.tab.h: src/parser.y | $(BUILD)
	bison -Wall --report=all -d -o $(BUILD)/parser.tab.c $<

# --- Flex: genera lex.yy.c y lexer.h; -v muestra estadísticas del AFD.
$(BUILD)/lex.yy.c $(BUILD)/lexer.h: src/lexer.l $(BUILD)/parser.tab.h | $(BUILD)
	flex -v --header-file=$(BUILD)/lexer.h -o $(BUILD)/lex.yy.c $<

$(BUILD)/parser.tab.o: $(BUILD)/parser.tab.c
	$(CC) $(CFLAGS) -c $< -o $@

# El código generado por Flex produce avisos inofensivos con -Wextra.
$(BUILD)/lex.yy.o: $(BUILD)/lex.yy.c
	$(CC) $(CFLAGS) -Wno-unused-function -c $< -o $@

$(BUILD)/main.o: src/main.c $(BUILD)/lexer.h $(BUILD)/parser.tab.h
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/tipos.o: src/tipos.c src/tipos.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/db.o: src/db.c src/db.h src/tipos.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BIN): $(OBJS)
	$(CC) $(OBJS) -o $@ $(LDLIBS)

test: $(BIN)
	@python3 tests/verificar.py

demo: $(BIN)
	$(BIN) -l -d $(BUILD)/demo.db tests/entrada_prueba.txt

tokens: $(BIN)
	$(BIN) -t -e "insertar en tabla clientes valores: id = 1, nombre = 'Ana', activo = verdadero fin;"

clean:
	rm -rf $(BUILD)

.PHONY: all test demo tokens clean
