"""
portada_generalidades.py
Skill: Genera secciones preliminares + Secciones 1–4 del informe de calidad del aire.

Cubre:
  - Portada
  - Página de control (firmas, equipos, revisiones)
  - Tabla de contenido
  - Lista de Anexos / Figuras / Tablas / Gráficas
  - Glosario
  - Lista de Abreviaturas
  - Sección 1. Datos Básicos
  - Sección 2. Introducción  (+ Tablas 2, 3, 4 de cumplimiento)
  - Sección 3. Objetivos
  - Sección 4. Generalidades (§4.1 – §4.13)

Uso:
    from skills.portada_generalidades.portada_generalidades import generate_report
    result = generate_report(config: dict, output_dir: str)

Retorna:
    {
        "report_path": str,   # HTML autocontenido
    }
"""

import base64
import json
import os
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _b64(path: str) -> str:
    """Encode image to base64 data-URI. Returns empty string if file missing."""
    if not path or not os.path.isfile(path):
        return ""
    ext = Path(path).suffix.lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif", "svg": "svg+xml"}.get(ext, "png")
    with open(path, "rb") as f:
        return f"data:image/{mime};base64,{base64.b64encode(f.read()).decode()}"


def _img(path: str, style: str = "", alt: str = "") -> str:
    src = _b64(path)
    if not src:
        return f'<div class="img-placeholder" style="{style}">[Imagen no encontrada: {path}]</div>'
    return f'<img src="{src}" alt="{alt}" style="{style}">'


def _fmt_date(iso: str) -> str:
    """'2025-12-17' → '17 de diciembre de 2025'"""
    months = ["enero","febrero","marzo","abril","mayo","junio",
              "julio","agosto","septiembre","octubre","noviembre","diciembre"]
    try:
        y, m, d = iso.split("-")
        return f"{int(d)} de {months[int(m)-1]} de {y}"
    except Exception:
        return iso


def _period_text(period: dict) -> str:
    return (f"entre el {_fmt_date(period['start_date'])} "
            f"al {_fmt_date(period['end_date'])}, "
            f"durante {period['duration_days']} días continuos")


# ─────────────────────────────────────────────────────────────────────────────
# FIXED BOILERPLATE TEXT
# ─────────────────────────────────────────────────────────────────────────────

GLOSSARY = [
    ("Agentes contaminantes convencionales",
     "Se entiende por agentes contaminantes convencionales los contaminantes primarios (Monóxido de carbono, "
     "material particulado, óxidos de azufre e hidrocarburos) y contaminantes secundarios (ozono, Dióxido de nitrógeno)."),
    ("Analizador",
     "Equipo instrumental necesario para realizar análisis del aire ambiente mediante el uso de las propiedades "
     "físicas y químicas y que da señales de salida cíclicas o puntuales."),
    ("Azufre Total Reducido (TRS)",
     "Compuestos organosulfurados integrados principalmente por sulfuro de hidrógeno, metil mercaptano, dimetil "
     "sulfuro y dimetil disulfuro. Se caracterizan por su desagradable olor aun a bajas concentraciones."),
    ("Calibración",
     "Conjunto de operaciones que establece, bajo condiciones específicas, la relación entre los valores indicados "
     "por un instrumento de medición, sistema de medición o valores representados por una unidad de medida y los "
     "valores conocidos correspondientes a una medición."),
    ("Concentración de fondo",
     "Fracción de la calidad del aire observado que no se puede relacionar directamente con las fuentes que se estudian."),
    ("Concentración de olor",
     "El número de unidades de olor europeas en un metro cúbico de gas en condiciones normales."),
    ("Concentración de una Sustancia en el Aire",
     "Es la relación que existe entre el peso o el volumen de una sustancia y la unidad de volumen de aire en la cual está contenida."),
    ("Condiciones de Referencia",
     "Son los valores de temperatura y presión con base en los cuales se fijan las normas de calidad del aire y de "
     "las emisiones, que respectivamente equivalen a 25°C y 760 mm Hg (1 atmósfera de presión)."),
    ("Contaminación atmosférica",
     "Es el fenómeno de acumulación o de concentración de contaminantes en el aire."),
    ("Contaminantes",
     "Fenómenos físicos o sustancias, o elementos en estado sólido, líquido o gaseoso, causantes de efectos adversos "
     "en el medio ambiente, los recursos naturales renovables y la salud humana, que, solos o en combinación, o como "
     "productos de reacción, se emiten al aire como resultado de actividades humanas, de causas naturales, o de una combinación de estas."),
    ("Controles o banderas",
     "Son marcas que constan de una letra, cada una de las cuales le aporta una característica específica al dato "
     "que acompaña, ya sea de validez o de invalidez de este."),
    ("Emisión",
     "Es la descarga de una sustancia o elemento al aire, en estado sólido, líquido o gaseoso, o en alguna "
     "combinación de estos, provenientes de una fuente fija o móvil."),
    ("Emisión fugitiva",
     "Es la emisión ocasional de material contaminante."),
    ("Excedencia",
     "Representación numérica para cada episodio que por contaminante supera el límite normativo correspondiente."),
    ("Fuente fija",
     "Es la fuente de emisión situada en un lugar determinado e inamovible, aun cuando la descarga de contaminantes "
     "se produzca en forma dispersa."),
    ("Fuente Móvil",
     "Es la fuente de emisión que, por razón de su uso o propósito, es susceptible de desplazarse, como los "
     "automotores o vehículos de transporte a motor de cualquier naturaleza."),
    ("Fuentes Naturales",
     "Emisiones provenientes de fuentes naturales como la re-suspensión del polvo, las biogénicas y los volcanes en actividad."),
    ("Inmisión",
     "Transferencia de contaminantes de la atmósfera a un \"receptor\". Se entiende por inmisión la acción opuesta "
     "a la emisión. Aire inmiscible es el aire respirable a nivel de la troposfera."),
    ("Límite de detección",
     "Es el valor inferior del intervalo de variación de una característica (como la concentración) que un "
     "procedimiento que utiliza un método de medición específico puede discernir."),
    ("Monitoreo",
     "En el sentido más amplio de la palabra, medición repetida para seguir la evolución de un parámetro durante un período de tiempo."),
    ("Norma diaria",
     "Establece la concentración máxima diaria permisible de un contaminante, definida como el promedio aritmético "
     "de los valores de las muestras horarias, que podrá excederse solo una vez en un año."),
    ("Norma horaria",
     "Establece la concentración máxima permisible de un contaminante, de las mediciones realizadas en un periodo "
     "de tiempo establecido (media hora, una hora, tres horas, 6 horas y 8 horas)."),
    ("Norma de Calidad del Aire o Nivel de Inmisión",
     "Es el nivel de concentración legalmente permisible de sustancias o fenómenos contaminantes presentes en el "
     "aire, establecido por el Ministerio de Ambiente, Vivienda y Desarrollo Territorial, con el fin de preservar "
     "la buena calidad del medio ambiente, los recursos naturales renovables y la salud humana."),
    ("Punto Crítico",
     "Puntos donde se encuentran posibles concentraciones altas por exposición directa (Hot Spot)."),
    ("Validación",
     "Proceso que permite determinar si los datos resultantes de la etapa de monitoreo son confiables, "
     "representativos y de calidad, acopiando e inspeccionando mediante evidencia objetiva que confirme que los "
     "requerimientos específicos del uso final de los datos han sido cumplidos."),
]

ABBREVIATIONS = [
    ("μm", "Unidad de longitud, micrómetro"),
    ("°T", "Temperatura"),
    ("°Ta", "Temperatura Ambiente"),
    ("μg/m³", "Microgramos por metro cúbico"),
    ("ppm", "Partes por millón"),
    ("CO", "Monóxido de Carbono"),
    ("Dv", "Dirección del Viento"),
    ("ICA", "Índice de Calidad del Aire"),
    ("H₂S", "Sulfuro de Hidrógeno"),
    ("HR", "Humedad Relativa"),
    ("L", "Litros"),
    ("Low-Vol", "Muestreador de Bajo Volumen"),
    ("MADS", "Ministerio de Ambiente y Desarrollo Sostenible"),
    ("MDsvca", "Manual de Diseño de Sistemas de Vigilancia de la Calidad del Aire"),
    ("MOsvca", "Manual de Operación de Sistemas de Vigilancia de la Calidad del Aire"),
    ("NH₃", "Amoniaco"),
    ("NO₂", "Dióxido de Nitrógeno"),
    ("Pb", "Presión Barométrica"),
    ("PMSCA", "Protocolo para el Monitoreo y Seguimiento de la Calidad del Aire"),
    ("Pp", "Precipitación"),
    ("O₃", "Ozono"),
    ("Qa", "Caudal Real o Actual"),
    ("Qstd", "Caudal estándar"),
    ("r", "Coeficiente de correlación"),
    ("SO₂", "Dióxido de Azufre"),
    ("SEVCA", "Sistema Especial de Vigilancia de la Calidad del Aire"),
    ("SISAIRE", "Sistema de Información sobre Calidad del Aire"),
    ("SVCAI", "Sistema de Vigilancia de la Calidad del Aire Industrial"),
    ("TRS", "Azufre Total Reducido."),
    ("USEPA", "Agencia de Protección Ambiental de los Estados Unidos (Environmental Protection Agency)"),
    ("Vv", "Velocidad del Viento."),
]

# Tabla 5 – Contaminantes Medidos (Res. 2254/2017, fija por normativa)
POLLUTANT_TABLE = [
    {
        "contaminante": "PM<sub>10</sub>",
        "principio": "Dispersión Laser",
        "metodo": "Determinación de concentración de Material Particulado PM<sub>10</sub> & PM<sub>2,5</sub>, "
                  "Asociación Española de Normalización (UNE) EN 16450",
        "limites": [("50", "Anual"), ("75", "24 horas")],
    },
    {
        "contaminante": "PM<sub>2,5</sub>",
        "principio": "Dispersión Laser",
        "metodo": "Determinación de concentración de Material Particulado PM<sub>10</sub> & PM<sub>2,5</sub>, "
                  "Asociación Española de Normalización (UNE) EN 16450",
        "limites": [("25", "Anual"), ("37", "24 horas")],
    },
    {
        "contaminante": "SO<sub>2</sub>",
        "principio": "Fluorescencia UV",
        "metodo": "Determinación de la concentración de dióxido de Azufre, EPA e-CFR Título 40, parte 50, "
                  "anexo A-1, Automated Reference Method: EQSA-0506-159",
        "limites": [("50", "24 horas"), ("100", "1 hora")],
    },
    {
        "contaminante": "NO<sub>2</sub>",
        "principio": "Quimioluminiscencia",
        "metodo": "Determinación de la concentración de Monóxido de Carbono, EPA e-CFR Título 40, Capítulo 1, "
                  "Subcapítulo C, parte 50, apéndice F, Automated Reference Method: RFNA-0506-157",
        "limites": [("60", "Anual"), ("200", "1 hora")],
    },
    {
        "contaminante": "CO",
        "principio": "Infrarrojo No Dispersivo",
        "metodo": "Determinación de la concentración de Monóxido de Carbono, EPA e-CFR Título 40, parte 50, "
                  "apéndice C, Automated Reference Method: RFCA-056-158",
        "limites": [("5000", "8 horas"), ("35000", "1 hora")],
    },
    {
        "contaminante": "O<sub>3</sub>",
        "principio": "Absorción UV no Dispersiva",
        "metodo": "Determinación de la concentración de Ozono, EPA e-CFR Título 40, parte 50, apéndice D, "
                  "Automated Reference Method: EQOA-0506-160",
        "limites": [("100", "8 horas")],
    },
]

