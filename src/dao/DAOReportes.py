import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

class DAOReportes:
    def connect(self):
        # Conectar usando el DATABASE_URL de Render (configurado en las variables de entorno)
        return psycopg2.connect(os.getenv("DATABASE_URL"))

    def insertar_reporte(self, data):
        con = self.connect()
        cursor = con.cursor()

        try:
            sql = """
                INSERT INTO reportes
                (nombre_pdf, nombre_candidato, tipo_reporte, nombre_documento_origen, origen_documento, empresa_id, usuario_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                data['nombre_pdf'],
                data.get('nombre_candidato'),
                data['tipo_reporte'],  # 'individual', 'resumido' o 'comparativo'
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
            con.close()

    def obtener_reportes_individuales_por_usuario(self, usuario_id):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            sql = """
                SELECT nombre_pdf
                FROM reportes
                WHERE usuario_id = %s AND tipo_reporte = 'individual'
            """
            cursor.execute(sql, (usuario_id,))
            return cursor.fetchall()
        except Exception as e:
            print(f"[DAOReportes] Error al obtener reportes individuales del usuario: {e}")
            return []
        finally:
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
            con.close()

    def obtener_reportes_comparativos_por_usuario(self, usuario_id):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            sql = """
                SELECT nombre_pdf
                FROM reportes
                WHERE usuario_id = %s AND tipo_reporte = 'comparativo'
            """
            cursor.execute(sql, (usuario_id,))
            return cursor.fetchall()
        except Exception as e:
            print(f"[DAOReportes] Error al obtener reportes comparativos del usuario: {e}")
            return []
        finally:
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
            con.close()

    def contar_reportes_por_usuario(self, usuario_id):
        con = self.connect()
        cursor = con.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM reportes WHERE usuario_id = %s", (usuario_id,))
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            print(f"[DAOReportes] Error al contar reportes: {e}")
            return 0
        finally:
            con.close()

    def contar_reportes_por_empresa(self, empresa_id):
        con = self.connect()
        cursor = con.cursor()
        try:
            print(f"[DEBUG] Consultando reportes para empresa_id: {empresa_id}")  # Depuración
            cursor.execute("SELECT COUNT(*) FROM reportes WHERE empresa_id = %s", (empresa_id,))
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            print(f"[DAOReportes] Error al contar reportes por empresa: {e}")
            return 0
        finally:
            con.close()

    def eliminar_reportes_por_usuario(self, usuario_id):
        con = self.connect()
        cursor = con.cursor()
        try:
            cursor.execute("DELETE FROM reportes WHERE usuario_id = %s", (usuario_id,))
            con.commit()
        except Exception as e:
            print(f"[DAOReportes] Error al eliminar reportes del usuario: {e}")
        finally:
            con.close()

    def obtener_reportes_individuales_por_empresa(self, empresa_id):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            sql = """
                SELECT r.nombre_pdf, u.email as usuario_email
                FROM reportes r
                JOIN usuarios u ON r.usuario_id = u.id
                WHERE u.empresa_id = %s AND r.tipo_reporte = 'individual'
            """
            cursor.execute(sql, (empresa_id,))
            return cursor.fetchall()
        except Exception as e:
            print(f"[DAOReportes] Error al obtener reportes individuales por empresa: {e}")
            return []
        finally:
            cursor.close()
            con.close()

    def obtener_reportes_comparativos_por_empresa(self, empresa_id):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            sql = """
                SELECT r.nombre_pdf, u.email as usuario_email
                FROM reportes r
                JOIN usuarios u ON r.usuario_id = u.id
                WHERE u.empresa_id = %s AND r.tipo_reporte = 'comparativo'
            """
            cursor.execute(sql, (empresa_id,))
            return cursor.fetchall()
        except Exception as e:
            print(f"[DAOReportes] Error al obtener reportes comparativos por empresa: {e}")
            return []
        finally:
            cursor.close()
            con.close()

    def obtener_reportes_resumidos_por_usuario(self, usuario_id):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            sql = """
                SELECT nombre_pdf
                FROM reportes
                WHERE usuario_id = %s AND tipo_reporte = 'resumido'
            """
            cursor.execute(sql, (usuario_id,))
            return cursor.fetchall()
        except Exception as e:
            print(f"[DAOReportes] Error al obtener reportes resumidos del usuario: {e}")
            return []
        finally:
            con.close()

    def obtener_reportes_resumidos_por_empresa(self, empresa_id):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            sql = """
                SELECT r.nombre_pdf, u.email AS nombre_usuario
                FROM reportes r
                JOIN usuarios u ON r.usuario_id = u.id
                WHERE r.empresa_id = %s AND r.tipo_reporte = 'resumido'
            """
            cursor.execute(sql, (empresa_id,))
            return cursor.fetchall()
        except Exception as e:
            print(f"[DAOReportes] Error al obtener reportes resumidos por empresa: {e}")
            return []
        finally:
            cursor.close()
            con.close()

    def es_resumido(self, nombre_pdf):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            sql = "SELECT tipo_reporte FROM reportes WHERE nombre_pdf = %s"
            cursor.execute(sql, (nombre_pdf,))
            resultado = cursor.fetchone()
            if resultado:
                return resultado['tipo_reporte'] == 'psicotecnico'
            return False
        except Exception as e:
            print(f"[DAOReportes] Error al verificar si es resumido: {e}")
            return False
        finally:
            cursor.close()
            con.close()
