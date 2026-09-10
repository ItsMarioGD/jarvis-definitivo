import re
import ejecutor
import deshacer
from datetime import datetime, timedelta

class HabilidadNavidad:
    patterns = [
        r'dime cuantos dias faltan para navidad',
        r'cuantos dias faltan para navidad',
        r'cuantos dias quedan para navidad',
        r'cuantos dias faltan para la navidad'
    ]
    priority = 40
    description = "Calcula los días que faltan para Navidad"

    def handle(self, text, core):
        try:
            now = datetime.now()
            navidad = datetime(now.year, 12, 25)
            
            # Si ya pasó Navidad este año, calculamos para el próximo
            if now > navidad:
                navidad = datetime(now.year + 1, 12, 25)
            
            days_left = (navidad - now).days
            
            return f"Señor, faltan {days_left} días para Navidad."
        except Exception as e:
            return None