# Textos fijos por contaminante – §4.3.x
POLLUTANT_DESCRIPTIONS = {
    "PM": {
        "title": "4.3.1 &nbsp; Material Particulado",
        "paragraphs": [
            "El material particulado se define como las partículas ambientales presentes en el aire, estas "
            "partículas se dividen según su diámetro aerodinámico, el material particulado PM<sub>10</sub>, "
            "son todas aquellas partículas cuyo diámetro es menor a 10 micras, así mismo, las partículas "
            "con diámetro menor a 2.5 micras, son denominadas material particulado PM<sub>2.5</sub>.",

            "Según la guía de calidad del aire de la OMS los efectos a la salud por parte de este "
            "contaminante son amplios, entre los cuales se encuentran afecciones al sistema respiratorio "
            "y cardiovascular. Su tamaño microscópico permite que las partículas ingresen al torrente "
            "sanguíneo a través del sistema respiratorio y viajen por todo el cuerpo, causando efectos "
            "de gran alcance en la salud, como asma, cáncer de pulmón y enfermedades cardíacas. El "
            "material particulado en el aire puede provenir de una variedad de fuentes como combustión "
            "de motores de vehículos, industria, incendios y quema de carbón. También existe tipo de "
            "fuentes de tipo natural, tales como, tormentas de arena y reacciones químicas presentes en la atmosfera.",

            "En Colombia, las concentraciones de Material Particulado PM<sub>10</sub> según la "
            "<strong>Figura 1</strong>, se encuentra en un rango entre 20 a 50 μg/m<sup>3</sup>, "
            "mientras que el PM<sub>2,5</sub> se encuentra en un rango de 25 a 35 μg/m3, para el efecto "
            "normativo, dichos parámetros se referencias en la Resolución 2254 de 2017 del Ministerio de "
            "Ambiente y Desarrollo Social MADS, dichos límites se encuentran en la <strong>Tabla 5</strong>.",

            "Para la medición de los parámetros PM<sub>10</sub> y PM<sub>2,5</sub>, el laboratorio "
            "ambiental Corola Ambiental S.A.S, cuenta con un analizador Grimm EDM-180C Dust Monitor, el "
            "cual bajo el principio de medición de Dispersión Laser, realiza la cuantificación de los "
            "parámetros en tiempo real, con mediciones horarias. Dicho método está avalado por la "
            "Normatividad Europea UNE 16450.",
        ],
        "fig_key": "fig1_pm",
        "fig_caption": "Figura 1 Exposición Mundial de Material Particulado PM<sub>10</sub> & PM<sub>2,5</sub>.",
        "fig_source": "World Health Organization – WHO. 2025.",
    },
    "SO2": {
        "title": "4.3.2 &nbsp; Dióxido de Azufre",
        "paragraphs": [
            "El SO<sub>2</sub> es un gas incoloro con un olor penetrante que se genera con la combustión "
            "de fósiles (carbón y petróleo) y la fundición de menas que contienen azufre. La principal "
            "fuente antropogénica del SO<sub>2</sub> es la combustión de fósiles que contienen azufre "
            "usados para la calefacción doméstica, la generación de electricidad y los vehículos a motor.",

            "Según la guía de calidad del aire de la OMS, el SO<sub>2</sub> puede afectar al sistema "
            "respiratorio y las funciones pulmonares, y causa irritación ocular. La inflamación del "
            "sistema respiratorio provoca tos, secreción mucosa y agravamiento del asma y la bronquitis "
            "crónica; asimismo, aumenta la propensión de las personas a contraer infecciones del sistema "
            "respiratorio. Los ingresos hospitalarios por cardiopatías y la mortalidad aumentan en los "
            "días en que los niveles de SO<sub>2</sub> son más elevados. En combinación con el agua, el "
            "SO<sub>2</sub> se convierte en ácido sulfúrico, que es el principal componente de la lluvia "
            "ácida que causa la deforestación.",

            "En la <strong>Figura 2</strong>, se observa el estado mundial de emisiones de Dióxido de "
            "Azufre, donde estas concentran en mayor cantidad en el este Asia y el sur este de Europa, "
            "respecto a America Latina, la zona crítica es parte sur del Perú.",

            "En Colombia el dióxido de azufre SO<sub>2</sub> esta referenciados en la Resolución 2254 "
            "de 2017 del Ministerio de Ambiente y Desarrollo Social MADS, estos parámetros se comparan "
            "con unos límites máximos permisibles en dos tipos distintos de tiempo de exposición, dichos "
            "límites se encuentran en la <strong>Tabla 5</strong>.",

            "Para la medición del parámetro SO<sub>2</sub>, el laboratorio ambiental Corola Ambiental "
            "S.A.S, cuenta con un analizador Horiba APSA-370 Air Monitor, el cual bajo el principio de "
            "medición de Fluorescencia UV, realiza la cuantificación del parámetro en tiempo real, con "
            "mediciones horarias. Dicho método está avalado por la Agencia de Protección Ambiental EPA "
            "en su método de referencia EQSA-0506-159.",
        ],
        "fig_key": "fig2_so2",
        "fig_caption": "Figura 2 Exposición Mundial de Dióxido de Azufre SO<sub>2</sub>.",
        "fig_source": "Global SO2 Emisión Hotspot Database.2025",
    },
    "NO2": {
        "title": "4.3.3 &nbsp; Dióxido de Nitrógeno",
        "paragraphs": [
            "El NO<sub>2</sub> es un gas incoloro que se puede correlacionar con varias actividades "
            "industriales. En concentraciones de corta duración superiores a 200 mg/m<sup>3</sup>, es un "
            "gas tóxico que causa una importante inflamación de las vías respiratorias. Su fuente "
            "principal son los aerosoles de nitrato, que constituyen una parte importante de las concentraciones.",

            "Las principales fuentes de emisiones antropogénicas de NO<sub>2</sub> son los procesos de "
            "combustión (calefacción, generación de electricidad y motores de vehículos y barcos).",

            "Según la guía de calidad del aire de la OMS el contaminante NO<sub>2</sub> puede generar "
            "síntomas de bronquitis en niños asmáticos aumentan en relación con la exposición prolongada "
            "al NO<sub>2</sub>. La disminución del desarrollo de la función pulmonar también se asocia "
            "con las concentraciones de NO<sub>2</sub>.",

            "En la <strong>Figura 3</strong>, se observa el estado mundial de emisiones de Dióxido de "
            "Nitrógeno, donde estas concentran en mayor cantidad en el norte de Europa y el este de "
            "Rusia, respecto a America Latina, la zona crítica es parte sureste de Brasil.",

            "En Colombia el dióxido de nitrógeno NO<sub>2</sub> esta referenciados en la Resolución "
            "2254 de 2017 del Ministerio de Ambiente y Desarrollo Social MADS, estos parámetros se "
            "comparan con unos límites máximos permisibles en dos tipos distintos de tiempo de exposición, "
            "dichos límites se encuentran en la <strong>Tabla 5</strong>.",

            "Para la medición del parámetro NO<sub>2</sub>, el laboratorio ambiental Corola Ambiental "
            "S.A.S, cuenta con un analizador Horiba APNA-370 Air Monitor, el cual, bajo el principio de "
            "medición de Quimioluminiscencia, realiza la cuantificación del parámetro en tiempo real, "
            "con mediciones horarias. Dicho método está avalado por la Agencia de Protección Ambiental "
            "EPA en su método de referencia RFNA-0506-157.",
        ],
        "fig_key": "fig3_no2",
        "fig_caption": "Figura 3 Exposición Mundial de Dióxido de Nitrógeno NO<sub>2</sub>.",
        "fig_source": "Copernicus Sentinel-5P.2025",
    },
    "CO": {
        "title": "4.3.4 &nbsp; Monóxido de Carbono",
        "paragraphs": [
            "El CO es un gas incoloro no irritante sin olor o sabor. En concentraciones de corta duración "
            "superiores a 5000 mg/m<sup>3</sup>, es un gas tóxico que causa una obstrucción en las vías "
            "respiratorias y puede causar la muerte. El monóxido de carbono se produce de la combustión "
            "incompleta del carbón. Es producido tanto por actividades humanas como por fuentes naturales. "
            "La fuente humana más importante de monóxido de carbono es el tubo de escape de automóviles.",

            "En Colombia el Monóxido de Carbono CO esta referenciado en la Resolución 2254 de 2017 del "
            "Ministerio de Ambiente y Desarrollo Social MADS, estos parámetros se comparan con unos "
            "límites máximos permisibles en dos tipos distintos de tiempo de exposición, dichos límites "
            "se encuentran en la <strong>Tabla 5</strong>.",

            "Para la medición del parámetro CO, el laboratorio ambiental Corola Ambiental S.A.S, cuenta "
            "con un analizador Horiba APMA-370 Air Monitor, el cual, bajo el principio de medición de "
            "Infrarrojo No Dispersivo, realiza la cuantificación del parámetro en tiempo real, con "
            "mediciones horarias. Dicho método está avalado por la Agencia de Protección Ambiental EPA "
            "en su método de referencia RFCA-056-158.",
        ],
        "fig_key": None,
        "fig_caption": None,
        "fig_source": None,
    },
    "O3": {
        "title": "4.3.5 &nbsp; Ozono",
        "paragraphs": [
            "El ozono troposférico no es una sustancia emitida directamente a la atmósfera sino un "
            "contaminante secundario y es el compuesto más representativo de los oxidantes fotoquímicos "
            "y uno de los principales ingredientes del smog urbano. Su proceso de formación comienza con "
            "la emisión del dióxido de nitrógeno (NO<sub>2</sub>) y de hidrocarburos, a los que se les "
            "conoce como los \"precursores\" principales para la formación del ozono, los cuales son "
            "compuestos que reaccionan en la presencia de calor y de luz solar para producir ozono.",

            "En Colombia el Ozono – O<sub>3</sub>, esta referenciado en la Resolución 2254 de 2017 del "
            "Ministerio de Ambiente y Desarrollo Sostenible MADS, este parámetro se compara con un "
            "límite máximo permisible, en un tiempo de exposición octohorario, dicho límite se encuentra "
            "en la <strong>Tabla 5</strong>.",

            "Para la medición del parámetro O<sub>3</sub>, el laboratorio ambiental Corola Ambiental "
            "S.A.S, cuenta con un analizador Horiba APOA-370 Air Monitor, el cual, bajo el principio de "
            "medición de Absorción UV no Dispersiva y avalado por la Agencia de Protección Ambiental EPA "
            "en su método de referencia EQOA-0506-160.",
        ],
        "fig_key": None,
        "fig_caption": None,
        "fig_source": None,
    },
}

