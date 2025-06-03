import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
load_dotenv() 

class DAOEmpresas:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")

    def connect(self):
        return psycopg2.connect(self.db_url)

    def obtener_empresa_id_por_usuario(self, usuario_id):
        con = self.connect()
        cursor = con.cursor()
        try:
            sql = "SELECT empresa_id FROM usuarios WHERE id = %s"
            cursor.execute(sql, (usuario_id,))
            result = cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            print(f"[DAOEmpresas] Error al obtener empresa_id del usuario: {e}")
            return None
        finally:
            cursor.close()
            con.close()

    def obtener_nombre_empresa(self, empresa_id):
        con = self.connect()
        cursor = con.cursor()
        try:
            cursor.execute("SELECT nombre FROM empresas WHERE id = %s", (empresa_id,))
            result = cursor.fetchone()
            return result[0] if result else ""
        except Exception as e:
            print(f"[DAOEmpresas] Error al obtener nombre de empresa: {e}")
            return ""
        finally:
            cursor.close()
            con.close()

    def obtener_usuarios_por_empresa(self, empresa_id):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            cursor.execute("""
                SELECT id, nombre, email, contrasena
                FROM usuarios
                WHERE empresa_id = %s AND activo = TRUE AND rol = 'usuario'
            """, (empresa_id,))
            return cursor.fetchall()
        except Exception as e:
            print(f"[DAOEmpresas] Error al obtener usuarios por empresa: {e}")
            return []
        finally:
            cursor.close()
            con.close()

    def obtener_limite_usuarios(self, empresa_id):
        con = self.connect()
        cursor = con.cursor()
        try:
            cursor.execute("SELECT limite_usuarios FROM empresas WHERE id = %s", (empresa_id,))
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            print(f"[DAOEmpresas] Error al obtener límite de usuarios: {e}")
            return 0
        finally:
            cursor.close()
            con.close()

    def contar_usuarios_activos(self, empresa_id):
        con = self.connect()
        cursor = con.cursor()
        try:
            cursor.execute("""
                SELECT COUNT(*) FROM usuarios
                WHERE empresa_id = %s AND activo = TRUE AND rol = 'usuario'
            """, (empresa_id,))
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            print(f"[DAOEmpresas] Error al contar usuarios activos: {e}")
            return 0
        finally:
            cursor.close()
            con.close()

    def obtener_limite_reportes(self, empresa_id):
        con = self.connect()
        cursor = con.cursor()
        try:
            cursor.execute("SELECT limite_reportes FROM empresas WHERE id = %s", (empresa_id,))
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            print(f"[DAOEmpresas] Error al obtener límite de reportes: {e}")
            return 0
        finally:
            cursor.close()
            con.close()
