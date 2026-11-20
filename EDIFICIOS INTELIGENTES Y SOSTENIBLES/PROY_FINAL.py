import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import urllib.request
import json
import os
import random
import time
from openai import OpenAI
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

client = OpenAI(base_url="http://localhost:1235/v1", api_key="bionic-local")
MODELO_IA = "qwen2.5-coder-3b-instruct"
ARCHIVO_CONFIG = "novaterra_config.json"

PERFILES_DISPOSITIVOS = {
    "Estación de Trabajo / PC (50W - 150W)": (50.0, 150.0),
    "Carga Ligera / Router / Cargador (5W - 35W)": (5.0, 35.0),
    "Televisor / Ventilador (40W - 120W)": (40.0, 120.0),
    "Iluminación LED / Oficina (10W - 60W)": (10.0, 60.0),
    "Electrodoméstico Alta Potencia (700W - 1500W)": (700.0, 1500.0)
}

def cargar_configuracion():
    if os.path.exists(ARCHIVO_CONFIG):
        try:
            with open(ARCHIVO_CONFIG, "r", encoding="utf-8") as f:
                datos = json.load(f)
                if isinstance(datos, dict):
                    return datos.get("dispositivos", [])
                elif isinstance(datos, list):
                    return datos
        except:
            pass
    return []

def guardar_configuracion(dispositivos):
    try:
        datos = {
            "dispositivos": dispositivos
        }
        with open(ARCHIVO_CONFIG, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=4, ensure_ascii=False)
    except Exception as e:
        messagebox.showerror("Error al Guardar", f"No se pudo guardar la configuración: {e}")

class MonitoreoKPIs:
    def __init__(self):
        self.dispositivos = cargar_configuracion()
        self.lecturas = 0
        self.errores_ia = 0
        self.evaluaciones_ia = 0
        self.interrupciones = 0
        self.intentos_emparejamiento = 0
        self.fallos_emparejamiento = 0
        self.ultimo_tiempo_diag = 0.0
        self.total_tiempo_diag = 0.0
        self.total_diagnosticos = 0

    def registrar_emparejamiento(self, exito):
        self.intentos_emparejamiento += 1
        if not exito:
            self.fallos_emparejamiento += 1

    def registrar_interrupcion(self):
        self.lecturas += 1
        self.interrupciones += 1

    def registrar_evaluacion(self, math_res, ai_res):
        self.lecturas += 1
        self.evaluaciones_ia += 1
        if math_res != ai_res:
            self.errores_ia += 1

    def registrar_tiempo_diagnostico(self, segundos):
        self.ultimo_tiempo_diag = segundos
        self.total_tiempo_diag += segundos
        self.total_diagnosticos += 1

def entrenamiento(min_w, max_w):
    mensajes = [
        {
            "role": "system",
            "content": f"Regla: Responde 'NORMAL' si el consumo está entre {min_w} y {max_w} inclusive. Responde 'ANOMALIA' si es < {min_w} o > {max_w}. Responde EXACTAMENTE CON UNA PALABRA."
        }
    ]
    limite_sup = max(max_w * 2.0, 300.0)
    for _ in range(12):
        if random.random() < 0.5:
            val = round(random.uniform(min_w, max_w), 2)
        else:
            if random.random() < 0.5 and min_w > 1.0:
                val = round(random.uniform(0.0, max(0.1, min_w - 0.5)), 2)
            else:
                val = round(random.uniform(max_w + 0.5, limite_sup), 2)
        res = "NORMAL" if min_w <= val <= max_w else "ANOMALIA"
        mensajes.append({"role": "user", "content": f"Consumo: {val}W"})
        mensajes.append({"role": "assistant", "content": res})
    return mensajes

def consultar_ia(consumo, min_w, max_w):
    mensajes = entrenamiento(min_w, max_w)
    mensajes.append({"role": "user", "content": f"Consumo: {consumo}W"})
    try:
        resp = client.chat.completions.create(model=MODELO_IA, messages=mensajes, temperature=0, max_tokens=10)
        texto = resp.choices[0].message.content.strip().upper()
        return ("ANOMALIA" if "ANOMAL" in texto else "NORMAL", None)
    except Exception as e:
        return ("ERROR", str(e))