# Texto fijo §4.4
TEXT_4_4 = ("No se registraron ninguna adicción, desviación o exclusión a los métodos de ensayo, "
            "presentes en la <strong>Tabla 5</strong>.")

# Texto fijo §4.5
TEXT_4_5 = [
    ("Los períodos de medición reflejarán las variaciones diurnas y nocturnas y los valores máximos "
     "para los casos de mediciones continuas. Las concentraciones de los contaminantes se ven afectadas "
     "por variabilidades temporales de clima, ciclos diurnos en condiciones meteorológicas y patrones de emisión."),
    ("La escala de representatividad depende de la topografía del territorio, de su entorno y de la "
     "meteorología. Entre más pequeña sea la escala de representatividad, más limitados y específicos "
     "son los objetivos de medición, por ejemplo, para medir el impacto de una Fuente puntual es "
     "necesario utilizar escalas pequeñas, esta escala denominada “micro” va desde varios metros "
     "cuadrados hasta cien metros cuadrados y corresponde a puntos ubicados muy cerca de la(s) Fuente(s). "
     "Los usos del suelo tales como residenciales, industriales y de servicio o comercial también se "
     "deben considerar para la ubicación de los puntos de monitoreo."),
]

# Texto fijo §4.2
TEXT_4_2 = ("La duración del muestreo para la determinación de los promedios horarios y Octo-horarios "
            "debe establecerse con base a las condiciones de operación representativas de la actividad y "
            "de la meteorología en el área de afectación, como mínimo se deben monitorear 18 días "
            "calendario por 24 horas en la ejecución de una campaña de calidad del aire.")

# Texto fijo §4.3 intro
TEXT_4_3_INTRO = [
    ("El Reglamento de Protección y Control de la Calidad del Aire adoptado mediante el Decreto 948 de "
     "1995, define y establece los tipos de contaminantes atmosféricos sujetos a reglamentación por "
     "considerarlos causantes de efectos adversos en el medio ambiente, los recursos naturales renovables "
     "y la salud humana."),
    ("El desarrollo de una campaña de calidad del aire, objeto del presente estudio, se enmarca en las "
     "directrices establecidas en el Protocolo de Calidad del Aire: Diseño y Operación adoptado por la "
     "Resolución 2154 de 2010, y los resultados obtenidos se comparan con los límites máximos diarios "
     "establecidos en la Resolución 2254 de 2017 MADS."),
]

# Texto fijo §4.10
TEXT_4_10 = (
    "El proceso de validación de datos implementa un sistema dual que inicia con una validación "
    "automática donde se examina sistemáticamente la integridad de los datos, rangos operativos y "
    "calidad de la señal, asignando banderas específicas a cada dato según su estado de validación. "
    "Estas banderas pueden indicar si el dato es válido, inválido, sospechoso o requiere verificación "
    "adicional, facilitando así el análisis posterior. Los criterios mínimos de aceptación establecen "
    "una captura de datos igual o superior al 75% durante el período de evaluación, considerando los "
    "errores máximos permisibles según las especificaciones técnicas de cada analizador. El sistema "
    "requiere una documentación rigurosa de calibraciones, mantenimientos e intervenciones técnicas, "
    "generando reportes periódicos que aseguran la trazabilidad completa del proceso. Este procedimiento "
    "culmina con una validación secundaria y final realizada por personal calificado, quien revisa las "
    "banderas asignadas y confirma la calidad de la información ambiental, garantizando así la "
    "confiabilidad de los datos para su uso en análisis posteriores y toma de decisiones."
)

VALID_FLAGS = [
    ("V", "S", "Datos válidos"),
    ("O", "S", "Dato Corregido"),
    ("R", "S", "Dato Reconstruido"),
    ("<", "S", "Falta de Datos"),
    ("^", "S", "Valor alto del equipo"),
    ("_", "S", "Valor bajo del equipo"),
    ("/", "S", "Cambio brusco de la concentración"),
]

INVALID_FLAGS = [
    ("-", "N", "Dato perturbado por alarma de analizador"),
    ("C", "N", "Dato perturbado por calibración"),
    ("S", "N", "Dato perturbado por calibración de Span"),
    ("Z", "N", "Dato perturbado por calibración de Zero"),
    ("M", "N", "Dato erróneo por fallo eléctrico"),
    ("D", "N", "Dato perturbado por fallo técnico"),
    ("T", "N", "Dato que no ha sufrido el proceso de validación adecuado"),
    ("#", "N", "Datos insuficientes"),
    ("B", "N", "Mal estado externo"),
    ("E", "N", "Fallo eléctrico"),
    ("F", "N", "Fallo en la corriente eléctrica"),
    ("!", "N", "Señal fuera de rango"),
    ("H", "N", "Valor de prueba"),
    ("P", "N", "Proceso de purga del equipo"),
]

# Texto fijo §4.11
TEXT_4_11 = (
    "Para tener un entorno adecuado para la medición de los parámetros, se exige un control en variables "
    "externas, tal como la temperatura, según el Handbook Volume II, en su numeral 7.2.2, estipula un "
    "rango de operación de temperatura de 25°C ± 5°C, a continuación, se presenta el rango de "
    "temperatura durante el monitoreo."
)

# Texto fijo §4.12
TEXT_4_12 = (
    "El valor de incertidumbre de medición declarada en este informe de resultados es la incertidumbre "
    "expandida, que se obtiene a partir de la respuesta del analizador y del patrón, multiplicado un "
    "factor de cubrimiento k=2.0, a un nivel de confianza aproximado del 95,45 %. El laboratorio Corola "
    "Ambiental S.A.S, se basa en la incertidumbre que se presenta a continuación para los siguientes parámetros:"
)

# Texto fijo §4.13
TEXT_4_13 = (
    "Para obtener datos meteorológicos representativos en los estudios sobre la contaminación del aire "
    "es muy importante ceñirse a los requisitos establecidos en el numeral 6.8.2. del MDsvca. A "
    "continuación, se presentan los criterios de ubicación de los sensores de la estación meteorológica."
)

