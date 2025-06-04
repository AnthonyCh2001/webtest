import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

class DAOUsuario:
    def connect(self):
        # Conectar usando DATABASE_URL de Render (configurado en las variables de entorno)
        return psycopg2.connect(os.getenv("DATABASE_URL"))

    def get_user_by_email(self, email):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            cursor.execute("SELECT * FROM usuarios WHERE email = %s AND activo = TRUE", (email,))
            return cursor.fetchone()
        except:
            return None
        finally:
            con.close()

    def obtener_usuarios_por_empresa(self, empresa_id):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            cursor.execute("SELECT id, email, contrasena FROM usuarios WHERE empresa_id = %s", (empresa_id,))
            return cursor.fetchall()
        except Exception as e:
            print(f"[DAOUsuarios] Error al obtener usuarios por empresa: {e}")
            return []
        finally:
            con.close()

    def obtener_limite(self, usuario_id):
        con = self.connect()
        cursor = con.cursor()
        try:
            sql = """
                SELECT e.limite_reportes
                FROM usuarios u
                JOIN empresas e ON u.empresa_id = e.id
                WHERE u.id = %s
            """
            cursor.execute(sql, (usuario_id,))
            resultado = cursor.fetchone()
            return resultado[0] if resultado else 0
        except Exception as e:
            print(f"[DAOUsuarios] Error al obtener límite: {e}")
            return 0
        finally:
            con.close()

    def obtener_empresa_id(self, usuario_id):
        con = self.connect()
        cursor = con.cursor()
        try:
            cursor.execute("SELECT empresa_id FROM usuarios WHERE id = %s", (usuario_id,))
            result = cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            print(f"[DAOUsuario] Error al obtener empresa_id: {e}")
            return None
        finally:
            con.close()


    def insertar_usuario(self, nombre, email, contrasena, empresa_id):
        con = self.connect()
        cursor = con.cursor()
        try:
            cursor.execute("""
                INSERT INTO usuarios (nombre, email, contrasena, empresa_id)
                VALUES (%s, %s, %s, %s)
            """, (nombre, email, contrasena, empresa_id))
            con.commit()
        except Exception as e:
            print(f"[DAOUsuarios] Error al insertar usuario: {e}")
            raise e
        finally:
            con.close()

    def obtener_usuario_por_id(self, usuario_id):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            cursor.execute("SELECT id, email, contrasena, activo FROM usuarios WHERE id = %s", (usuario_id,))
            return cursor.fetchone()
        except Exception as e:
            print(f"[DAOUsuario] Error al obtener usuario: {e}")
            return None
        finally:
            con.close()

    def actualizar_usuario(self, usuario_id, nueva_contrasena, activo):
        con = self.connect()
        cursor = con.cursor()
        try:
            cursor.execute("""
                UPDATE usuarios SET contrasena = %s, activo = %s WHERE id = %s
            """, (nueva_contrasena, activo, usuario_id))
            con.commit()
        except Exception as e:
            print(f"[DAOUsuario] Error al actualizar usuario: {e}")
        finally:
            con.close()

    def eliminar_usuario(self, usuario_id):
        con = self.connect()
        cursor = con.cursor()
        try:
            cursor.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
            con.commit()
        except Exception as e:
            print(f"[DAOUsuario] Error al eliminar usuario: {e}")
        finally:
            con.close()

    def obtener_admin_medio_por_empresa(self, empresa_id):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            cursor.execute("""
                SELECT * FROM usuarios
                WHERE empresa_id = %s AND rol = 'admin_medio' LIMIT 1
            """, (empresa_id,))
            return cursor.fetchone()
        except Exception as e:
            print(f"[DAOUsuarios] Error al obtener admin medio: {e}")
            return None
        finally:
            con.close()

    def actualizar_datos_admin_medio(self, usuario_id, nombre, email):
        con = self.connect()
        cursor = con.cursor()
        try:
            cursor.execute("""
                UPDATE usuarios SET nombre = %s, email = %s WHERE id = %s
            """, (nombre, email, usuario_id))
            con.commit()
        except Exception as e:
            print(f"[DAOUsuarios] Error al actualizar datos admin medio: {e}")
        finally:
            con.close()
