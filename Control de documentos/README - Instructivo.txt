CONTROL DE DOCUMENTOS - INSTRUCTIVO PARA EMPEZAR DESDE CERO
============================================================

Este instructivo esta pensado para alguien que nunca uso el programa.
Si algo sale mal, mirar el archivo "Problemas comunes y como solucionarlos.txt".


1. PARA QUE SIRVE
-----------------
Lleva el control de los documentos de una obra: cual se entrego, en que estado
esta (en revision, aprobado, devuelto con DPC...), en que revision va (A, B, 0, 1...)
y si se cumplieron los plazos. Trabaja junto al Excel de control: cada hoja
"Rev (N)" del Excel es una revision de la lista, y el programa la mantiene
actualizada por vos. Tambien arma las hojas "KPI N°1", "KPI N°2" y "Dashboard".


2. INSTALACION (una sola vez)
-----------------------------
1) Copiar "Control de documentos.exe" a una carpeta PROPIA de tu computadora
   (por ejemplo Documentos\Control doc). No hace falta instalar nada.
2) NO ejecutarlo desde la carpeta de red: cada persona usa su propia copia.
3) Doble clic. La primera vez tarda unos segundos en abrir.
4) Windows puede avisar "editor desconocido": clic en "Mas informacion" y despues
   "Ejecutar de todas formas".
5) Al abrirlo por primera vez se crea, al lado del .exe, un archivo
   "documentos.db". Es la base de datos con TODA la informacion.
   No borrarlo ni moverlo solo. Hacerle una copia de seguridad cada tanto.


3. USUARIOS Y PERMISOS
----------------------
  Admin      / admin123     -> puede hacer todo.
  usuario1   / usuario234   -> solo consulta: Consultar, Dashboard y KPI.
  Gerencia   / gerencia123  -> solo Dashboard y KPI.

Si la primera vez el programa te pide crear contraseñas, hacelo (minimo 4
caracteres y distintas entre si). El Admin puede cambiarlas despues con el boton
"Usuarios" (arriba a la derecha).


4. AL ENTRAR: ELEGIR PROYECTO Y CLIENTE
---------------------------------------
Despues del usuario aparece una ventana:
  - Proyecto: elegir uno de la lista o crear uno nuevo ("Nuevo proyecto").
  - Cliente: por ejemplo YPF o EPEN. El nombre del cliente reemplaza a "EPEN" en
    todos los textos y encabezados del Excel.
Con "Entrar" se abre el programa. Proyecto y cliente se pueden cambiar despues
desde la barra de arriba.


5. LA PANTALLA PRINCIPAL
------------------------
Arriba hay: Cliente, Proyecto, "Revision de la lista" (selector), el boton
"Nueva revision" y el boton "Sincronizar con Excel".
Abajo hay 5 pestañas:

  1 · Cargar documentos     (solo Admin)
  2 · Consultar documento
  3 · Modificar / Actualizar (solo Admin)
  4 · Dashboard
  5 · KPI


6. PRIMER USO: TRAER EL EXCEL DE CONTROL (solo Admin)
-----------------------------------------------------
Pestaña 1 · Cargar documentos:
1) Cerrar el Excel de control si lo tenes abierto.
2) Boton "Importar Excel de control...": elegir el archivo. Cada hoja "Rev (N)"
   pasa a ser una revision; la ultima queda como la revision de trabajo actual.
3) El Excel queda "vinculado": arriba se ve "Excel vinculado: ...". Desde ahi, el
   programa modifica ESE archivo cuando guardas cambios. (Con "Vincular / cambiar
   Excel..." se puede elegir otro.)

Otros botones de la pestaña 1:
  - Exportar a Excel nuevo: genera un Excel completo (hojas Rev, KPI y Dashboard).
  - Generar KPI y Dashboard en el Excel: regenera esas 3 hojas en el Excel vinculado.
  - Cargar informe PDF: ver punto 9.
  - B · Listado general: cargar todos los documentos de la obra y marcar cuales
    entregamos nosotros.
  - C · Cargar a mano: agregar un documento, o varios pegados desde Excel.


7. CONSULTAR UN DOCUMENTO (todos los usuarios)
----------------------------------------------
Pestaña 2:
- Escribi en el buscador parte del nombre, codigo o estado y se filtra la lista.
- Al elegir un documento se ve su ficha: revisiones, estados, plazos, correcciones
  y la evolucion en cada revision.
- FILTRO POR COLOR: abajo de la lista hay una leyenda de colores. Hacer clic en un
  color muestra solo los documentos de ese estado; clic de nuevo en el mismo
  color quita el filtro. El contador muestra "X de Y documentos".

Colores:
  Verde      = Aprobado o APC
  Amarillo   = Aprobado con observaciones
  Rojo       = DPC / Rechazado
  Azul       = En revision
  Celeste    = No se observa
  Gris azul  = Visto
  Sin color  = Sin estado


8. MODIFICAR UN DOCUMENTO (solo Admin)
--------------------------------------
Pestaña 3 · Modificar / Actualizar:
1) "1. Elegi el documento": escribir para filtrar la lista y hacer clic en el documento.
2) "2. Actualiza el estado":
   - Revision emitida (Grupo Oeste / Cliente / el cliente elegido): la secuencia es
        A -> B -> C ...  mientras el documento tenga observaciones
        y al quedar APROBADO pasa a 0 -> 1 -> 2 ...
     El boton "Subir" aplica esa regla solo, segun el estado cargado. Tambien se
     puede escribir la revision a mano.
   - Entrega y estado: tildar "Documento entregado" y elegir el estado (APC,
     Aprobado, Aprobado c/obs, DPC, En revision...) y el N° de informe.
   - Fechas para los KPI: fecha limite (cronograma), fecha real de entrega (al tildar
     "entregado" propone la de hoy), transmittal (ej.: Envio 4). Formato dd/mm/aaaa.
   - Correccion: si el documento volvio con DPC, tildar "Correccion", elegir la
     "Revision devuelta" (ej.: A) y cargar la fecha de devolucion; cuando se
     reenvia corregido, cargar la fecha de reenvio.
   - Comentarios.
