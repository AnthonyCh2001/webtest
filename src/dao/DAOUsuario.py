import pymysql

class DAOUsuario:
    def connect(self):
        return pymysql.connect(host="localhost", user="root", password="", db="db_poo")

    def get_user_by_email(self, email):
        con = self.connect()
        cursor = con.cursor(pymysql.cursors.DictCursor)
        try:
            cursor.execute("SELECT * FROM usuarios WHERE email = %s AND activo = TRUE", (email,))
            return cursor.fetchone()
        except:
            return None
        finally:
            con.close()

    def obtener_usuarios_por_empresa(self, empresa_id):
        con = self.connect()
        cursor = con.cursor(pymysql.cursors.DictCursor)
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

    def obtener_usuarios_por_empresa(self, empresa_id):
        con = self.connect()
        cursor = con.cursor(pymysql.cursors.DictCursor)
        try:
            sql = """
                SELECT id, email, contrasena, activo
                FROM usuarios
                WHERE empresa_id = %s AND rol = 'usuario'
            """
            cursor.execute(sql, (empresa_id,))
            resultados = cursor.fetchall()
            print(f"[DAOUsuarios] Usuarios encontrados para empresa {empresa_id}: {resultados}")
            return resultados
        except Exception as e:
            print(f"[DAOUsuarios] Error al obtener usuarios por empresa: {e}")
            return []
        finally:
            con.close()

    
    def insertar_usuario(self, nombre, email, contrasena, empresa_id):
        con = self.connect()
        cursor = con.cursor()
        try:
            sql = """
                INSERT INTO usuarios (nombre, email, contrasena, rol, empresa_id, activo)
                VALUES (%s, %s, %s, 'usuario', %s, TRUE)
            """
            cursor.execute(sql, (nombre, email, contrasena, empresa_id))
            con.commit()
        except Exception as e:
            print(f"[DAOUsuario] Error al insertar usuario: {e}")
        finally:
            con.close()

    def obtener_usuario_por_id(self, usuario_id):
        con = self.connect()
        cursor = con.cursor(pymysql.cursors.DictCursor)
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


