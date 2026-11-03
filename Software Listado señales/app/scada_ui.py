"""Ventanas del SCADA (columnas H-O): offsets iniciales, revisión de las descripciones propuestas y avisos.

La lógica (confirmar propuestas y recordarlas) está en `confirmar_propuestas`, sin pantalla, para poder probarla."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from modelo import Funcion, Senal

from scada import Glosario
from scada import texto as tx


# ---------------------------------------------------------------- lógica sin pantalla
def pendientes_de_confirmar(niveles) -> list[Senal]:
    """Señales cuya DESC. SCADA es una propuesta (todavía no confirmada por el usuario)."""
    return [s for n in niveles for c in n.campos for s in c.senales
            if s.desc_scada_origen == "propuesta" and s.desc_scada and not s.segunda_fila]


def confirmar_propuestas(items: list[tuple[Senal, str]], todas: list[Senal], glosario: Glosario, maximo: int) -> int:
    """items = [(señal, descripción SCADA definitiva)]. Marca cada una como confirmada por el usuario (no se vuelve a
    pisar), propaga el valor a los comandos que comparten descripción con su señalización y recuerda la abreviatura
    en el glosario del usuario para las próximas obras. Devuelve cuántas confirmó. Lanza ValueError si alguna no entra."""
    for s, valor in items:
        if not valor.strip():
            raise ValueError(f"«{s.desc_hmi}»: la descripción SCADA no puede quedar vacía")
        if len(valor) > maximo:
            raise ValueError(f"«{valor}» tiene {len(valor)} caracteres (máximo {maximo})")
    for s, valor in items:
        anterior = s.desc_scada
        s.desc_scada, s.desc_scada_origen = valor.strip(), "usuario"
        if "desc_scada" not in s.fijos:
            s.fijos.append("desc_scada")
        for x in todas:  # el comando comparte la descripción de su señalización
            if x is not s and x.funcion == Funcion.COMANDO and x.par and x.par == s.par and x.desc_scada == anterior:
                x.desc_scada, x.desc_scada_origen = s.desc_scada, "usuario"
        prefijo, texto = tx.separar_prefijo(s.desc_hmi)
        if texto and s.desc_scada.lower().startswith(prefijo.lower()):
            resto = s.desc_scada[len(prefijo):].strip()
            if resto:
                glosario.recordar("texto", tx.clave_exacta(texto), resto)
    return len(items)


def resumen_informe(informe, total_filas: int) -> str:
    o = informe.origen
    lineas = [f"SCADA generado para {total_filas} filas.", "",
              f"DESC. SCADA: {o.get('glosario', 0)} del glosario del cliente, {o.get('reglas', 0)} por reglas, "
              f"{o.get('usuario', 0)} de tus respuestas anteriores, {o.get('propuesta', 0)} PROPUESTAS a confirmar "
              f"(resaltadas en amarillo; botón «Propuestas SCADA…»).",
              f"MIN/MAX EU de {informe.eu_por_defecto} mediciones calculados como RAW × factor: son valores de ingeniería "
              f"del aparato, conviene confirmarlos."]
    if informe.avisos:
        lineas += ["", f"Avisos ({len(informe.avisos)}):"] + [f"  • {a}" for a in informe.avisos]
    return "\n".join(lineas)


# ---------------------------------------------------------------- ventanas
class DialogoOffsets(tk.Toplevel):
    """El software siempre pregunta desde qué número arrancar cada tipo de offset (una obra intervenida continúa
    desde el último número de la obra anterior). `resultado` = {"DI": 200, "AI": 200, ...} o None si cancela."""

    TIPOS = (("DI", "Entradas digitales (alarmas, señalizaciones, reservas)", True),
             ("AI", "Entradas analógicas (mediciones)", True),
             ("DO", "Salidas digitales de comandos sin señalización (opcional)", False))

    def __init__(self, master, iniciales: dict[str, int]):
        super().__init__(master)
        self.title("Offsets iniciales")
        self.transient(master)
        self.resultado: Optional[dict[str, int]] = None
        self.vars = {t: tk.StringVar(value=str(iniciales.get(t, 200 if t != "DO" else ""))) for t, _, _ in self.TIPOS}
        f = ttk.Frame(self, padding=10)
        f.pack()
        ttk.Label(f, foreground="#555", wraplength=420, justify="left",
                  text="¿Desde qué número arranca cada OFFSET? Si la obra continúa una anterior, poné el siguiente al último "
                       "de ese listado. Un comando de doble bit usa el mismo offset que su señalización.").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        for i, (t, texto, _) in enumerate(self.TIPOS, start=1):
            ttk.Label(f, text=f"{t} — {texto}").grid(row=i, column=0, sticky="w", pady=2, padx=(0, 8))
            ttk.Entry(f, textvariable=self.vars[t], width=8).grid(row=i, column=1)
        b = ttk.Frame(f)
        b.grid(row=len(self.TIPOS) + 1, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(b, text="Cancelar", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(b, text="Generar SCADA", command=self._ok).pack(side="right")
        self.bind("<Return>", lambda e: self._ok())
        self.grab_set()

    def _ok(self) -> None:
        res: dict[str, int] = {}
        for t, texto, obligatorio in self.TIPOS:
            v = self.vars[t].get().strip()
            if not v:
                if obligatorio:
                    messagebox.showwarning("Falta dato", f"Indicá el offset inicial de {t}.", parent=self)
                    return
                continue
            if not v.isdigit():
                messagebox.showwarning("Valor no válido", f"El offset de {t} debe ser un número entero (0 o mayor).", parent=self)
                return
            res[t] = int(v)
        self.resultado = res
        self.destroy()


class VentanaPropuestas(tk.Toplevel):
    """Descripciones SCADA propuestas por palabras: se corrigen con doble clic y se confirman. Lo confirmado queda fijo
    en el listado y se recuerda en el glosario (no se vuelve a preguntar en las próximas obras)."""

    def __init__(self, master, senales: list[Senal], todas: list[Senal], glosario: Glosario, ruta_glosario,
                 maximo: int, al_cambiar: Callable[[], None]):
        super().__init__(master)
        self.title("Descripciones SCADA propuestas")
        self.transient(master)
        self.geometry("860x460")
        self.senales, self.todas, self.glosario = senales, todas, glosario
        self.ruta, self.maximo, self.al_cambiar = ruta_glosario, maximo, al_cambiar
        self.valores = [s.desc_scada for s in senales]
        ttk.Label(self, foreground="#555", wraplength=820, justify="left", padding=8,
                  text=f"Son PROPUESTAS: el cliente abrevia a su manera. Corregí con doble clic en la columna DESC. SCADA "
                       f"(máximo {maximo} caracteres) y confirmá. Lo confirmado se recuerda para las próximas obras."
                  ).pack(fill="x")
        marco = ttk.Frame(self)
        marco.pack(fill="both", expand=True, padx=8)
        self.arbol = ttk.Treeview(marco, columns=("hmi", "scada", "largo"), show="headings", selectmode="browse")
        for c, t, w in (("hmi", "DESC. HMI", 470), ("scada", "DESC. SCADA propuesta", 230), ("largo", "LARGO", 60)):
            self.arbol.heading(c, text=t)
            self.arbol.column(c, width=w, anchor="w")
        sy = ttk.Scrollbar(marco, orient="vertical", command=self.arbol.yview)
        self.arbol.configure(yscrollcommand=sy.set)
        self.arbol.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        marco.rowconfigure(0, weight=1)
        marco.columnconfigure(0, weight=1)
        self.arbol.bind("<Double-1>", self._editar)
        self._ed: Optional[tk.Entry] = None
        self._llenar()
        b = ttk.Frame(self, padding=8)
        b.pack(fill="x")
        ttk.Button(b, text="Cerrar", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(b, text="Confirmar todas y recordar", command=self._confirmar).pack(side="right")
        self.estado = ttk.Label(b, text=f"{len(senales)} propuestas")
        self.estado.pack(side="left")

    def _llenar(self) -> None:
        self.arbol.delete(*self.arbol.get_children())
        for i, (s, v) in enumerate(zip(self.senales, self.valores)):
            self.arbol.insert("", "end", iid=str(i), values=(s.desc_hmi, v, len(v)))

    def _editar(self, ev) -> None:
        iid, col = self.arbol.identify_row(ev.y), self.arbol.identify_column(ev.x)
        if not iid or col != "#2":
            return
        x, y, w, h = self.arbol.bbox(iid, col)
        ent = tk.Entry(self.arbol)
        ent.insert(0, self.valores[int(iid)])
        ent.select_range(0, "end")
        ent.place(x=x, y=y, width=w, height=h)
        ent.focus_set()

        def fin(guardar: bool) -> None:
            if guardar:
                self.valores[int(iid)] = ent.get().strip()
            ent.destroy()
            self._llenar()

        ent.bind("<Return>", lambda e: fin(True))
        ent.bind("<Escape>", lambda e: fin(False))
        ent.bind("<FocusOut>", lambda e: fin(True))

    def _confirmar(self) -> None:
        try:
            n = confirmar_propuestas(list(zip(self.senales, self.valores)), self.todas, self.glosario, self.maximo)
            self.glosario.guardar(self.ruta)
        except (ValueError, OSError) as e:
            messagebox.showwarning("No se pudo confirmar", str(e), parent=self)
            return
        self.al_cambiar()
        messagebox.showinfo("Confirmadas", f"{n} descripciones confirmadas y recordadas.", parent=self)
        self.destroy()


def mostrar_texto(master, titulo: str, texto: str) -> tk.Toplevel:
    """Ventana de solo lectura con texto largo (resumen y avisos del SCADA)."""
    v = tk.Toplevel(master)
    v.title(titulo)
    v.geometry("780x420")
    t = tk.Text(v, wrap="word", padx=8, pady=8)
    sb = ttk.Scrollbar(v, orient="vertical", command=t.yview)
    t.configure(yscrollcommand=sb.set)
    t.insert("1.0", texto)
    t.configure(state="disabled")
    sb.pack(side="right", fill="y")
    t.pack(fill="both", expand=True)
    return v