3) Boton "Guardar cambios". Esto guarda en la base Y ACTUALIZA LA HOJA de la
   ultima revision del Excel vinculado. El Excel tiene que estar CERRADO.
   Aparece el mensaje "Guardado ... Excel Rev (N) actualizado".
Otros botones: "Deshacer" (vuelve a lo ultimo guardado) y "Eliminar documento".


9. ACTUALIZAR CON EL INFORME DE INGENIERIA (PDF) (solo Admin)
--------------------------------------------------------------
Pestaña 1 -> "Cargar informe PDF...":
1) Elegir el PDF. El programa lee la tabla y propone, documento por documento,
   el estado nuevo (APC, Aprobado c/obs, DPC...) y la revision.
2) Revisar la lista que aparece. Los documentos que no cambian vienen sin marcar.
3) "Aplicar al control" para guardar. Tambien se actualiza el Excel.
Importante: si el informe es MAS VIEJO que el ultimo ya aplicado, el programa
lo bloquea para no pisar datos nuevos.


10. NUEVA REVISION: CUANDO SE ENTREGAN ARCHIVOS
-----------------------------------------------
Las revisiones se crean cuando se ENTREGAN archivos, no cada vez que se edita.
- Mientras trabajes sobre la revision actual (por ejemplo Rev 7), todo lo que
  guardes MODIFICA la hoja "Rev (7)" del Excel. No se agregan hojas.
- Cuando se entrega una tanda nueva de archivos: boton "Nueva revision N°X"
  (arriba). Agrega la hoja "Rev (X)" al Excel, con el estado actual de los
  documentos como punto de partida.
- Para ver una revision vieja, elegirla en "Revision de la lista".
Antes de modificar el Excel, el programa guarda una copia de respaldo en la carpeta
"respaldos", junto al Excel.


11. DASHBOARD Y KPI (todos los usuarios)
----------------------------------------
- Dashboard: totales, % entregado, aprobados, en revision, devueltos, y graficos.
- KPI N°1: cumplimiento de entrega (fecha limite contra fecha real). Muestra
  maximo desvio, documento con ese desvio y promedio (se toman del Excel).
- KPI N°2: respuesta a correcciones (dias entre la devolucion con DPC y el reenvio).
Para que los KPI tengan datos hay que cargar las fechas en la pestaña 3.
Para tenerlos tambien dentro del Excel: pestaña 1 -> "Generar KPI y Dashboard en
el Excel" (con el Excel cerrado).


12. RUTINA RECOMENDADA
----------------------
1) Abrir el programa, elegir proyecto y cliente.
2) Llega un informe de ingenieria: cargarlo (punto 9) y revisar lo propuesto.
3) Llegan documentos corregidos o devueltos: pestaña 3, actualizar y "Guardar cambios".
4) Se entregan archivos nuevos: "Nueva revision".
5) Generar KPI y Dashboard en el Excel cuando haga falta un reporte.
6) Cada semana: copiar "documentos.db" a un lugar seguro.


13. REGLAS DE ORO
-----------------
- Excel CERRADO antes de guardar, crear revision o generar KPI.
- Fechas siempre dd/mm/aaaa.
- Cada persona usa su propia copia del programa (no desde la carpeta de red).
- Cuidar "documentos.db": es toda la informacion. Hacer copias de seguridad.
- No editar a mano el Excel a la vez que el programa: si hay que editarlo,
  hacerlo y luego usar "Sincronizar con Excel" si se borraron hojas.
