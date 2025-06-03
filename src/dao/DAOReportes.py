import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
load_dotenv() 

class DAOReportes:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")

    def connect(self):
        return psycopg2.connect(self.db_url)

    def insertar_reporte(self, data):
        con = self.connect()
        cursor = con.cursor()
        try:
            sql = """
                INSERT INTO reportes
                (nombre_pdf, nombre_candidato, es_comparativo, nombre_documento_origen, origen_documento, empresa_id, usuario_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                data['nombre_pdf'],
                data.get('nombre_candidato'),
                data['es_comparativo'],
                data['nombre_documento_origen'],
                data['origen_documento'],
                data['empresa_id'],
                data['usuario_id']
            ))
            con.commit()
            return True
        except Exception as e:
            print(f"[DAOReportes] Error al insertar: {e}")
            con.rollback()
            return False
        finally:
            cursor.close()
            con.close()

    def obtener_reportes_individuales_por_usuario(self, usuario_id):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            sql = """
                SELECT nombre_pdf
                FROM reportes
                WHERE usuario_id = %s AND es_comparativo = FALSE
            """
            cursor.execute(sql, (usuario_id,))
            return cursor.fetchall()
        except Exception as e:
            print(f"[DAOReportes] Error al obtener reportes individuales del usuario: {e}")
            return []
        finally:
            cursor.close()
            con.close()

    def actualizar_nombre_pdf(self, nombre_actual, nuevo_nombre):
        con = self.connect()
        cursor = con.cursor()
        try:
            sql = "UPDATE reportes SET nombre_pdf = %s WHERE nombre_pdf = %s"
            cursor.execute(sql, (nuevo_nombre, nombre_actual))
            con.commit()
            return True
        except Exception as e:
            print(f"[DAOReportes] Error al actualizar nombre_pdf: {e}")
            con.rollback()
            return False
        finally:
            cursor.close()
            con.close()

    def obtener_reportes_comparativos_por_usuario(self, usuario_id):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            sql = """
                SELECT nombre_pdf
                FROM reportes
                WHERE usuario_id = %s AND es_comparativo = TRUE
            """
            cursor.execute(sql, (usuario_id,))
            return cursor.fetchall()
        except Exception as e:
            print(f"[DAOReportes] Error al obtener reportes comparativos del usuario: {e}")
            return []
        finally:
            cursor.close()
            con.close()

    def obtener_reportes_comparativos_por_empresa(self, empresa_id):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            sql = """
                SELECT nombre_pdf
                FROM reportes
                WHERE empresa_id = %s AND es_comparativo = TRUE
            """
            cursor.execute(sql, (empresa_id,))
            return cursor.fetchall()
        except Exception as e:
            print(f"[DAOReportes] Error al obtener reportes comparativos de la empresa: {e}")
            return []
        finally:
            cursor.close()
            con.close()

    def eliminar_reporte_por_nombre_pdf(self, nombre_pdf):
        con = self.connect()
        cursor = con.cursor()
        try:
            sql = "DELETE FROM reportes WHERE nombre_pdf = %s"
            cursor.execute(sql, (nombre_pdf,))
            con.commit()
        except Exception as e:
            print(f"[DAOReportes] Error al eliminar reporte: {e}")
            con.rollback()
        finally:
            cursor