# Tabla 15 checklist – fija (siempre Sí para Corola)
MET_CHECKLIST = {
    "Sensor de Velocidad y Dirección del Viento": [
        ("Altura del instrumento sobre el suelo", "Si",
         "La altura a la que se ubicó el instrumento anemométrico es de 10 metros sobre el terreno de llano abierto"),
        ("Distancia al obstáculo más cercano", "Si",
         "La distancia entre el anemómetro y cualquier obstáculo fue de por lo menos 10 veces superior a la altura del obstáculo, se ubicó a más de 25 metros."),
    ],
    "Sensor de temperatura": [
        ("Altura del instrumento sobre el suelo", "Si",
         "La altura del sensor de temperatura se presenta a 10 metros del nivel del suelo"),
        ("Distancia al obstáculo más cercano", "Si",
         "Se presenta a más de cuatro veces la altura del obstáculo más cercano (25 metros), presenta exposición directa al sol y al viento y libre de sombra."),
        ("Otros criterios", "Si",
         "El sensor se ubica a más de 10 metros de áreas pavimentadas, se ubica sobre un suelo cubierto por una capa natural de gravilla y lejos de aguas estancadas"),
    ],
    "Sensor de Humedad Relativa": [
        ("Altura del instrumento sobre el suelo", "Si",
         "La altura del instrumento se presenta a más de 10 metros sobre el nivel medio del terreno"),
        ("Distancia al obstáculo más cercano", "Si",
         "La distancia del sensor y cualquier obstáculo se presentó a más de 4 veces la altura del obstáculo más cercano"),
        ("Ubicación del instrumento", "Si",
         "El montaje de la estación meteorológica garantiza que el sensor está protegido de la lluvia y el viento, adicional se garantiza que no se presenta un microclima"),
    ],
    "Sensor de Precipitación": [
        ("Altura del instrumento sobre el suelo", "Si",
         "El instrumento se ubica a una altura superior de 10 metros medido sobre el nivel medio del terreno"),
        ("Distancia al obstáculo más cercano", "Si",
         "La distancia del sensor y cualquier obstáculo se presentó a más de 2 veces la altura del obstáculo más cercano"),
        ("Ubicación del instrumento", "Si",
         "Se ubicó en un sitio donde no se presentan laderas o techos de edificaciones."),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 11pt;
    color: #000;
    background: #fff;
    line-height: 1.45;
}
/* ── Header de página ── */
.page-header {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 18px;
}
.page-header td { border: 1px solid #999; padding: 4px 8px; vertical-align: middle; }
.page-header .logo-cell { width: 140px; }
.page-header .title-cell { text-align: center; font-weight: bold; font-size: 11pt; }
.page-header .code-cell  { text-align: center; font-size: 10pt; }
.page-header .client-logo-cell { width: 120px; text-align: center; }
/* ── Footer de página ── */
.page-footer {
    width: 100%;
    border-collapse: collapse;
    margin-top: 30px;
    font-size: 9pt;
    color: #1a5276;
}
.page-footer td { border: 1px solid #1a5276; padding: 3px 6px; }
/* ── Cortes de página ── */
.page-break { page-break-before: always; }
/* ── Portada ── */
.cover-page {
    text-align: center;
    min-height: 1050px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    padding: 40px 60px;
    position: relative;
}
.cover-badge {
    position: absolute;
    top: 0;
    right: 0;
    background: #1a3a5c;
    color: white;
    font-weight: bold;
    font-size: 14pt;
    padding: 12px 20px;
}
.cover-logo { margin-bottom: 20px; }
.cover-title { font-size: 15pt; font-weight: bold; margin: 16px 0 10px; }
.cover-pollutants { font-size: 13pt; margin-bottom: 18px; }
.cover-client { font-size: 11pt; font-weight: bold; margin-bottom: 6px; }
.cover-code { font-size: 11pt; margin: 12px 0; }
.cover-period { font-size: 13pt; font-weight: bold; margin-bottom: 6px; }
.cover-location { font-size: 12pt; font-weight: bold; margin-bottom: 20px; }
.cover-logos-row {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 40px;
    margin: 14px 0;
}
.cover-photo { width: 100%; max-width: 750px; margin-top: 20px; }
/* ── Página de control ── */
.control-intro { text-align: justify; margin-bottom: 24px; }
.control-logos { display: flex; gap: 24px; align-items: center; margin: 20px 0 30px; flex-wrap: wrap; }
.section-title { font-weight: bold; text-align: center; font-size: 13pt; margin: 24px 0 20px; }
.control-signatures {
    display: flex;
    justify-content: space-around;
    margin: 24px 0;
}
.sig-block { text-align: center; min-width: 160px; }
.sig-label { font-weight: bold; font-size: 11pt; margin-bottom: 50px; }
.sig-name { font-weight: bold; border-top: 1px solid #000; padding-top: 6px; }
.sig-title { font-size: 10pt; }
/* ── Tablas generales ── */
table.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 10pt;
    margin: 14px 0;
}
table.data-table th, table.data-table td {
    border: 1px solid #999;
    padding: 5px 8px;
    vertical-align: middle;
}
table.data-table th {
    background: #145a32;
    color: #fff;
    font-weight: bold;
    text-align: center;
}
table.data-table td.label { font-weight: bold; }
table.data-table caption {
    font-size: 10pt;
    font-style: normal;
    font-weight: bold;
    text-align: center;
    margin-bottom: 6px;
    caption-side: top;
}
/* ── Tabla de cumplimiento normativo (Tablas 2-4) ── */
.compliance-section th.group { background: #1a5276; }
.pct-100 { background: #d5f5e3; }
/* ── Encabezados de sección ── */
h1 { font-size: 13pt; font-weight: bold; text-align: center; margin: 24px 0 16px; }
h2 { font-size: 12pt; font-weight: bold; margin: 20px 0 12px; }
h3 { font-size: 11pt; font-weight: bold; margin: 16px 0 10px; }
p  { text-align: justify; margin-bottom: 10px; }
/* ── Tabla de contenido / Listas ── */
.toc-table { width: 100%; border-collapse: collapse; font-size: 10pt; }
.toc-table tr:nth-child(even) { background: #f9f9f9; }
.toc-table td { padding: 3px 6px; }
.toc-indent-1 { padding-left: 20px !important; }
.toc-indent-2 { padding-left: 40px !important; }
/* ── Ficha Técnica ── */
.ficha-table { width: 100%; border-collapse: collapse; font-size: 10pt; margin: 14px 0; }
.ficha-table th { background: #145a32; color: #fff; text-align: center; padding: 5px; font-size: 10pt; }
.ficha-table td { border: 1px solid #aaa; padding: 5px 8px; }
.ficha-table .row-header { background: #d5f5e3; font-weight: bold; text-align: center; }
/* ── Fotos ── */
.photo-grid { display: flex; flex-wrap: wrap; gap: 12px; justify-content: flex-start; margin: 14px 0; }
.photo-cell { flex: 0 0 calc(50% - 6px); text-align: center; }
.photo-cell img { width: 100%; max-height: 280px; object-fit: cover; }
.photo-caption { font-size: 9pt; text-align: center; margin-top: 4px; }
/* ── Glosario ── */
.gloss-term { font-weight: bold; }
/* ── Fuente de figura/tabla ── */
.fig-caption { text-align: center; font-size: 10pt; font-weight: bold; margin-top: 6px; }
.fig-source  { text-align: center; font-size: 9pt; font-weight: bold; margin-bottom: 14px; }
"""


# ─────────────────────────────────────────────────────────────────────────────
# COMPONENTES HTML REUTILIZABLES
# ─────────────────────────────────────────────────────────────────────────────

def _page_header(cfg: dict) -> str:
    corola_logo = _img(cfg.get("corola_logo_path", ""), "height:40px;", "Corola Ambiental")
    client_logo = _img(cfg.get("lab_partner", {}).get("logo_path", ""), "height:40px;",
                       cfg.get("lab_partner", {}).get("name", ""))
    return f"""
<table class="page-header">
  <tr>
    <td class="logo-cell">{corola_logo}</td>
    <td class="title-cell">INFORME DE RESULTADOS</td>
    <td class="client-logo-cell">{client_logo}</td>
  </tr>
  <tr>
    <td></td>
    <td class="code-cell">{cfg["report_code"]}</td>
    <td></td>
  </tr>
</table>"""


def _page_footer() -> str:
    return """
<table class="page-footer">
  <tr>
    <td>Corola Ambiental S.A.S</td>
    <td style="text-align:right">Código: F02-PT.5.10</td>
  </tr>
  <tr>
    <td>Carrera 52 #45ª – 28</td>
    <td style="text-align:right">Fecha: 2015.11.03</td>
  </tr>
  <tr>
    <td>Tel: (1) 358-4365</td>
    <td style="text-align:right">Versión: 01</td>
  </tr>
  <tr>
    <td><a href="http://www.corolaambiental.com" style="color:#1a5276">www.corolaambiental.com</a></td>
    <td style="text-align:right; color:#1a5276;">Página</td>
  </tr>
</table>"""


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN: PORTADA
# ─────────────────────────────────────────────────────────────────────────────

def _build_cover(cfg: dict) -> str:
    p = cfg["period"]
    loc = cfg["location"]
    fc = cfg.get("final_client", {})
    lab = cfg.get("lab_partner", {})
    badge = cfg.get("report_type", "CA")

    corola_logo = _img(cfg.get("corola_logo_path", ""), "height:70px;", "Corola Ambiental")
    client_logo = _img(lab.get("logo_path", ""), "height:60px;", lab.get("name", ""))
    cover_photo = _img(cfg.get("cover_photo_path", ""), "width:100%;max-height:400px;object-fit:cover;", "Foto portada")

    pollutants_str = " – ".join([
        "PM<sub>10</sub>", "PM<sub>2.5</sub>", "SO<sub>2</sub>",
        "NO<sub>2</sub>", "CO", "O<sub>3</sub>"
    ])

    period_label = (f"{p.get('month_start', p['start_date'][:7].upper())} – "
                    f"{p.get('month_end', p['end_date'][:7].upper())}"
                    if p.get("period_label")
                    else f"{_fmt_date(p['start_date']).upper()} – {_fmt_date(p['end_date']).upper()}")
    if p.get("period_label"):
        period_label = p["period_label"]

    return f"""
<div class="cover-page">
  <div class="cover-badge">{badge}</div>
  <div class="cover-logo">{corola_logo}</div>
  <div class="cover-title">{cfg.get('title', 'MONITOREO CALIDAD DEL AIRE INDUSTRIAL')}</div>
  <div class="cover-pollutants">{pollutants_str}</div>
  <div class="cover-client">{fc.get('name', '')}</div>
  <div class="cover-client">{lab.get('name', '')}</div>
  <div class="cover-client">{fc.get('station_name', '')}</div>
  <div class="cover-code">{cfg['report_code']}</div>
  <div class="cover-logos-row">
    {client_logo}
    <div>
      <div class="cover-period">{period_label}</div>
    </div>
    {_img(cfg.get("client_logo_path",""), "height:60px;", fc.get("name",""))}
  </div>
  <div class="cover-location">{loc.get('municipality', '')}, {loc.get('department', '')}</div>
  <div class="cover-photo">{cover_photo}</div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN: PÁGINA DE CONTROL
# ─────────────────────────────────────────────────────────────────────────────

def _build_control_page(cfg: dict) -> str:
    pers = cfg.get("personnel", {})
    rev = cfg.get("revision", {})

    def sig(role_label: str, person: dict) -> str:
        name = person.get("name", "")
        title = person.get("title", "").replace("\n", "<br>")
        return f"""
        <div class="sig-block">
          <div class="sig-label">{role_label}</div>
          <div class="sig-name">{name}</div>
          <div class="sig-title">{title}</div>
        </div>"""

    return f"""
<div class="page-break">
{_page_header(cfg)}
<p class="control-intro">
El siguiente informe de Calidad del Aire, ha sido elaborado y revisado por profesionales competentes
y calificados bajo normatividad <strong>ISO/IEC 17025</strong>; así como, para la realización del
monitoreo se utilizaron analizadores aprobados por ente nacionales e internacionales, tales como:
<strong>Instituto de Hidrología, Meteorología y Estudios Ambientales - IDEAM</strong>,
<strong>Environmental Protection Agency – EPA</strong> &amp;
<strong>Asociación Española de Normalización UNE-EN</strong>.
</p>

<div class="section-title">COLABORADORES</div>

<div class="control-signatures">
{sig("REALIZÓ", pers.get("realizo", {}))}
{sig("REVISÓ", pers.get("reviso", {}))}
</div>
<div class="control-signatures">
{sig("APROBÓ", pers.get("aprobo", {}))}
</div>

<table class="data-table" style="margin-top:30px;">
  <caption>CONTROL DE REVISIONES</caption>
  <thead>
    <tr><th>Revisión</th><th>Fecha</th><th>Comentarios</th><th>Realizo</th></tr>
  </thead>
  <tbody>
    <tr>
      <td style="text-align:center">{rev.get("number", 1)}</td>
      <td style="text-align:center">{rev.get("date", "")}</td>
      <td style="text-align:center">{rev.get("comments", "Ninguno")}</td>
      <td style="text-align:center">{rev.get("author", "")}</td>
    </tr>
  </tbody>
</table>
{_page_footer()}
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN: TABLA DE CONTENIDO
# ─────────────────────────────────────────────────────────────────────────────

def _build_toc(cfg: dict) -> str:
    stations = cfg.get("stations", [])
    rows = [
        ("1.", "DATOS BÁSICOS", ""),
        ("1.1", "Información empresa solicitante del monitoreo", ""),
        ("1.2", "Información empresa encargada del monitoreo", ""),
        ("1.3", "Analizadores empleados para la ejecución del monitoreo", ""),
        ("2.", "INTRODUCCIÓN", ""),
        ("3.", "OBJETIVOS", ""),
        ("3.1", "Objetivo general", ""),
        ("3.2", "Objetivos específicos", ""),
        ("4.", "GENERALIDADES", ""),
        ("4.1", "Planeación del monitoreo", ""),
        ("4.2", "Tiempo de toma de muestra y duración del muestreo", ""),
        ("4.3", "Contaminantes por medir, límite normativo y método referencia", ""),
        ("4.3.1", "Material Particulado", ""),
        ("4.3.2", "Dióxido de Azufre", ""),
        ("4.3.3", "Dióxido de Nitrógeno", ""),
        ("4.3.4", "Monóxido de Carbono", ""),
        ("4.3.5", "Ozono", ""),
        ("4.4", "Adiciones – Desviaciones y/o Exclusiones del Método de Ensayo", ""),
        ("4.5", "Condiciones de Monitoreo", ""),
        ("4.6", "Descripción de las principales fuentes de emisión y receptores potenciales", ""),
        ("4.7", "Descripción puntos de monitoreo", ""),
        ("4.8", "Fichas técnicas de estaciones de monitoreo", ""),
    ]
    for i, st in enumerate(stations, 1):
        rows.append((f"4.8.{i}", f"Est {i}. {st.get('code','')}", ""))
    rows += [
        ("4.9", "Cronología del monitoreo", ""),
        ("4.10", "Validación de datos", ""),
        ("4.11", "Condiciones ambientales", ""),
        ("4.12", "Incertidumbre de datos", ""),
        ("4.13", "Micro Localización de Estación Meteorológica", ""),
        ("5.", "METEOROLOGÍA", ""),
        ("6.", "RESULTADOS Y ANÁLISIS", ""),
        ("7.", "ÍNDICES DE CALIDAD DEL AIRE – ICA", ""),
        ("8.", "CONCLUSIONES", ""),
        ("10.", "BIBLIOGRAFÍA", ""),
    ]

    def indent(num: str) -> str:
        dots = num.count(".")
        if dots == 0:
            return ""
        if dots == 1:
            return "toc-indent-1"
        return "toc-indent-2"

    rows_html = "\n".join(
        f'<tr><td class="{indent(n)}">{n}</td><td class="{indent(n)}">{title}</td><td style="text-align:right">{pg}</td></tr>'
        for n, title, pg in rows
    )

    return f"""
<div class="page-break">
{_page_header(cfg)}
<h1>TABLA DE CONTENIDO</h1>
<table class="toc-table">
  <tbody>{rows_html}</tbody>
</table>
{_page_footer()}
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN: LISTAS (Anexos, Figuras, Tablas, Gráficas)
# ─────────────────────────────────────────────────────────────────────────────

def _build_lists(cfg: dict) -> str:
    annexes = [
        ("ANEXO 1", "REPORTE DE RESULTADOS"),
        ("ANEXO 2", "RESOLUCIÓN DE ACREDITACIÓN IDEAM"),
        ("ANEXO 3", "CERTIFICACIÓN DE ANALIZADORES"),
        ("ANEXO 4", "METEOROLOGÍA."),
        ("ANEXO 5", "FORMATO DE CAMPO."),
        ("ANEXO 6", "GDB."),
        ("ANEXO 7", "CARTOGRAFIA"),
    ]

    def list_block(title: str, items: list) -> str:
        rows = "".join(
            f'<tr><td style="font-style:italic;">{a}</td><td style="text-align:right">{b}</td></tr>'
            for a, b in items
        )
        return f"<h1>{title}</h1><table class='toc-table'><tbody>{rows}</tbody></table>"

    return f"""
<div class="page-break">
{_page_header(cfg)}
{list_block("LISTA DE ANEXOS", [(a, b) for a, b in annexes])}
<br>
<p><em>(La lista completa de Figuras, Tablas y Gráficas se genera automáticamente al ensamblar el informe completo.)</em></p>
{_page_footer()}
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN: GLOSARIO Y ABREVIATURAS
# ─────────────────────────────────────────────────────────────────────────────

def _build_glossary(cfg: dict) -> str:
    terms_html = "".join(
        f"<p><span class='gloss-term'>{term}:</span> {defn}</p>\n"
        for term, defn in GLOSSARY
    )
    abbr_html = "".join(
        f"<p><strong>{abbr}:</strong> &nbsp; {meaning}</p>\n"
        for abbr, meaning in ABBREVIATIONS
    )
    return f"""
<div class="page-break">
{_page_header(cfg)}
<h1>GLOSARIO</h1>
{terms_html}
{_page_footer()}
</div>
<div class="page-break">
{_page_header(cfg)}
<h1>LISTA DE ABREVIATURAS</h1>
{abbr_html}
{_page_footer()}
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 1: DATOS BÁSICOS
# ─────────────────────────────────────────────────────────────────────────────

def _build_section1(cfg: dict) -> str:
    client = cfg.get("client", {})
    corola = {
        "Nombre o Razón Social": "Corola Ambiental S.A.S",
        "NIT": "900690275-2",
        "Persona de contacto": "Luis Olaya",
        "Dirección de la empresa": "Cra 52 # 45ª - 28",
        "Teléfono": "(1) 358 43 65 (+57) 313 4524660",
        "Municipio/Departamento": "Bogotá D.C.",
        "Correo electrónico": "corola.ambiental@gmail.com",
        "Acreditación IDEAM": cfg.get("ideam_acreditacion", "Resolución N°0920 de 2024 (Vigencia hasta septiembre 2028)"),
    }

    def info_table(title: str, data: dict, source: str) -> str:
        rows = "".join(
            f"<tr><td class='label'>{k}</td><td>{v}</td></tr>"
            for k, v in data.items()
        )
        return f"""
<h2>{title}</h2>
<table class="data-table">
  <tbody>{rows}</tbody>
</table>
<p style="text-align:right;font-size:9pt;"><strong>Fuente:</strong> {source}</p>"""

    client_data = {
        "Nombre o Razón Social": client.get("name", ""),
        "NIT": client.get("NIT", ""),
        "Persona de contacto": client.get("contact", ""),
        "Dirección de la empresa": client.get("address", ""),
        "Teléfono": client.get("phone", ""),
        "Municipio/Departamento": client.get("municipality_dept", ""),
        "Correo electrónico": client.get("email", ""),
        "Actividad principal de la empresa": client.get("activity", ""),
    }

    year = cfg["period"]["end_date"][:4]

    return f"""
<div class="page-break">
{_page_header(cfg)}
<h1>1. &nbsp; DATOS BÁSICOS</h1>
{info_table("1.1 &nbsp; INFORMACIÓN EMPRESA SOLICITANTE DEL MONITOREO",
            client_data, f"Corola Ambiental S.A.S – {year}.")}
{info_table("1.2 &nbsp; INFORMACIÓN EMPRESA ENCARGADA DEL MONITOREO",
            corola, f"Corola Ambiental S.A.S – {year}.")}
<h2>1.3 &nbsp; ANALIZADORES EMPLEADOS PARA LA EJECUCIÓN DEL MONITOREO</h2>
<p>Equipo(s) utilizado(s): {cfg.get("analyzers_text", "")}.</p>
{_page_footer()}
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 2: INTRODUCCIÓN
# ─────────────────────────────────────────────────────────────────────────────

def _compliance_table(table_num: str, title: str, rows_data: list, groups: list) -> str:
    """
    rows_data: list of {id, code, pollutants: {name: {validas, excedencias}}}
    groups: list of pollutant group names to render
    """
    group_headers = "".join(
        f'<tr><th colspan="5" class="group">{g}</th></tr>'
        f'<tr><th>ID</th><th>ESTACIÓN</th><th>Muestras Válidas</th><th># Excedencias</th><th>Cumplimiento Normativo</th></tr>'
        for g in groups
    )

    def station_rows(pollutant_name: str) -> str:
        html = ""
        for row in rows_data:
            p_data = row.get("pollutants", {}).get(pollutant_name, {})
            validas = p_data.get("validas", "–")
            exc = p_data.get("excedencias", 0)
            pct = "100%" if exc == 0 else f"{p_data.get('cumplimiento', '–')}"
            css = "pct-100" if exc == 0 else ""
            html += f"""
            <tr>
              <td style="text-align:center">{row.get('id','')}</td>
              <td style="text-align:center">{row.get('code','')}</td>
              <td style="text-align:center">{validas}</td>
              <td style="text-align:center">{exc}</td>
              <td style="text-align:center" class="{css}">{pct}</td>
            </tr>"""
        return html

    body = ""
    for g in groups:
        body += f'<tr><th colspan="5" class="group" style="background:#1a5276;color:#fff">{g}</th></tr>'
        body += f'<tr><th>ID</th><th>ESTACIÓN</th><th>Muestras Válidas</th><th># Excedencias</th><th>Cumplimiento Normativo</th></tr>'
        body += station_rows(g)

    return f"""
<table class="data-table compliance-section">
  <caption>Tabla {table_num}. {title}</caption>
  <tbody>{body}</tbody>
</table>"""


def _build_section2(cfg: dict) -> str:
    p = cfg["period"]
    fc = cfg.get("final_client", {})
    loc = cfg["location"]
    year = p["end_date"][:4]
    compliance = cfg.get("compliance", {})

    pollutants_str = ("Material Particulado PM<sub>10</sub> y PM<sub>2,5</sub>, "
                      "Dióxido de Azufre SO<sub>2</sub>, Dióxido de Nitrógeno NO<sub>2</sub>, "
                      "Monóxido de Carbono CO y Ozono O<sub>3</sub>")

    intro_p1 = (
        f"La empresa {cfg.get('client', {}).get('name', '')} subcontrató al laboratorio ambiental "
        f"Corola Ambiental S.A.S. para desarrollar un monitoreo de calidad del aire, referente a los "
        f"contaminantes criterio establecidos en la Resolución 2254 de 2017, como {pollutants_str}, "
        f"en el área de influencia de {fc.get('station_name', 'la estación')}, ubicada en el municipio "
        f"de {loc.get('municipality', '')}, departamento de {loc.get('department', '')}. "
        f"La campaña de monitoreo de calidad del aire se realizó en época {p.get('season', 'seca')}, "
        f"{_period_text(p)}, con mediciones continuas horarias por contaminante monitoreado, "
        f"desde las 00:00 a las 23:00 horas."
    )

    client_description = fc.get("description", "")

    # Tabla 1 – estaciones
    stations = cfg.get("stations", [])
    station_rows = "".join(f"""
    <tr>
      <td style="text-align:center">Est {i+1}</td>
      <td style="text-align:center">{st.get('code','')}</td>
      <td>{st.get('description', '')}</td>
      <td style="text-align:center">{st.get('altitude_msnm', '')}</td>
      <td style="text-align:center">{st.get('norte', '')}</td>
      <td style="text-align:center">{st.get('este', '')}</td>
      <td style="text-align:center">{st.get('parameters_measured', pollutants_str)}</td>
    </tr>""" for i, st in enumerate(stations))

    tabla1 = f"""
<table class="data-table">
  <caption>Tabla 1. Identificación estación monitoreo de calidad del aire</caption>
  <thead>
    <tr>
      <th rowspan="2">ID</th>
      <th rowspan="2">Estación de monitoreo</th>
      <th rowspan="2">Descripción</th>
      <th rowspan="2">Altitud m</th>
      <th colspan="2">Coordenadas Origen Nacional</th>
      <th rowspan="2">Parámetros Medidos</th>
    </tr>
    <tr><th>Norte</th><th>Este</th></tr>
  </thead>
  <tbody>{station_rows}</tbody>
</table>
<p style="text-align:right;font-size:9pt;"><strong>Fuente:</strong> Corola Ambiental S.A.S – {year}.</p>"""

    # Tablas 2, 3, 4 de cumplimiento
    t2 = _compliance_table("2", "Cumplimiento Normativo Horario – Res 2254/2017",
                           compliance.get("horario", []),
                           compliance.get("grupos_horario",
                                         ["Dióxido de Azufre - SO₂", "Dióxido de Nitrógeno - NO₂", "Monóxido de Carbono - CO"]))
    t3 = _compliance_table("3", "Cumplimiento Normativo 8 horas – Res 2254/2017",
                           compliance.get("octohorario", []),
                           compliance.get("grupos_8h", ["Monóxido de Carbono - CO", "Ozono – O₃"]))
    t4 = _compliance_table("4", "Cumplimiento Normativo 24 horas – Res 2254/2017",
                           compliance.get("diario", []),
                           compliance.get("grupos_24h",
                                         ["Material Particulado - PM₁₀", "Material Particulado - PM₂,₅",
                                          "Dióxido de Azufre - SO₂"]))

    acreditacion_text = (
        f"El día 02 de septiembre de 2024 el Instituto de Hidrología, Meteorología y Estudios Ambientales – IDEAM, "
        f"profirió la resolución 0920 de 2024, por la cual le otorga la acreditación bajo la NTC ISO/IEC 17025:2017 "
        f"a la sociedad COROLA AMBIENTAL S.A.S. con NIT 900690275-2, ubicado en la Carrera 52 No. 45 A – 28 de la "
        f"ciudad de Bogotá D.C, para producir información cuantitativa física y química, para los estudios o análisis "
        f"ambientales requeridos por las Autoridades Ambientales competentes, para los parámetros en la matriz de "
        f"calidad del aire de Azufre Total Reducido, Amoniaco, Sulfuro de Hidrógeno, Material Particulado "
        f"PM<sub>10</sub> & PM<sub>2,5</sub>, Dióxido de Azufre, Dióxido de Nitrógeno, Monóxido de Carbono y Ozono, "
        f"por analizadores automáticos – medición directa – en tiempo real."
    )

    return f"""
<div class="page-break">
{_page_header(cfg)}
<h1>2. &nbsp; INTRODUCCIÓN</h1>
<p>{intro_p1}</p>
<p>{client_description}</p>
<p>A continuación, se presenta la información general de las estaciones monitoreadas.</p>
{tabla1}
<p>El artículo 2 de la resolución 672 de 2014, modifica el artículo 16 de la resolución 1541 de 2013 el cual
cita: <u>"Realización de mediciones directas</u>. El responsable de realizar la toma de muestras, análisis de
laboratorio y medición directa en campo de emisiones para verificar el cumplimiento de los niveles permisibles
de calidad del aire o niveles permisibles de inmisión de sustancias o mezclas de sustancias de olores ofensivos,
deberá estar acreditado de conformidad con lo establecido en el Decreto 1600 de 1994, modificado por el Decreto
2570 de 2006 o las normas que los modifiquen, adicionen o sustituyan."</p>
<p>{acreditacion_text}</p>
<p>En cumplimiento con el artículo 2 de la resolución 2254 de 2017 del Ministerio de Medio Ambiente y Desarrollo
Sostenible – MADS; se muestran los resultados obtenidos para la campaña de monitoreo. En la <strong>Tabla 2</strong>
a la <strong>Tabla 4</strong> se reflejan cumplimiento total de los límites máximos permisibles para los parámetros
PM<sub>10</sub>, PM<sub>2,5</sub>, NO<sub>2</sub>, SO<sub>2</sub>, CO y O<sub>3</sub>.</p>
{t2}{t3}{t4}
{_page_footer()}
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 3: OBJETIVOS
# ─────────────────────────────────────────────────────────────────────────────

def _build_section3(cfg: dict) -> str:
    p = cfg["period"]
    loc = cfg["location"]
    fc = cfg.get("final_client", {})
    stations = cfg.get("stations", [])
    n_st = len(stations)
    days = p["duration_days"]

    pollutants_str = ("Material Particulado (PM<sub>10</sub> y PM<sub>2,5</sub>), "
                      "Dióxido de Azufre (SO<sub>2</sub>), Dióxido de Nitrógeno (NO<sub>2</sub>), "
                      "Monóxido de Carbono (CO) y Ozono (O<sub>3</sub>)")

    objetivo_general = (
        f"Realizar un estudio de calidad del aire en lo referente a los contaminantes criterio, "
        f"tales como {pollutants_str}, en el área de influencia de {fc.get('station_name', 'la estación')}, "
        f"ubicada en el municipio de {loc.get('municipality','')}, departamento de {loc.get('department','')}, "
        f"durante el periodo comprendido {_period_text(p)}, con mediciones diarias."
    )

    especificos = [
        (f"Determinar las concentraciones de Material Particulado PM<sub>10</sub> & PM<sub>2,5</sub>, "
         f"Dióxido de Nitrógeno NO<sub>2</sub>, Monóxido de Carbono CO y Ozono O<sub>3</sub>, "
         f"mediante la ejecución del estudio de calidad del aire, en {n_st} estaciones de monitoreo."),
        (f"Verificar el cumplimiento normativo para un tiempo de exposición de 1 hora para los parámetros "
         f"SO<sub>2</sub>, NO<sub>2</sub> y CO, en un estudio de calidad del aire durante {days} días, "
         f"con mediciones diarias, en {n_st} estaciones de monitoreo."),
        (f"Verificar el cumplimiento normativo para un tiempo de exposición de 8 horas para los parámetros "
         f"CO y O<sub>3</sub>, en un estudio de calidad del aire durante {days} días, con mediciones "
         f"diarias, en {n_st} estaciones de monitoreo."),
        (f"Verificar el cumplimiento normativo para un tiempo de exposición de 24 horas para los parámetros "
         f"PM<sub>10</sub>, PM<sub>2,5</sub> y SO<sub>2</sub>, en un estudio de calidad del aire durante "
         f"{days} días, con mediciones diarias, en {n_st} estaciones de monitoreo."),
        ("Determinar los índices de la calidad del aire, según Resolución 2254 de 2017, de manera que sea "
         "posible establecer la afectación de los contaminantes criterio sobre la salud humana."),
    ]

    bullets = "".join(f"<li style='margin-bottom:10px;text-align:justify;'>{e}</li>" for e in especificos)

    return f"""
<div class="page-break">
{_page_header(cfg)}
<h1>3. &nbsp; OBJETIVOS</h1>
<h2>3.1 &nbsp; OBJETIVO GENERAL</h2>
<p>{objetivo_general}</p>
<h2>3.2 &nbsp; OBJETIVOS ESPECÍFICOS</h2>
<ul style="padding-left:24px;margin-top:10px;">{bullets}</ul>
{_page_footer()}
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 4: GENERALIDADES
# ─────────────────────────────────────────────────────────────────────────────

def _build_tabla5() -> str:
    rows = ""
    for p in POLLUTANT_TABLE:
        lim_rows = p["limites"]
        first = True
        for val, tiempo in lim_rows:
            if first:
                rows += f"""
        <tr>
          <td rowspan="{len(lim_rows)}" style="text-align:center">{p["contaminante"]}</td>
          <td rowspan="{len(lim_rows)}" style="text-align:center">{p["principio"]}</td>
          <td rowspan="{len(lim_rows)}">{p["metodo"]}</td>
          <td style="text-align:center">{val}</td>
          <td style="text-align:center">{tiempo}</td>
        </tr>"""
                first = False
            else:
                rows += f"""
        <tr>
          <td style="text-align:center">{val}</td>
          <td style="text-align:center">{tiempo}</td>
        </tr>"""
    return f"""
<table class="data-table">
  <caption>Tabla 5. Contaminantes Medidos</caption>
  <thead>
    <tr>
      <th rowspan="2">Contaminante</th>
      <th rowspan="2">Principio de medición</th>
      <th rowspan="2">Método de referencia</th>
      <th colspan="2">Límite Normativo</th>
    </tr>
    <tr><th>Nivel Máximo Permisible μg/m³</th><th>Tiempo de Exposición</th></tr>
  </thead>
  <tbody>{rows}</tbody>
</table>"""


def _build_pollutant_section(key: str, cfg: dict, fig_paths: dict) -> str:
    d = POLLUTANT_DESCRIPTIONS[key]
    paras = "".join(f"<p>{t}</p>" for t in d["paragraphs"])
    fig_html = ""
    if d["fig_key"] and d["fig_caption"]:
        fig_path = fig_paths.get(d["fig_key"], "")
        fig_img = _img(fig_path, "width:100%;max-width:700px;display:block;margin:auto;", d["fig_caption"])
        fig_html = f"""
<div style="text-align:center;margin:14px 0;">
  <p class="fig-caption">{d["fig_caption"]}</p>
  {fig_img}
  <p class="fig-source"><strong>Fuente:</strong> {d["fig_source"]}</p>
</div>"""
    return f"<h3>{d['title']}</h3>{paras}{fig_html}"


def _build_ficha_tecnica(st: dict, station_num: int, year: str) -> str:
    equipos_rows = "".join(
        f"<tr><td>{e.get('equipo','')}</td><td style='text-align:center'>{e.get('parametro','')}</td>"
        f"<td style='text-align:center'>{e.get('codigo_interno','')}</td><td style='text-align:center'>{e.get('sn','')}</td></tr>"
        for e in st.get("equipos", [])
    )

    photos_aerial = _img(st.get("photo_aerial_path", ""),
                         "width:100%;max-height:320px;object-fit:cover;", "Vista aérea estación")
    field_photos = "".join(
        f'<td style="width:33%;text-align:center;padding:4px;">{_img(p, "width:100%;max-height:180px;object-fit:cover;", "")}</td>'
        for p in st.get("photos_field", [])
    )

    return f"""
<div class="page-break">
<h3>4.8.{station_num} &nbsp; Est {station_num}. {st.get('code','')}</h3>
<table class="ficha-table">
  <caption style="font-weight:bold;text-align:center;margin-bottom:6px;">
    Tabla {6 + station_num}. Ficha Técnica Estación {station_num} – {st.get('code','')}
  </caption>
  <tbody>
    <tr><th colspan="4">ESTACIÓN {station_num}: {st.get('code','')}</th></tr>
    <tr><td colspan="4"><strong>OBJETIVO:</strong> {st.get('objective','')}</td></tr>
    <tr><td class="row-header" colspan="4">TIPO ESTACION</td></tr>
    <tr><td colspan="4" style="text-align:center">{st.get('type','')}</td></tr>
    <tr><td class="row-header" colspan="4">UBICACIÓN</td></tr>
    <tr><td class="row-header" colspan="4">Coordenadas Geográficas</td></tr>
    <tr><td colspan="2" style="text-align:center"><strong>Latitud</strong></td><td colspan="2" style="text-align:center"><strong>Longitud</strong></td></tr>
    <tr><td colspan="2" style="text-align:center">{st.get('latitude','')}</td><td colspan="2" style="text-align:center">{st.get('longitude','')}</td></tr>
    <tr><td class="row-header" colspan="4">Origen Nacional</td></tr>
    <tr><td colspan="2" style="text-align:center"><strong>Norte</strong></td><td colspan="2" style="text-align:center"><strong>Este</strong></td></tr>
    <tr><td colspan="2" style="text-align:center">{st.get('norte','')}</td><td colspan="2" style="text-align:center">{st.get('este','')}</td></tr>
    <tr>
      <td><strong>Altitud</strong></td><td>{st.get('altitude_msnm','')} msnm</td>
      <td><strong>Presión Barométrica</strong></td><td>{st.get('presion_barometrica','')}</td>
    </tr>
    <tr>
      <td><strong>Ancho de Vía</strong></td><td>{st.get('ancho_via','')}</td>
      <td><strong>Dirección Predominante del Viento</strong></td><td>{st.get('dir_viento_predominante','')}</td>
    </tr>
    <tr>
      <td><strong>Tiempo</strong></td><td>{st.get('tiempo','')}</td>
      <td><strong>Tipo Conexión:</strong></td><td>{st.get('tipo_conexion','')}</td>
    </tr>
    <tr>
      <td><strong>Fecha de inicio</strong></td><td>{st.get('fecha_inicio','')}</td>
      <td><strong>Fecha de finalización</strong></td><td>{st.get('fecha_finalizacion','')}</td>
    </tr>
    <tr><td colspan="4" style="text-align:center"><strong>Número de muestras:</strong> {st.get('num_muestras','')}</td></tr>
    <tr><td class="row-header" colspan="4">EQUIPOS DE MEDICION</td></tr>
    <tr><th>EQUIPO</th><th>PARAMETRO</th><th>CODIGO INTERNO</th><th>SN</th></tr>
    {equipos_rows}
  </tbody>
</table>
<p style="text-align:right;font-size:9pt;"><strong>Fuente:</strong> Corola Ambiental S.A.S – {year}.</p>
<table style="width:100%;border-collapse:collapse;margin:14px 0;">
  <thead><tr><th colspan="2" style="background:#145a32;color:#fff;padding:6px;">REGISTRO FOTOGRAFICO</th></tr></thead>
  <tbody>
    <tr><td colspan="2" style="padding:6px;">{photos_aerial}</td></tr>
    <tr>{field_photos}</tr>
  </tbody>
</table>
<p style="text-align:center;font-size:9pt;"><strong>Fuente:</strong> Corola Ambiental S.A.S – {year}.</p>
</div>"""


def _build_section4(cfg: dict) -> str:
    p = cfg["period"]
    fc = cfg.get("final_client", {})
    loc = cfg["location"]
    year = p["end_date"][:4]
    stations = cfg.get("stations", [])
    fig_paths = cfg.get("figure_paths", {})
    sources = cfg.get("emission_sources", [])
    cronograma = cfg.get("cronograma", [])
    cond_amb = cfg.get("condiciones_ambientales", [])
    incert = cfg.get("incertidumbre", [])

    pollutants_str = ("Material Particulado PM<sub>10</sub> & PM<sub>2,5</sub>, "
                      "Dióxido de Azufre SO<sub>2</sub>, Dióxido de Nitrógeno NO<sub>2</sub>, "
                      "Monóxido de Carbono CO y Ozono O<sub>3</sub>")

    # §4.1 Planeación
    sec41 = f"""
<p>En este capítulo se describen los conocimientos sobre los contaminantes a medir, así mismo, como su
tipo de medición para la ejecución de la campaña de monitoreo y finalmente las descripciones de las
estaciones instaladas.</p>
<h2>4.1 &nbsp; PLANEACIÓN DEL MONITOREO</h2>
<p>De acuerdo con la solicitud realizada por {cfg.get('client',{}).get('name','')}, se generó el plan
de monitoreo {cfg.get('monitoring_plan_code','')}, en el cual se contempla la medición los contaminantes
{pollutants_str}, en el área de influencia de {fc.get('station_name','la estación')}, ubicada en el
municipio de {loc.get('municipality','')}, departamento de {loc.get('department','')}. La campaña de
monitoreo de calidad del aire se realizó, {_period_text(p)}, con mediciones diarias. Con registros
horarios y diarios.</p>
<p>Para la realización de la campaña de monitoreo de calidad del aire se contó con información de
mediciones previas realizadas en el campo objeto del muestreo. Se realizó la calibración y verificación
del analizador, las cuales se presentan en el <strong>Anexo 3</strong>, con el fin de garantizar las
condiciones del equipo en uso. Durante el monitoreo se llevó registro de operación del analizador, bajo
las directrices establecidas por el procedimiento de monitoreo en calidad del aire PTCA.5.4., y los
instructivos I3PTCA-5.4 Determinación de Monóxido de Carbono, I4PTCA-5.4 Determinación de Dióxido de
Azufre, I8PTCA-5.4 Determinación de Dióxido de Nitrógeno y finalmente el I9PTCA-5.4 Determinación de
Material Particulado.</p>"""

    # §4.2 Tiempo de toma
    sec42 = f"""
<h2>4.2 &nbsp; TIEMPO DE TOMA DE MUESTRA Y DURACIÓN DEL MUESTREO</h2>
<p>{TEXT_4_2}</p>"""

    # §4.3 Contaminantes
    paras_intro = "".join(f"<p>{t}</p>" for t in TEXT_4_3_INTRO)
    pollutant_sections = "".join(
        _build_pollutant_section(key, cfg, fig_paths)
        for key in ["PM", "SO2", "NO2", "CO", "O3"]
    )
    sec43 = f"""
<h2>4.3 &nbsp; CONTAMINANTES POR MEDIR, LÍMITE NORMATIVO Y MÉTODO REFERENCIA</h2>
{paras_intro}
{_build_tabla5()}
<p style="text-align:right;font-size:9pt;"><strong>Fuente:</strong> Corola Ambiental S.A.S – {year}.</p>
{pollutant_sections}"""

    # §4.4 Adiciones
    sec44 = f"""
<h2>4.4 &nbsp; ADICIONES – DESVIACIONES y/o EXCLUSIONES DEL METODO DE ENSAYO</h2>
<p>{TEXT_4_4}</p>"""

    # §4.5 Condiciones
    paras_cond = "".join(f"<p>{t}</p>" for t in TEXT_4_5)
    sec45 = f"<h2>4.5 &nbsp; CONDICIONES DE MONITOREO</h2>{paras_cond}"

    # §4.6 Fuentes de Emisión
    source_table_rows = "".join(
        f"<tr><td style='text-align:center'>{s.get('id','')}</td>"
        f"<td>{s.get('name','')}</td><td>{s.get('description','')}</td></tr>"
        for s in sources
    )
    source_table = f"""
<table class="data-table">
  <caption>Tabla 6. Inventario de Fuentes – {fc.get('name','')} {fc.get('station_name','')}.</caption>
  <thead><tr><th>ID</th><th>Nombre Fuente</th><th>Descripción</th></tr></thead>
  <tbody>{source_table_rows}</tbody>
</table>
<p style="text-align:right;font-size:9pt;"><strong>Fuente:</strong> Corola Ambiental S.A.S – {year}.</p>"""

    # Fotos de fuentes (grid 2 columnas)
    photo_pairs = ""
    for i in range(0, len(sources), 2):
        left = sources[i]
        right = sources[i+1] if i+1 < len(sources) else None
        l_img = _img(left.get("photo_path",""), "width:100%;max-height:250px;object-fit:cover;", left.get("name",""))
        r_img = _img(right.get("photo_path",""), "width:100%;max-height:250px;object-fit:cover;", right.get("name","")) if right else ""
        l_cap = left.get("name", "")
        r_cap = right.get("name", "") if right else ""
        photo_pairs += f"""
<tr>
  <td style="width:30px;text-align:center;font-weight:bold;">{left.get('id','')}</td>
  <td style="text-align:center;">{l_img}<br><strong>{l_cap}</strong></td>
  <td style="width:30px;text-align:center;font-weight:bold;">{right.get('id','') if right else ''}</td>
  <td style="text-align:center;">{r_img}<br><strong>{r_cap}</strong></td>
</tr>"""

    source_photos = f"""
<table style="width:100%;border-collapse:collapse;margin:14px 0;">
  <thead>
    <tr>
      <th colspan="2" style="background:#145a32;color:#fff;padding:6px;">ID</th>
      <th colspan="2" style="background:#145a32;color:#fff;padding:6px;">Registro Fotográfico</th>
    </tr>
  </thead>
  <tbody>{photo_pairs}</tbody>
</table>
<p style="text-align:right;font-size:9pt;"><strong>Fuente:</strong> Corola Ambiental S.A.S – {year}.</p>"""

    # Figura 4 – mapa fuentes
    fig4_path = fig_paths.get("fig4_fuentes", cfg.get("geo_map_fuentes_path", ""))
    fig4 = (f'<p class="fig-caption">Figura 4 Ubicación Geográfica inventario de fuentes – '
            f'{fc.get("name","")} {fc.get("station_name","")}.</p>'
            f'{_img(fig4_path, "width:100%;max-width:750px;display:block;margin:auto;", "Mapa fuentes")}'
            f'<p class="fig-source"><strong>Fuente:</strong> Corola Ambiental S.A.S – {year}.</p>')

    sec46 = f"""
<h2>4.6 &nbsp; DESCRIPCIÓN DE LAS PRINCIPALES FUENTES DE EMISIÓN Y RECEPTORES POTENCIALES</h2>
{source_table}
{source_photos}
<p>En la <strong>Figura 4</strong>, se presentan la ubicación geográfica de las fuentes previamente descritas.</p>
{fig4}"""

    # §4.7 Descripción puntos
    fig5_path = fig_paths.get("fig5_estaciones", cfg.get("geo_map_stations_path", ""))
    fig5 = (f'<p class="fig-caption">Figura 5 Ubicación Geográfica de la estación de calidad del aire.</p>'
            f'{_img(fig5_path, "width:100%;max-width:750px;display:block;margin:auto;", "Mapa estaciones")}'
            f'<p class="fig-source"><strong>Fuente:</strong> Corola Ambiental S.A.S – {year}.</p>')

    sec47 = f"""
<h2>4.7 &nbsp; DESCRIPCIÓN PUNTOS DE MONITOREO</h2>
<p>Según la zona de estudio, la clasificación de la campaña de monitoreo corresponde a una escala micro,
que se define generalmente en áreas como cañones urbanos y corredores de tráfico donde el público puede
estar expuesto a altas concentraciones de contaminantes provenientes de las emisiones de fuentes móviles
o fuentes puntuales. Responde a estudios puntuales de un grupo de fuentes y receptores específicos y/o
estudios epidemiológicos. Las mediciones tomadas a esta escala no deben tomarse como representativas de
un área mayor. El monitoreo se realizó durante {p["duration_days"]} días, con mediciones diarias, en las
estaciones dispuestas en el área de influencia de {fc.get('station_name','la estación')}, ubicada en el
municipio de {loc.get('municipality','')}, departamento de {loc.get('department','')}, como se presenta
en la <strong>Figura 5</strong>.</p>
{fig5}"""

    # §4.8 Fichas técnicas
    sec48_header = "<h2>4.8 &nbsp; FICHAS TÉCNICAS DE ESTACIONES DE MONITOREO</h2>"
    fichas = "".join(
        _build_ficha_tecnica(st, i+1, year)
        for i, st in enumerate(stations)
    )

    # §4.9 Cronograma
    cron_rows = "".join(
        f"<tr><td style='text-align:center;font-weight:bold'>{c.get('fecha','')}</td>"
        f"<td style='text-align:center'>{c.get('actividad','')}</td></tr>"
        for c in cronograma
    )
    sec49 = f"""
<h2>4.9 &nbsp; CRONOLOGÍA DEL MONITOREO</h2>
<p>A continuación, se presenta el cronograma con las principales actividades realizadas en el desarrollo
de la campaña de monitoreo de calidad del aire.</p>
<table class="data-table">
  <caption>Tabla 10. Cronograma de actividades.</caption>
  <thead><tr>
    <th style="background:#145a32;color:#fff">Fecha</th>
    <th style="background:#145a32;color:#fff">Actividad</th>
  </tr></thead>
  <tbody>{cron_rows}</tbody>
</table>
<p style="text-align:right;font-size:9pt;"><strong>Fuente:</strong> Corola Ambiental S.A.S – {year}.</p>"""

    # §4.10 Validación
    valid_rows = "".join(
        f"<tr><td style='text-align:center'>{f}</td><td style='text-align:center'>{v}</td><td>{d}</td></tr>"
        for f, v, d in VALID_FLAGS
    )
    invalid_rows = "".join(
        f"<tr><td style='text-align:center'>{f}</td><td style='text-align:center'>{v}</td><td>{d}</td></tr>"
        for f, v, d in INVALID_FLAGS
    )
    sec410 = f"""
<h2>4.10 &nbsp; VALIDACIÓN DE DATOS</h2>
<p>{TEXT_4_10}</p>
<table class="data-table">
  <caption>Tabla 11. Banderas que indican validez del dato.</caption>
  <thead><tr><th>Bandera</th><th>Validez</th><th>Descripción</th></tr></thead>
  <tbody>{valid_rows}</tbody>
</table>
<p style="text-align:right;font-size:9pt;"><strong>Fuente:</strong> Corola Ambiental S.A.S – {year}.</p>
<table class="data-table">
  <caption>Tabla 12. Banderas que indican invalidez del dato.</caption>
  <thead><tr><th>Bandera</th><th>Validez</th><th>Descripción</th></tr></thead>
  <tbody>{invalid_rows}</tbody>
</table>
<p style="text-align:right;font-size:9pt;"><strong>Fuente:</strong> Corola Ambiental S.A.S – {year}.</p>"""

    # §4.11 Condiciones ambientales
    cond_rows = "".join(
        f"<tr><td style='text-align:center'>{c.get('id','')}</td>"
        f"<td style='text-align:center'>{c.get('code','')}</td>"
        f"<td style='text-align:center'>{c.get('temp_min','')}</td>"
        f"<td style='text-align:center'>{c.get('temp_max','')}</td></tr>"
        for c in cond_amb
    )
    sec411 = f"""
<h2>4.11 &nbsp; CONDICIONES AMBIENTALES</h2>
<p>{TEXT_4_11}</p>
<table class="data-table">
  <caption>Tabla 13. Condiciones ambientales monitoreo.</caption>
  <thead>
    <tr><th rowspan="2">ID</th><th rowspan="2">Estación de monitoreo</th><th colspan="2">Temperatura Ambiente</th></tr>
    <tr><th>Mínima</th><th>Máxima</th></tr>
  </thead>
  <tbody>{cond_rows}</tbody>
</table>
<p style="text-align:right;font-size:9pt;"><strong>Fuente:</strong> Corola Ambiental S.A.S – {year}.</p>"""

    # §4.12 Incertidumbre
    incert_rows = "".join(
        f"<tr><td style='text-align:center'>{r.get('id','')}</td>"
        f"<td style='text-align:center'>{r.get('code','')}</td>"
        f"<td style='text-align:center'>{r.get('PM10','')}</td>"
        f"<td style='text-align:center'>{r.get('PM25','')}</td>"
        f"<td style='text-align:center'>{r.get('SO2','')}</td>"
        f"<td style='text-align:center'>{r.get('NO2','')}</td>"
        f"<td style='text-align:center'>{r.get('CO','')}</td>"
        f"<td style='text-align:center'>{r.get('O3','')}</td></tr>"
        for r in incert
    )
    sec412 = f"""
<h2>4.12 &nbsp; INCERTIDUMBRE DE DATOS</h2>
<p>{TEXT_4_12}</p>
<table class="data-table">
  <caption>Tabla 14. Incertidumbre parámetros.</caption>
  <thead>
    <tr><th rowspan="2">ID</th><th rowspan="2">Estación</th><th colspan="6">Incertidumbre K²</th></tr>
    <tr><th>PM<sub>10</sub></th><th>PM<sub>2,5</sub></th><th>SO<sub>2</sub></th>
        <th>NO<sub>2</sub></th><th>CO</th><th>O<sub>3</sub></th></tr>
  </thead>
  <tbody>{incert_rows}</tbody>
</table>
<p style="text-align:right;font-size:9pt;"><strong>Fuente:</strong> Corola Ambiental S.A.S – {year}.</p>"""

    # §4.13 Micro localización
    met_photo = _img(cfg.get("met_station_photo_path", ""),
                     "width:100%;max-width:500px;display:block;margin:auto;", "Estación meteorológica")

    checklist_rows = ""
    for sensor, items in MET_CHECKLIST.items():
        checklist_rows += f'<tr><td colspan="2" style="background:#d5f5e3;font-weight:bold;text-align:center">{sensor}</td></tr>'
        for item, cumple, obs in items:
            checklist_rows += (
                f"<tr><td>{item}</td><td>{cumple}</td></tr>"
                f"<tr><td colspan='2' style='font-size:9pt;color:#555;padding-left:12px'>{obs}</td></tr>"
            )

    sec413 = f"""
<h2>4.13 &nbsp; MICRO LOCALIZACIÓN DE ESTACIÓN METEOROLÓGICA</h2>
<p>{TEXT_4_13}</p>
<table class="data-table">
  <caption>Tabla 15. Check List. Micro localización de estación meteorológica</caption>
  <thead>
    <tr><th>ÍTEM EVALUADO</th><th>Cumple Si / No</th></tr>
  </thead>
  <tbody>{checklist_rows}</tbody>
</table>
<p style="text-align:center;margin:14px 0;font-weight:bold;">Registro Fotográfico</p>
{met_photo}
<p class="fig-source"><strong>Fuente:</strong> Corola Ambiental S.A.S – {year}.</p>"""

    return f"""
<div class="page-break">
{_page_header(cfg)}
<h1>4. &nbsp; GENERALIDADES</h1>
{sec41}{sec42}
{_page_footer()}
</div>
<div class="page-break">
{_page_header(cfg)}
{sec43}
{_page_footer()}
</div>
<div class="page-break">
{_page_header(cfg)}
{sec44}{sec45}
{_page_footer()}
</div>
<div class="page-break">
{_page_header(cfg)}
{sec46}
{_page_footer()}
</div>
<div class="page-break">
{_page_header(cfg)}
{sec47}
{sec48_header}
{_page_footer()}
</div>
{fichas}
<div class="page-break">
{_page_header(cfg)}
{sec49}{sec410}
{_page_footer()}
</div>
<div class="page-break">
{_page_header(cfg)}
{sec411}{sec412}{sec413}
{_page_footer()}
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def generate_report(config: dict, output_dir: str) -> dict:
    """
    Genera el HTML autocontenido con Portada + Preliminares + Secciones 1–4.

    Args:
        config:     Diccionario con todos los parámetros del proyecto.
                    Ver data/sample_portada_config.json para la estructura completa.
        output_dir: Carpeta de salida donde se guardará el HTML.

    Returns:
        {"report_path": str}
    """
    os.makedirs(output_dir, exist_ok=True)

    body = "\n".join([
        _build_cover(config),
        _build_control_page(config),
        _build_toc(config),
        _build_lists(config),
        _build_glossary(config),
        _build_section1(config),
        _build_section2(config),
        _build_section3(config),
        _build_section4(config),
    ])

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Informe {config.get('report_code', '')} – Secciones 1–4</title>
  <style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>"""

    out_path = os.path.join(output_dir, "seccion1_4_portada_generalidades.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    return {"report_path": out_path}


# ─────────────────────────────────────────────────────────────────────────────
# CLI rápido para pruebas
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    config_path = sys.argv[1] if len(sys.argv) > 1 else "data/sample_portada_config.json"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "output"
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)
    result = generate_report(cfg, out_dir)
    print(f"Generado: {result['report_path']}")
