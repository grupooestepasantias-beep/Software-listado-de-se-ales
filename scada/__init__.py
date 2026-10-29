"""Motor SCADA (columnas H-O del listado): tag, offset, descripción SCADA, estados/RAW/EU y unidades.

    from scada import generar_scada, cargar_perfil
    informe = generar_scada(proyecto, cargar_perfil("EPEN"))

Reglas por cliente en perfiles/<cliente>/scada.json; abreviaturas aprendidas en perfiles/<cliente>/glosario.json.
"""
from .descripcion import Glosario  # noqa: F401
from .gen import ErrorGeneracion, Informe, generar_scada  # noqa: F401
from .perfil import PerfilInvalido, PerfilScada  # noqa: F401
from .perfil import cargar as cargar_perfil  # noqa: F401
from .perfil import listar as listar_perfiles  # noqa: F401