def obtener_datos_shelly(ip):
    try:
        url = f"http://{ip}/rpc/Switch.GetStatus?id=0"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=4) as respuesta:
            if respuesta.status == 200:
                datos = json.loads(respuesta.read().decode("utf-8"))
                potencia = float(datos.get("apower", 0.0))
                voltaje = float(datos.get("voltage", 0.0))
                return potencia, voltaje, None
            else:
                return 0.0, 0.0, f"HTTP {respuesta.status}"
    except Exception as e:
        return 0.0, 0.0, str(e)

class InterfazBionic:
    def __init__(self, root):
        self.root = root
        self.root.title("Novaterra - Monitor Energético IA")
        self.root.geometry("950x800")
        self.root.configure(bg="#0A2540")
        self.kpis = MonitoreoKPIs()
        self.estados_red = {}
        self.monitoreando = False
        self.inicio_diagnostico = 0.0

        self.style = ttk.Style()
        self.style.theme_use('clam')

        self.style.configure("TFrame", background="#173A5E")
        self.style.configure("TLabel", background="#173A5E", font=("Segoe UI", 10), foreground="#FFFFFF")
        self.style.configure("TButton", font=("Segoe UI", 9, "bold"), padding=6)

        self.style.configure("TLabelframe", background="#173A5E", foreground="#FFD700", bordercolor="#0A2540", borderwidth=2)
        self.style.configure("TLabelframe.Label", background="#173A5E", foreground="#FFD700", font=("Segoe UI", 10, "bold"))

        self.style.configure("TNotebook", background="#0A2540", borderwidth=0)
        self.style.configure("TNotebook.Tab", background="#0B1B32", foreground="#FFFFFF", padding=[20, 8], font=("Segoe UI", 10, "bold"))
        self.style.map("TNotebook.Tab", background=[("selected", "#000000")], foreground=[("selected", "#FFD700")])

        self.style.configure("Add.TButton", background="#000000", foreground="#FFD700")
        self.style.map("Add.TButton", background=[("active", "#111111")])
        self.style.configure("Start.TButton", background="#FFD700", foreground="#000000")
        self.style.map("Start.TButton", background=[("active", "#CCAC00")])

        header_frame = tk.Frame(self.root, bg="#0A2540", pady=12)
        header_frame.pack(fill='x')
        tk.Label(header_frame, text="NOVATERRA", font=("Segoe UI Black", 24), bg="#0A2540", fg="#FFD700").pack()
        tk.Label(header_frame, text="Sistema de Monitoreo Bionic IA con Shelly Real", font=("Segoe UI", 11), bg="#0A2540", fg="#FFFFFF").pack()

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(expand=True, fill='both', padx=10, pady=(0, 10))

        self.tab_monitor = ttk.Frame(self.notebook)
        self.tab_prueba = ttk.Frame(self.notebook)
        self.tab_kpis_tec = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_monitor, text="MONITOREO")
        self.notebook.add(self.tab_prueba, text="PRUEBAS AISLADAS")
        self.notebook.add(self.tab_kpis_tec, text="KPIs TÉCNICOS")

        self.setup_monitor()
        self.setup_prueba()
        self.setup_kpis_tecnicos()
        self.root.after(400, self.buscar_dispositivos_al_iniciar)

    def setup_monitor(self):
        sec_agregar = ttk.LabelFrame(self.tab_monitor, text=" AGREGAR DISPOSITIVO NUEVO ", padding=10)
        sec_agregar.pack(pady=(10, 6), padx=15, fill='x')

        ttk.Label(sec_agregar, text="Nombre del Dispositivo:", font=("Segoe UI", 10, "bold")).pack(side='left')
        self.entry_disp = ttk.Entry(sec_agregar, font=("Segoe UI", 10), width=18)
        self.entry_disp.pack(side='left', padx=(5, 15))

        ttk.Label(sec_agregar, text="Dirección IP:", font=("Segoe UI", 10, "bold")).pack(side='left')
        self.entry_ip = ttk.Entry(sec_agregar, font=("Segoe UI", 10), width=16)
        self.entry_ip.pack(side='left', padx=(5, 15))

        ttk.Button(sec_agregar, text="Guardar Dispositivo", style="Add.TButton", command=self.agregar_dispositivo_nuevo).pack(side='left', padx=5)

        sec_conectados = ttk.LabelFrame(self.tab_monitor, text=" DISPOSITIVOS CONECTADOS ", padding=10)
        sec_conectados.pack(pady=6, padx=15, fill='x')

        self.lista_disp = tk.Listbox(
            sec_conectados,
            height=4,
            font=("Consolas", 10),
            bg="#000000",
            fg="#FFD700",
            selectbackground="#00AAFF",
            selectforeground="#000000",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#0A2540"
        )
        self.lista_disp.pack(fill='x', pady=(0, 8))
        self.lista_disp.bind("<<ListboxSelect>>", self.al_seleccionar_dispositivo)

        fila_tipo = ttk.Frame(sec_conectados)
        fila_tipo.pack(fill='x', pady=(0, 8))

        ttk.Label(fila_tipo, text="Tipo de Dispositivo:", font=("Segoe UI", 10, "bold")).pack(side='left')
        self.combo_tipo_mon = ttk.Combobox(
            fila_tipo,
            values=list(PERFILES_DISPOSITIVOS.keys()),
            state="readonly",
            font=("Segoe UI", 9),
            width=42
        )
        self.combo_tipo_mon.current(0)
        self.combo_tipo_mon.pack(side='left', padx=8)
        self.combo_tipo_mon.bind("<<ComboboxSelected>>", self.cambiar_tipo_dispositivo)

        self.lbl_rango_mon = ttk.Label(fila_tipo, text="Rango Normal: 50.0W - 150.0W", font=("Segoe UI", 10, "bold"), foreground="#00AAFF")
        self.lbl_rango_mon.pack(side='left', padx=10)

        fila_acciones = ttk.Frame(sec_conectados)
        fila_acciones.pack(fill='x')

        ttk.Button(fila_acciones, text="Cambiar Nombre", style="Add.TButton", command=self.cambiar_nombre_dispositivo).pack(side='left', padx=(0, 8))
        ttk.Button(fila_acciones, text="Eliminar Dispositivo", style="Add.TButton", command=self.eliminar_dispositivo).pack(side='left', padx=(0, 8))

        self.btn_diagnostico = ttk.Button(fila_acciones, text="Iniciar Diagnóstico", style="Start.TButton", command=self.iniciar_diagnostico)
        self.btn_diagnostico.pack(side='right')

        self.consola = tk.Text(
            self.tab_monitor,
            state='disabled',
            height=13,
            font=("Consolas", 10),
            bg="#000000",
            fg="#FFFFFF",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#0A2540"
        )
        self.consola.pack(pady=(6, 12), padx=15, fill='both', expand=True)

        self.consola.tag_config("acierto", foreground="#00AAFF", font=("Consolas", 10, "bold"))
        self.consola.tag_config("fallo", foreground="#FFD700", font=("Consolas", 10, "bold"))
        self.consola.tag_config("error", foreground="#FFD700", font=("Consolas", 10, "bold"))
        self.consola.tag_config("info", foreground="#FFFFFF", font=("Consolas", 10, "bold"))
        self.consola.tag_config("sep", foreground="#173A5E")
        self.consola.tag_config("tit", foreground="#FFD700", font=("Consolas", 10, "bold"))

    def obtener_indice_seleccionado(self):
        seleccion = self.lista_disp.curselection()
        if seleccion:
            return seleccion[0]
        if len(self.kpis.dispositivos) == 1:
            self.lista_disp.selection_set(0)
            return 0
        return None

    def actualizar_lista_visual(self):
        sel_actual = self.lista_disp.curselection()
        indice_previo = sel_actual[0] if sel_actual else None

        self.lista_disp.delete(0, 'end')
        for dev in self.kpis.dispositivos:
            nombre = dev["nombre"]
            ip = dev["ip"]
            tipo = dev.get("tipo", list(PERFILES_DISPOSITIVOS.keys())[0])
            estado = self.estados_red.get(ip, "Verificando...")
            self.lista_disp.insert('end', f" • {nombre} | IP: {ip} | {tipo} | [{estado}]")

        if self.kpis.dispositivos:
            idx = indice_previo if (indice_previo is not None and indice_previo < len(self.kpis.dispositivos)) else 0
            self.lista_disp.selection_set(idx)
            tipo_sel = self.kpis.dispositivos[idx].get("tipo", list(PERFILES_DISPOSITIVOS.keys())[0])
            if tipo_sel in PERFILES_DISPOSITIVOS:
                self.combo_tipo_mon.set(tipo_sel)
                min_w, max_w = PERFILES_DISPOSITIVOS[tipo_sel]
                self.lbl_rango_mon.config(text=f"Rango Normal: {min_w}W - {max_w}W")

    def al_seleccionar_dispositivo(self, event=None):
        idx = self.obtener_indice_seleccionado()
        if idx is not None and idx < len(self.kpis.dispositivos):
            tipo = self.kpis.dispositivos[idx].get("tipo", list(PERFILES_DISPOSITIVOS.keys())[0])
            if tipo in PERFILES_DISPOSITIVOS:
                self.combo_tipo_mon.set(tipo)
                min_w, max_w = PERFILES_DISPOSITIVOS[tipo]
                self.lbl_rango_mon.config(text=f"Rango Normal: {min_w}W - {max_w}W")

    def cambiar_tipo_dispositivo(self, event=None):
        tipo_nuevo = self.combo_tipo_mon.get()
        min_w, max_w = PERFILES_DISPOSITIVOS[tipo_nuevo]
        self.lbl_rango_mon.config(text=f"Rango Normal: {min_w}W - {max_w}W")

        idx = self.obtener_indice_seleccionado()
        if idx is not None and idx < len(self.kpis.dispositivos):
            self.kpis.dispositivos[idx]["tipo"] = tipo_nuevo
            guardar_configuracion(self.kpis.dispositivos)
            self.actualizar_lista_visual()
            nombre = self.kpis.dispositivos[idx]["nombre"]
            self.escribir_consola(f"> Rango de '{nombre}' actualizado a {tipo_nuevo}.\n", "acierto")

    def dialog_ip_no_encontrada(self, nombre, ip):
        decision = {"accion": "cancelar", "nueva_ip": ""}
        ventana = tk.Toplevel(self.root)
        ventana.title("IP No Encontrada")
        ventana.geometry("450x210")
        ventana.configure(bg="#0A2540")
        ventana.resizable(False, False)
        ventana.transient(self.root)
        ventana.grab_set()

        tk.Label(
            ventana,
            text="DISPOSITIVO NO ENCONTRADO",
            font=("Segoe UI", 12, "bold"),
            bg="#0A2540",
            fg="#FFD700"
        ).pack(pady=(15, 8))

        tk.Label(
            ventana,
            text=f"No se encontró la IP ({ip}) del dispositivo '{nombre}'.\n¿Qué deseas hacer con este dispositivo?",
            font=("Segoe UI", 10),
            bg="#0A2540",
            fg="#FFFFFF",
            justify="center"
        ).pack(pady=(0, 18), padx=15)

        frame_btns = tk.Frame(ventana, bg="#0A2540")
        frame_btns.pack(pady=5)

        def elegir_cambiar():
            nueva = simpledialog.askstring(
                "Cambiar Dirección IP",
                f"Ingresa la nueva dirección IP para '{nombre}':",
                parent=ventana
            )
            if nueva and nueva.strip():
                decision["accion"] = "cambiar"
                decision["nueva_ip"] = nueva.strip()
                ventana.destroy()

        def elegir_eliminar():
            decision["accion"] = "eliminar"
            ventana.destroy()

        tk.Button(
            frame_btns,
            text="Cambiar Dirección IP",
            bg="#FFD700",
            fg="#000000",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=5,
            command=elegir_cambiar
        ).pack(side='left', padx=8)

        tk.Button(
            frame_btns,
            text="Eliminar Dispositivo",
            bg="#000000",
            fg="#FFD700",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=5,
            command=elegir_eliminar
        ).pack(side='left', padx=8)

        self.root.wait_window(ventana)
        return decision

    def buscar_dispositivos_al_iniciar(self):
        if not self.kpis.dispositivos:
            self.escribir_consola("> No hay dispositivos guardados. Añade uno en 'AGREGAR DISPOSITIVO NUEVO'.\n", "info")
            return

        self.actualizar_lista_visual()
        self.escribir_consola("> Buscando dispositivos guardados en la red...\n", "tit")

        i = 0
        while i < len(self.kpis.dispositivos):
            dev = self.kpis.dispositivos[i]
            nombre = dev["nombre"]
            ip = dev["ip"]
            _, _, error = obtener_datos_shelly(ip)

            if not error:
                self.kpis.registrar_emparejamiento(True)
                self.estados_red[ip] = "CONECTADO"
                self.escribir_consola(f"> Dispositivo '{nombre}' encontrado en {ip}.\n", "acierto")
                i += 1
            else:
                self.kpis.registrar_emparejamiento(False)
                self.estados_red[ip] = "SIN RESPUESTA"
                self.actualizar_lista_visual()
                self.actualizar_kpis_tecnicos()
                res = self.dialog_ip_no_encontrada(nombre, ip)
                if res["accion"] == "cambiar":
                    nueva_ip = res["nueva_ip"]
                    self.kpis.dispositivos[i]["ip"] = nueva_ip
                    guardar_configuracion(self.kpis.dispositivos)
                    self.escribir_consola(f"> IP de '{nombre}' cambiada a {nueva_ip}. Verificando...\n", "acierto")
                elif res["accion"] == "eliminar":
                    self.kpis.dispositivos.pop(i)
                    guardar_configuracion(self.kpis.dispositivos)
                    self.escribir_consola(f"> Dispositivo '{nombre}' eliminado.\n", "fallo")
                else:
                    self.escribir_consola(f"> Dispositivo '{nombre}' ({ip}) sin conexión.\n", "error")
                    i += 1

        self.actualizar_lista_visual()
        self.actualizar_kpis_tecnicos()

    def agregar_dispositivo_nuevo(self):
        nombre = self.entry_disp.get().strip()
        ip = self.entry_ip.get().strip()
        if not nombre or not ip:
            messagebox.showwarning("Datos incompletos", "Ingresa el nombre y la dirección IP del dispositivo.")
            return

        tipo_defecto = self.combo_tipo_mon.get()

        while True:
            _, _, error = obtener_datos_shelly(ip)
            if not error:
                self.kpis.registrar_emparejamiento(True)
                self.estados_red[ip] = "CONECTADO"
                actualizado = False
                for dev in self.kpis.dispositivos:
                    if dev["nombre"].lower() == nombre.lower():
                        dev["ip"] = ip
                        actualizado = True
                        break
                if not actualizado:
                    self.kpis.dispositivos.append({"nombre": nombre, "ip": ip, "tipo": tipo_defecto})
                guardar_configuracion(self.kpis.dispositivos)
                self.entry_disp.delete(0, 'end')
                self.entry_ip.delete(0, 'end')
                self.actualizar_lista_visual()
                self.actualizar_kpis_tecnicos()
                self.escribir_consola(f"> Dispositivo '{nombre}' conectado y guardado en {ip}.\n", "acierto")
                break
            else:
                self.kpis.registrar_emparejamiento(False)
                self.actualizar_kpis_tecnicos()
                res = self.dialog_ip_no_encontrada(nombre, ip)
                if res["accion"] == "cambiar":
                    ip = res["nueva_ip"]
                    self.entry_ip.delete(0, 'end')
                    self.entry_ip.insert(0, ip)
                elif res["accion"] == "eliminar":
                    self.entry_disp.delete(0, 'end')
                    self.entry_ip.delete(0, 'end')
                    self.escribir_consola(f"> Registro de '{nombre}' descartado.\n", "fallo")
                    break
                else:
                    break

    def cambiar_nombre_dispositivo(self):
        idx = self.obtener_indice_seleccionado()
        if idx is None or idx >= len(self.kpis.dispositivos):
            messagebox.showinfo("Seleccionar", "Selecciona un dispositivo en la lista de Dispositivos Conectados.")
            return

        nombre_actual = self.kpis.dispositivos[idx]["nombre"]
        nuevo_nombre = simpledialog.askstring(
            "Cambiar Nombre",
            f"Ingresa el nuevo nombre para '{nombre_actual}':",
            initialvalue=nombre_actual,
            parent=self.root
        )
        if nuevo_nombre and nuevo_nombre.strip():
            self.kpis.dispositivos[idx]["nombre"] = nuevo_nombre.strip()
            guardar_configuracion(self.kpis.dispositivos)
            self.actualizar_lista_visual()
            self.escribir_consola(f"> Dispositivo renombrado de '{nombre_actual}' a '{nuevo_nombre.strip()}'.\n", "acierto")

    def eliminar_dispositivo(self):
        idx = self.obtener_indice_seleccionado()
        if idx is None or idx >= len(self.kpis.dispositivos):
            messagebox.showinfo("Seleccionar", "Selecciona un dispositivo en la lista de Dispositivos Conectados.")
            return

        eliminado = self.kpis.dispositivos.pop(idx)
        guardar_configuracion(self.kpis.dispositivos)
        self.actualizar_lista_visual()
        self.actualizar_kpis_tecnicos()
        self.escribir_consola(f"> Dispositivo '{eliminado['nombre']}' eliminado.\n", "fallo")

    def escribir_consola(self, texto, tag="normal"):
        self.consola.config(state='normal')
        self.consola.insert('end', texto, tag)
        self.consola.see('end')
        self.consola.config(state='disabled')

    def log_tarjeta(self, disp, consumo, voltaje, min_w, max_w, math_res, ai_res, error_msg, match):
        self.escribir_consola(f"┌{'─'*62}┐\n", "sep")
        self.escribir_consola(f"│ DISPOSITIVO  : ", "normal")
        self.escribir_consola(f"{disp:<46}│\n", "info")
        self.escribir_consola(f"│ LECTURA      : ", "normal")
        lectura_txt = f"{consumo} W  (Voltaje: {voltaje} V)"
        self.escribir_consola(f"{lectura_txt:<46}│\n", "info")
        self.escribir_consola(f"│ RANGO NORMAL : ", "normal")
        rango_txt = f"{min_w} W - {max_w} W"
        self.escribir_consola(f"{rango_txt:<46}│\n", "normal")

        if error_msg:
            self.escribir_consola(f"│ ESTADO       : ", "normal")
            self.escribir_consola(f"{error_msg[:45]:<46}│\n", "error")
        else:
            comparacion = f"{ai_res} (IA) vs {math_res} (REAL)"
            self.escribir_consola(f"│ EVALUACIÓN   : ", "normal")
            self.escribir_consola(f"{comparacion:<46}│\n", "normal")
            self.escribir_consola(f"│ PRECISIÓN IA : ", "normal")
            tag = "acierto" if match == "[ACIERTO]" else "fallo"
            self.escribir_consola(f"{match:<46}│\n", tag)

        self.escribir_consola(f"└{'─'*62}┘\n", "sep")

    def iniciar_diagnostico(self):
        if not self.kpis.dispositivos:
            messagebox.showwarning("Sin Dispositivos", "Agrega al menos un dispositivo nuevo antes de iniciar el diagnóstico.")
            return
        if self.monitoreando:
            return

        self.monitoreando = True
        self.inicio_diagnostico = time.perf_counter()
        self.btn_diagnostico.config(text="Diagnosticando...", state='disabled')
        self.escribir_consola("\n" + "="*64 + "\n", "sep")
        self.escribir_consola(" INICIANDO DIAGNÓSTICO CON BIONIC IA\n", "tit")
        self.escribir_consola("="*64 + "\n\n", "sep")
        self.procesar_dispositivo(0)

    def procesar_dispositivo(self, indice):
        if indice >= len(self.kpis.dispositivos):
            duracion = time.perf_counter() - self.inicio_diagnostico
            self.kpis.registrar_tiempo_diagnostico(duracion)
            self.monitoreando = False
            self.btn_diagnostico.config(text="Iniciar Diagnóstico", state='normal')
            self.actualizar_lista_visual()
            self.actualizar_kpis_tecnicos()
            self.escribir_consola("\n" + "="*64 + "\n", "sep")
            self.escribir_consola(f" DIAGNÓSTICO FINALIZADO ({duracion:.2f} s)\n", "tit")
            self.escribir_consola("="*64 + "\n\n", "sep")
            return

        dev = self.kpis.dispositivos[indice]
        disp = dev["nombre"]
        ip = dev["ip"]
        tipo = dev.get("tipo", list(PERFILES_DISPOSITIVOS.keys())[0])
        min_w, max_w = PERFILES_DISPOSITIVOS.get(tipo, (50.0, 150.0))

        consumo, voltaje, error_shelly = obtener_datos_shelly(ip)

        if error_shelly:
            self.kpis.registrar_emparejamiento(False)
            self.estados_red[ip] = "SIN RESPUESTA"
            self.actualizar_kpis_tecnicos()
            res = self.dialog_ip_no_encontrada(disp, ip)
            if res["accion"] == "cambiar":
                ip = res["nueva_ip"]
                self.kpis.dispositivos[indice]["ip"] = ip
                guardar_configuracion(self.kpis.dispositivos)
                consumo, voltaje, error_shelly = obtener_datos_shelly(ip)
            elif res["accion"] == "eliminar":
                self.kpis.dispositivos.pop(indice)
                guardar_configuracion(self.kpis.dispositivos)
                self.actualizar_lista_visual()
                self.escribir_consola(f"> Dispositivo '{disp}' eliminado durante diagnóstico.\n", "fallo")
                self.procesar_dispositivo(indice)
                return

        if error_shelly:
            self.estados_red[ip] = "SIN RESPUESTA"
            self.kpis.registrar_interrupcion()
            self.log_tarjeta(disp, 0.0, 0.0, min_w, max_w, "NORMAL", "ERROR", f"SHELLY: {error_shelly}", "[ERROR]")
        else:
            self.estados_red[ip] = "CONECTADO"
            math_res = "NORMAL" if min_w <= consumo <= max_w else "ANOMALIA"
            ai_res, error_ia = consultar_ia(consumo, min_w, max_w)

            if error_ia:
                self.kpis.registrar_interrupcion()
                self.log_tarjeta(disp, consumo, voltaje, min_w, max_w, math_res, "ERROR", f"IA: {error_ia}", "[ERROR]")
            else:
                self.kpis.registrar_evaluacion(math_res, ai_res)
                match = "[ACIERTO]" if math_res == ai_res else "[FALLO]"
                self.log_tarjeta(disp, consumo, voltaje, min_w, max_w, math_res, ai_res, None, match)

        self.actualizar_kpis_tecnicos()
        if indice + 1 < len(self.kpis.dispositivos):
            self.root.after(1000, lambda: self.procesar_dispositivo(indice + 1))
        else:
            self.procesar_dispositivo(indice + 1)

    def setup_prueba(self):
        frame_tipo = ttk.Frame(self.tab_prueba)
        frame_tipo.pack(pady=(35, 15))

        ttk.Label(frame_tipo, text="Tipo de Dispositivo:", font=("Segoe UI", 11, "bold")).pack(side='left')
        self.combo_tipo_prueba = ttk.Combobox(
            frame_tipo,
            values=list(PERFILES_DISPOSITIVOS.keys()),
            state="readonly",
            font=("Segoe UI", 10),
            width=42
        )
        self.combo_tipo_prueba.current(0)
        self.combo_tipo_prueba.pack(side='left', padx=10)
        self.combo_tipo_prueba.bind("<<ComboboxSelected>>", self.actualizar_rango_prueba)

        self.lbl_rango_prueba = ttk.Label(self.tab_prueba, text="Rango Normal Delimitado: 50.0 W - 150.0 W", font=("Segoe UI", 11, "bold"), foreground="#00AAFF")
        self.lbl_rango_prueba.pack(pady=5)

        frame = ttk.Frame(self.tab_prueba)
        frame.pack(pady=20)
        ttk.Label(frame, text="Inyectar Consumo (W):", font=("Segoe UI", 12, "bold")).pack(side='left')
        self.entry_prueba = ttk.Entry(frame, font=("Segoe UI", 12), width=15)
        self.entry_prueba.pack(side='left', padx=10)
        ttk.Button(frame, text="Ejecutar Prueba", style="Add.TButton", command=self.ejecutar_prueba).pack(side='left')

        self.res_prueba = ttk.Label(self.tab_prueba, text="", font=("Segoe UI", 13), justify="center")
        self.res_prueba.pack(pady=30)

    def actualizar_rango_prueba(self, event=None):
        tipo = self.combo_tipo_prueba.get()
        min_w, max_w = PERFILES_DISPOSITIVOS[tipo]
        self.lbl_rango_prueba.config(text=f"Rango Normal Delimitado: {min_w} W - {max_w} W")

    def ejecutar_prueba(self):
        try:
            consumo = float(self.entry_prueba.get())
        except:
            messagebox.showerror("Error de Formato", "Por favor, ingresa un valor numérico válido.")
            return

        tipo = self.combo_tipo_prueba.get()
        min_w, max_w = PERFILES_DISPOSITIVOS[tipo]
        math_res = "NORMAL" if min_w <= consumo <= max_w else "ANOMALIA"
        self.res_prueba.config(text="Entrenando y contactando servidor Bionic local...", foreground="#00AAFF")
        self.root.update()

        ai_res, error = consultar_ia(consumo, min_w, max_w)
        if error:
            self.res_prueba.config(text=f"ERROR DE CONEXIÓN:\n{error}", foreground="#FFD700")
        else:
            match = "ESTADO: LA IA ACERTÓ" if math_res == ai_res else "ESTADO: LA IA FALLÓ"
            color = "#00AAFF" if math_res == ai_res else "#FFD700"
            texto = (
                f"PERFIL: {tipo}\n"
                f"VALOR EVALUADO: {consumo} W  (Rango Normal: {min_w}W - {max_w}W)\n\n"
                f"Regla Matemática Estricta: {math_res}\n"
                f"Respuesta Modelo IA: {ai_res}\n\n"
                f"{match}"
            )
            self.res_prueba.config(text=texto, foreground=color)

    def setup_kpis_tecnicos(self):
        frame_stats = ttk.Frame(self.tab_kpis_tec)
        frame_stats.pack(side='left', fill='y', padx=25, pady=25)
        self.lbl_kpis_tec = ttk.Label(frame_stats, text="", font=("Segoe UI", 11), justify="left")
        self.lbl_kpis_tec.pack(anchor="nw")

        frame_graph = ttk.Frame(self.tab_kpis_tec)
        frame_graph.pack(side='right', fill='both', expand=True, padx=20, pady=20)

        self.fig_tec, self.ax_tec = plt.subplots(figsize=(5, 4))
        self.fig_tec.patch.set_facecolor('#173A5E')
        self.ax_tec.set_facecolor('#000000')
        self.canvas_tec = FigureCanvasTkAgg(self.fig_tec, master=frame_graph)
        self.canvas_tec.get_tk_widget().pack(fill='both', expand=True)

        self.actualizar_kpis_tecnicos()

    def actualizar_kpis_tecnicos(self):
        t_emp = (self.kpis.fallos_emparejamiento / self.kpis.intentos_emparejamiento * 100.0) if self.kpis.intentos_emparejamiento else 0.0
        t_ia = (self.kpis.errores_ia / self.kpis.evaluaciones_ia * 100.0) if self.kpis.evaluaciones_ia else 0.0
        t_int = (self.kpis.interrupciones / self.kpis.lecturas * 100.0) if self.kpis.lecturas else 0.0
        prom_diag = (self.kpis.total_tiempo_diag / self.kpis.total_diagnosticos) if self.kpis.total_diagnosticos else 0.0

        texto = (
            f"KPIs (A NIVEL TÉCNICO)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"1. Tiempo de Diagnóstico:\n"
            f"   {self.kpis.ultimo_tiempo_diag:.2f} s (Prom: {prom_diag:.2f} s)\n\n"
            f"2. Fallos de Emparejamiento:\n"
            f"   {self.kpis.fallos_emparejamiento} ({t_emp:.1f}%)\n\n"
            f"3. Lecturas Procesadas: {self.kpis.lecturas}\n\n"
            f"4. Errores de la IA:\n"
            f"   {self.kpis.errores_ia} ({t_ia:.1f}%)\n\n"
            f"5. Tasa Interrupciones de Red:\n"
            f"   {t_int:.1f}% ({self.kpis.interrupciones})"
        )
        self.lbl_kpis_tec.config(text=texto, foreground="#FFD700")

        self.ax_tec.clear()
        categorias = ['Tiempo\n(s)', 'Fallos\nEmparej.', 'Lecturas', 'Errores\nIA', 'Interrup.\nRed']
        valores = [
            round(self.kpis.ultimo_tiempo_diag, 2),
            self.kpis.fallos_emparejamiento,
            self.kpis.lecturas,
            self.kpis.errores_ia,
            self.kpis.interrupciones
        ]
        colores = ['#00AAFF', '#FFD700', '#FFFFFF', '#1E90FF', '#4A6B82']

        self.ax_tec.bar(categorias, valores, color=colores, edgecolor='#000000', linewidth=1)
        self.ax_tec.set_ylim(bottom=0)
        self.ax_tec.set_title("KPIs a Nivel Técnico", fontdict={'fontsize': 11, 'fontweight': 'bold', 'color': '#FFFFFF'})
        self.ax_tec.tick_params(colors='#FFFFFF')

        for sp in self.ax_tec.spines.values():
            sp.set_color('#173A5E')

        self.fig_tec.tight_layout()
        self.canvas_tec.draw()

if __name__ == "__main__":
    root = tk.Tk()
    app = InterfazBionic(root)
    root.mainloop()