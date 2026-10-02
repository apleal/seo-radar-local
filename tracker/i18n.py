"""Traducciones compartidas de la interfaz de SEO Radar Local."""
TRANSLATIONS = {"es": {
    "rankings": "Posiciones", "research": "Palabras clave", "site_explorer": "Explorador de sitios",
    "competitors": "Competidores", "ai_visibility": "Visibilidad en IA", "site_health": "Salud SEO",
    "link_gap": "Oportunidades de enlaces", "map_grid": "Mapa de visibilidad local",
    "tracked_urls": "Webs monitorizadas", "reports": "Informes", "all_urls": "Todas las webs",
    "last_update": "Última actualización", "refresh": "Actualizar", "rerun": "Ejecutar de nuevo",
    "keyword": "Palabra clave", "position": "Posición", "search_volume": "Volumenn de búsqueda",
    "cancel": "Cancelarar", "save": "Guardar", "remove": "Eliminar", "error": "Error",
    "queued": "Tarea añadida", "no se pudo completar": "No se pudo completar",
}}
def t(key, lang="es"):
    return TRANSLATIONS.get(lang, TRANSLATIONS["es"]).get(key, key)
