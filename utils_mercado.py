"""
Utilidad compartida de mercado para BrokerHub.

mercado_esta_abierto() estaba copiada de forma idéntica en main.py y en
ejecutor_ordenes.py. Se centraliza aquí para que ambos SIEMPRE usen
exactamente la misma regla de horario -- si se corregía en un archivo
y no en el otro, la API podía decir "mercado abierto" mientras el
ejecutor decidía con la regla vieja, o viceversa.

Nota: la lógica de "último precio conocido" NO se unifica porque main.py
la necesita para UN instrumento a la vez (bajo demanda, endpoint por
endpoint) mientras que ejecutor_ordenes.py la necesita en LOTE para
muchos instrumentos por ciclo (leer_precios_actuales). Son problemas
distintos con perfiles de rendimiento distintos; forzarlas a compartir
código añadiría complejidad sin beneficio real.
"""

from datetime import datetime
from zoneinfo import ZoneInfo


def mercado_esta_abierto() -> bool:
    """Horario de NYSE/NASDAQ: lunes a viernes, 9:30 AM - 4:00 PM hora de
    Nueva York. No contempla feriados (simplificación aceptada para el
    alcance del proyecto)."""
    ahora_ny = datetime.now(ZoneInfo("America/New_York"))

    if ahora_ny.weekday() >= 5:  # 5=sábado, 6=domingo
        return False

    apertura = ahora_ny.replace(hour=9, minute=30, second=0, microsecond=0)
    cierre = ahora_ny.replace(hour=16, minute=0, second=0, microsecond=0)

    return apertura <= ahora_ny <= cierre