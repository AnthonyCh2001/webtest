import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

class DAOEmpresas:
    def connect(self):
        # Conectar usando el DATABASE_URL de Render (configurado en las variables de entorno)
        return psycopg2.connect(os.getenv("DATABASE_URL"))

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
            con.close()

    def obtener_color_porcentaje(self, porcentaje):
        if porcentaje == 0:
            return 'bg-success'
        elif porcentaje <= 60:
            return 'bg-success'
        elif porcentaje <= 85:
            return 'bg-warning'
        else:
            return 'bg-danger'

    def obtener_todas_las_empresas_con_datos(self, dao_reportes):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            cursor.execute("SELECT * FROM empresas")
            empresas = cursor.fetchall()

            empresas_con_datos = []
            for empresa in empresas:
                empresa_id = empresa['id']
                cantidad_usuarios = self.contar_usuarios_activos(empresa_id)
                cantidad_reportes = dao_reportes.contar_reportes_por_empresa(empresa_id)

                # Obtener nombre del admin_medio
                cursor.execute("""
                    SELECT nombre FROM usuarios 
                    WHERE empresa_id = %s AND rol = 'admin_medio' LIMIT 1
                """, (empresa_id,))
                admin = cursor.fetchone()
                nombre_admin = admin['nombre'] if admin else 'Sin asignar'

                usuarios_limite = empresa['limite_usuarios'] or 0
                reportes_limite = empresa['limite_reportes'] or 0

                porcentaje_usuarios = (cantidad_usuarios / usuarios_limite * 100) if usuarios_limite else 0
                porcentaje_reportes = (cantidad_reportes / reportes_limite * 100) if reportes_limite else 0

                empresas_con_datos.append({
                    'id': empresa_id,
                    'nombre': empresa['nombre'],
                    'plan': empresa['plan'],
                    'administrador': nombre_admin,
                    'usuarios_actuales': cantidad_usuarios,
                    'limite_usuarios': usuarios_limite,
                    'porcentaje_usuarios': round(porcentaje_usuarios, 1),
                    'color_usuarios': self.obtener_color_porcentaje(porcentaje_usuarios),
                    'reportes_generados': cantidad_reportes,
                    'limite_reportes': reportes_limite,
                    'porcentaje_reportes': round(porcentaje_reportes, 1),
                    'color_reportes': self.obtener_color_porcentaje(porcentaje_reportes)
                })

            return empresas_con_datos

        except Exception as e:
            print(f"[DAOEmpresas] Error al obtener datos de todas las empresas: {e}")
            return []
        finally:
            con.close()

    def crear_empresa(self, nombre, correo_admin, plan, limite_usuarios, limite_reportes):
        con = self.connect()
        cursor = con.cursor()
        try:
            cursor.execute("""
                INSERT INTO empresas (nombre, correo_admin, plan, limite_usuarios, limite_reportes)
                VALUES (%s, %s, %s, %s, %s)
            """, (nombre, correo_admin, plan, limite_usuarios, limite_reportes))
            con.commit()
        except Exception as e:
            print(f"[DAOEmpresas] Error al crear empresa: {e}")
        finally:
            con.close()

    def obtener_empresa_por_id(self, empresa_id):
        con = self.connect()
        cursor = con.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            cursor.execute("SELECT * FROM empresas WHERE id = %s", (empresa_id,))
            result = cursor.fetchone()
            return result
        except Exception as e:
            print(f"[DAOEmpresas] Error al obtener empresa por ID: {e}")
            return None
        finally:
            con.close()

    def actualizar_empresa(self, empresa):
        con = self.connect()
        cursor = con.cursor()
        try:
            cursor.execute("""
                UPDATE empresas SET nombre=%s, plan=%s, limite_usuarios=%s, limite_reportes=%s
                WHERE id=%s
            """, (empresa['nombre'], empresa['plan'], empresa['limite_usuarios'], empresa['limite_reportes'], empresa['id']))
            con.commit()
        except Exception as e:
            print(f"[DAOEmpresas] Error al actualizar empresa: {e}")
        finally:
            con.close()

    def eliminar_empresa(self, empresa_id):
        con = self.connect()
        cursor = con.cursor()
        try:
            cursor.execute("DELETE FROM empresas WHERE id = %s", (empresa_id,))
            con.commit()
        except Exception as e:
            print(f"[DAOEmpresas] Error al eliminar empresa: {e}")
        finally:
            con.close()

    def crear_empresa_y_retornar_id(self, nombre, plan, limite_usuarios, limite_reportes):
        con = self.connect()
        cursor = con.cursor()
        try:
            cursor.execute("""
                INSERT INTO empresas (nombre, plan, limite_usuarios, limite_reportes)
                VALUES (%s, %s, %s, %s)
            """, (nombre, plan, limite_usuarios, limite_reportes))
            con.commit()
            return cursor.lastrowid
        except Exception as e:
            print(f"[DAOEmpresas] Error al crear empresa: {e}")
            raise e
        finally:
            con.close()