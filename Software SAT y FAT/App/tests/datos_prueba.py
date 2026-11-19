"""Datos FICTICIOS para las pruebas (no son información real de ingeniería)."""
DATOS = dict(FECHA="02/11/2026", OBRA="000-PRUEBA_Obra de prueba", TIPO_TABLERO="Tablero de Control",
             NOMBRE="Estación Prueba", CLIENTE="CLIENTE PRUEBA", NRO_OBRA="000", REVISION="A", PROTECCIONES=True, UBICACION="Ubicación de prueba")
DOCUMENTOS = [("PRUEBA-EF-0001_rA.pdf", "TABLERO DE CONTROL DE 33 KV ESQUEMA FUNCIONAL"),
              ("PRUEBA-TP-0001_rA.pdf", "TABLERO DE CONTROL DE 33 KV ESQUEMA CONSTRUCTIVO")]
COMPONENTES = ([("RTAC SEL 2241", "")] + [("POWER COUPLER SEL 2243", "")] * 2
               + [("MÓDULO DI SEL 2244-2", "")] * 4 + [("MÓDULO DO SEL 2244-3", "")] * 2)
TERMICAS = [("220 VCA", "Iluminación", "Q221"), ("220 VCA", "Toma", "Q222"),
            ("110 VCC", "Circuito de alimentación general", "Q1"),
            ("110 VCC", "Circuito de alimentación Fuente 1", "Q2")]
SENALES = [(f"-XFI1/{i}", f"Señal de prueba {i}") for i in range(1, 61)]
COMANDOS = [("XF01-2", "Comando de prueba apertura"), ("XF01-3", "Comando de prueba cierre")]
