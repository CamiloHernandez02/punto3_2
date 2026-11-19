/*
 * db.h
 * ---------------------------------------------------------------------------
 * Interfaz de la capa de base de datos (SQLite).
 * ---------------------------------------------------------------------------
 */
#ifndef DB_H
#define DB_H

#include "tipos.h"

/* Abre (o crea) el archivo de base de datos, crea las tres tablas
 * predefinidas si no existen y abre una transacción para toda la sesión.
 * Devuelve 0 si todo salió bien y -1 en caso contrario. */
int  db_abrir(const char *ruta);

/* Confirma la transacción y cierra la base de datos. */
void db_cerrar(void);

/* Valida semánticamente la sentencia contra el esquema real de la BD y, si es
 * correcta, ejecuta el INSERT.
 *   tabla    : nombre de la tabla indicado en la sentencia
 *   campos   : asignaciones campo = valor
 *   linea/columna : posición de la sentencia en el texto (para los mensajes)
 * Devuelve 0 si la fila se insertó y -1 si fue rechazada (el motivo se
 * imprime por stderr). */
int  db_insertar(const char *tabla, const ListaCampos *campos,
                 int linea, int columna);

/* Imprime el contenido de las tres tablas predefinidas. */
void db_mostrar_tablas(void);

#endif /* DB_H */
