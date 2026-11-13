"""Base central del generador: la señal con todos sus datos y el proyecto que las agrupa (etapa 1)."""
from .proyecto_db import VERSION, ProyectoDB
from .senal import FUENTE_POR_DEFECTO, MANUAL, PDF, REGLA, SenalBase

__all__ = ["ProyectoDB", "SenalBase", "VERSION", "PDF", "REGLA", "MANUAL", "FUENTE_POR_DEFECTO"]
