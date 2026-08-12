# Cristobal Salcedo — BI & Data Analytics

> _Spanish-language portfolio index and public-repo traffic telemetry for [@CSalcedoDataBI](https://github.com/CSalcedoDataBI)._

¡Hola! Soy Cristobal Salcedo, ingeniero en producción y consultor de análisis de datos apasionado por descubrir insights a través de la visualización de datos y la inteligencia de negocio. En este espacio comparto proyectos, desafíos resueltos y plantillas de visualización que pueden ayudarte a llevar tus habilidades en Power BI y herramientas de BI al siguiente nivel.

## Sobre mí

- **Profesión**: Ingeniero en Producción y Consultor de Análisis de Datos
- **Especializaciones**: Microsoft Power Platform y soluciones de BI
- **Intereses**: Desarrollo de visualizaciones avanzadas y técnicas de modelado de datos
- **Sitio web**: [csalcedodatabi.com](https://csalcedodatabi.com/)

## Repositorios destacados

| Repositorio | De qué trata |
|---|---|
| [PowerBI-Deneb](https://github.com/CSalcedoDataBI/PowerBI-Deneb) | Plantillas Deneb para Power BI: especificaciones Vega-Lite listas para copiar en tus informes. |
| [powerbi-pbip-tools](https://github.com/CSalcedoDataBI/powerbi-pbip-tools) | Herramientas de automatización para proyectos de Power BI en formato PBIP: recoloreado de íconos SVG, operaciones por lotes y más. |
| [BI_Challenges](https://github.com/CSalcedoDataBI/BI_Challenges) | Soluciones a retos de las comunidades de BI en PySpark, Python y lenguaje M de Power Query. |
| [SampleDataSets](https://github.com/CSalcedoDataBI/SampleDataSets) | Conjuntos de datos de muestra para pruebas, aprendizaje y demostraciones. |
| [fabric-data-agents](https://github.com/CSalcedoDataBI/fabric-data-agents) | Guía de referencia para construir e instruir agentes de datos de Microsoft Fabric. |
| [fabric-app-gallery](https://github.com/CSalcedoDataBI/fabric-app-gallery) | Plantillas de Microsoft Fabric Apps (Rayfin) listas para copiar, ejecutar y adaptar. |
| [ubl-star](https://github.com/CSalcedoDataBI/ubl-star) | De factura electrónica UBL 2.1 (DIAN Colombia, PEPPOL Europa) a un modelo dimensional listo para analizar. |
| [agentic-board](https://github.com/CSalcedoDataBI/agentic-board) | Coordinador de agentes de código que trabaja sobre un board real de GitHub Projects, con control de cuota y revisión obligatoria. |

## Telemetría del portafolio

Este repositorio, además del índice de arriba, mide cuánto tráfico reciben los repos públicos de la cuenta:

- **`telemetry/`** — `snapshot.py` toma cada día una foto de las métricas de tráfico de los repos listados en `telemetry/repos.json` (vistas, clones, referrers y páginas más visitadas) y normaliza los clones restando las ejecuciones de GitHub Actions, porque los runners de CI inflan la señal. Así el histórico refleja tráfico humano y sobrevive a la ventana corta que expone la API de tráfico.
- **`.github/workflows/telemetry-snapshot.yml`** — corre a las 01:30 UTC (los datos del día anterior ya están disponibles a esa hora) y commitea el snapshot. También se puede lanzar a mano con `workflow_dispatch`.
- **`docs/`** — el histórico acumulado (`docs/telemetry/`) y el dashboard que lo grafica (`docs/index.html`).

Para ver el dashboard en local basta con servir la carpeta `docs/`:

```bash
python -m http.server 8000 --directory docs
```

## Colaboraciones y contacto

Estoy abierto a colaboraciones y oportunidades que enriquezcan el mundo del análisis de datos. Si tienes alguna idea o proyecto en mente, ¡conversemos!

- [LinkedIn](https://www.linkedin.com/in/cristobal-salcedo)
- Correo: [contacto@csalcedodatabi.com](mailto:contacto@csalcedodatabi.com)

## Contribuciones

¡Tus contribuciones son bienvenidas! Si deseas mejorar alguno de los proyectos o tienes sugerencias, no dudes en hacer un fork del repositorio y enviar tus pull requests. Para cualquier discusión adicional, puedes abrir un issue o contactarme directamente.

## Licencia

[MIT](LICENSE) — puedes usar, copiar y adaptar el contenido de este repositorio citando la autoría.

---

⭐ No olvides dar estrellas a los repositorios que encuentres útiles. ¡Esto ayuda a que más personas los encuentren y aprendan de ellos!
