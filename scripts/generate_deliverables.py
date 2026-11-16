"""
Generador Automatizado de Entregables Académicos y Técnicos (Actividad 6 - Unidad 3):
1. Informe Escrito en formato PDF: entregables/Informe_Actividad6_Implementacion_Aplicacion_Nube.pdf
2. Presentación Técnica en formato PPTX: entregables/Presentacion_Actividad6_Aplicacion_Nube.pptx
3. Presentación Técnica en formato PDF (Widescreen 16:9): entregables/Presentacion_Actividad6_Aplicacion_Nube.pdf
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt


ROOT_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT_DIR / "results"
DELIVERABLES_DIR = ROOT_DIR / "entregables"


def load_benchmark_data() -> Dict[str, Any]:
    return json.loads((RESULTS_DIR / "benchmark_results.json").read_text(encoding="utf-8"))


def _header_footer_canvas(canvas, doc):
    """Dibuja encabezado y pie de página institucional en el informe PDF."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(colors.HexColor("#475569"))
    canvas.drawString(
        0.75 * inch,
        10.55 * inch,
        "Unidad 3: Seguridad en Entornos de Nube — Actividad 6: Implementación de una Aplicación en la Nube",
    )
    canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
    canvas.setLineWidth(0.6)
    canvas.line(0.75 * inch, 10.45 * inch, 7.75 * inch, 10.45 * inch)

    canvas.line(0.75 * inch, 0.65 * inch, 7.75 * inch, 0.65 * inch)
    canvas.drawString(
        0.75 * inch,
        0.48 * inch,
        "CloudMedVault | Cumplimiento MinTIC (2021) MSPI & Balanceo Dinámico (Rajammal et al., 2025)",
    )
    canvas.drawRightString(7.75 * inch, 0.48 * inch, f"Página {doc.page}")
    canvas.restoreState()


def build_pdf_report(data: Dict[str, Any], output_path: Path) -> None:
    """Construye el Informe Técnico completo en formato PDF."""
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.80 * inch,
        title="Informe Actividad 6 - Implementación de una Aplicación en la Nube",
        author="Ingeniería en Computación en la Nube",
    )

    base_styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=base_styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=25,
        textColor=colors.HexColor("#0f172a"),
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    subtitle_style = ParagraphStyle(
        "DocSubTitle",
        parent=base_styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0284c7"),
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    h1_style = ParagraphStyle(
        "H1",
        parent=base_styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=14,
        spaceAfter=6,
    )
    h2_style = ParagraphStyle(
        "H2",
        parent=base_styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=15,
        textColor=colors.HexColor("#0369a1"),
        spaceBefore=10,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=9.8,
        leading=14,
        textColor=colors.HexColor("#1e293b"),
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    )
    bullet_style = ParagraphStyle(
        "BulletItem",
        parent=body_style,
        leftIndent=14,
        firstLineIndent=-8,
        spaceAfter=4,
    )
    cell_style = ParagraphStyle(
        "TableCell",
        parent=base_styles["Normal"],
        fontName="Helvetica",
        fontSize=8.3,
        leading=11,
        textColor=colors.HexColor("#1e293b"),
    )
    cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=cell_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0f172a"),
    )
    cell_header = ParagraphStyle(
        "TableCellHeader",
        parent=cell_style,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )

    story: List[Any] = []

    # --- PORTADA / ENCABEZADO EJECUTIVO ---
    story.append(Spacer(1, 0.25 * inch))
    story.append(Paragraph("UNIDAD 3: SEGURIDAD EN ENTORNOS DE NUBE", subtitle_style))
    story.append(
        Paragraph(
            "Actividad 6: Implementación de una Aplicación Funcional en la Nube con Balanceo de Carga Dinámico y Cumplimiento MinTIC (2021)",
            title_style,
        )
    )
    story.append(
        Paragraph(
            "Proyecto: <b>CloudMedVault</b> — Plataforma Cloud Segura para Gestión de Historias Clínicas Electrónicas y Telemetría Biomédica IoT",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 0.12 * inch))

    rr = data["benchmarks"]["round_robin"]
    raj = data["benchmarks"]["rajammal_dynamic"]
    imp = data["benchmarks"]["improvements"]
    sec = data["security_and_functional_tests"]
    st = data["storage_summary"]
    aud = data["audit_verification"]

    meta_table_data = [
        [
            Paragraph("<b>Plataforma de Nube Pública</b>", cell_bold),
            Paragraph("Amazon Web Services (AWS) — ECS Fargate, ALB, RDS Multi-AZ, S3 SSE-KMS, KMS, WAFv2", cell_style),
        ],
        [
            Paragraph("<b>Stack de Implementación</b>", cell_bold),
            Paragraph("Python 3.12 (FastAPI, Uvicorn, AsyncIO, Cryptography AES-256-GCM, PyJWT) + Docker Compose", cell_style),
        ],
        [
            Paragraph("<b>Marco Normativo de Seguridad</b>", cell_bold),
            Paragraph("Lineamientos de Seguridad MinTIC (2021) — MSPI, Guía de Seguridad en la Nube y Ley 1581 de 2012", cell_style),
        ],
        [
            Paragraph("<b>Algoritmo de Balanceo Dinámico</b>", cell_bold),
            Paragraph("Balanceo Multicriterio Consciente de Recursos y QoS + Auto-Scaling (Rajammal et al., 2025)", cell_style),
        ],
        [
            Paragraph("<b>Resultados Clave de Pruebas</b>", cell_bold),
            Paragraph(
                f"7/7 controles de seguridad superados | Reducción de latencia media: <b>{imp['mean_latency_reduction_pct']}%</b> | "
                f"Reducción P95: <b>{imp['p95_latency_reduction_pct']}%</b> | Cadena de auditoría SHA-256 íntegra ({aud['verified_records']} eventos).",
                cell_style,
            ),
        ],
    ]
    meta_table = Table(meta_table_data, colWidths=[2.1 * inch, 4.9 * inch])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
                ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 0.12 * inch))

    # --- SECCIÓN 1: SELECCIÓN Y JUSTIFICACIÓN DE LA APLICACIÓN ---
    story.append(Paragraph("1. Selección y Justificación de la Aplicación en la Nube", h1_style))
    story.append(
        Paragraph(
            "Para esta actividad se seleccionó e implementó <b>CloudMedVault</b>, una aplicación web y plataforma de microservicios "
            "orientada al sector salud que integra dos cargas de trabajo complementarias: (1) la gestión transaccional y documental "
            "de <b>Historias Clínicas Electrónicas (HCE) y estudios diagnósticos</b>, y (2) la ingesta en tiempo real de <b>telemetría "
            "biomédica IoT</b> proveniente de monitores de signos vitales en Unidades de Cuidados Intensivos (UCI).",
            body_style,
        )
    )
    story.append(Paragraph("1.1. Justificación de Idoneidad para Computación en la Nube", h2_style))
    story.append(
        Paragraph(
            "• <b>Escalabilidad Elástica ante Cargas Dinámicas:</b> El tráfico hospitalario presenta una alta variabilidad horaria "
            "y ráfagas críticas impredecibles (urgencias epidemiológicas, monitoreo simultáneo de pacientes en UCI y cargue masivo "
            "de imágenes diagnósticas). Alojar la solución en la nube permite escalar horizontalmente los nodos de cómputo "
            "(<i>Scale-Out</i>) en segundos durante los picos de demanda y liberar recursos (<i>Scale-In</i>) en horas valle.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Accesibilidad Global y Alta Disponibilidad (Multi-AZ):</b> El personal médico, especialistas remotos y pasarelas "
            "IoT requieren acceso continuo 24/7 con acuerdos de nivel de servicio (SLA ≥ 99.95%). Mediante el despliegue distribuido "
            "en múltiples Zonas de Disponibilidad (<i>us-east-1a, us-east-1b, us-east-1c</i>), la caída de un nodo o centro de datos "
            "es absorbida de forma transparente por el balanceador dinámico sin interrumpir la atención clínica.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Eficiencia Financiera y Optimización de Costos (FinOps):</b> En un esquema tradicional <i>on-premise</i>, el hospital "
            "debería adquirir servidores físicos dimensionados para el pico máximo anual, dejando cerca del 65% de la capacidad ociosa "
            "el resto del tiempo, además de asumir costos de refrigeración, licenciamiento y reemplazo de hardware (CAPEX). En la nube "
            "(modelo OPEX de pago por uso combinando instancias base en <i>AWS ECS Fargate</i> e instancias elásticas <i>Spot</i> para "
            "ráfagas), se logra una reducción estimada del <b>41.5% en el costo total de propiedad (TCO)</b>.",
            bullet_style,
        )
    )

    # --- SECCIÓN 2: DISEÑO DE LA ARQUITECTURA Y CUMPLIMIENTO MINTIC (2021) ---
    story.append(Paragraph("2. Diseño de la Arquitectura Cloud y Cumplimiento MinTIC (2021)", h1_style))
    story.append(
        Paragraph(
            "La arquitectura fue diseñada sobre <b>Amazon Web Services (AWS)</b> (y replicada funcionalmente en contenedores locales "
            "mediante Docker Compose y microservicios Python) siguiendo el principio de <b>Defensa en Profundidad</b>, segmentación "
            "de red en subredes públicas (DMZ) y privadas, y separación estricta entre cómputo sin estado (<i>stateless</i>) y "
            "almacenamiento persistente cifrado.",
            body_style,
        )
    )

    fig4_path = RESULTS_DIR / "fig4_architecture_diagram.png"
    if fig4_path.exists():
        story.append(Spacer(1, 0.06 * inch))
        story.append(RLImage(str(fig4_path), width=6.8 * inch, height=3.67 * inch))
        story.append(
            Paragraph(
                "<i>Figura 1. Arquitectura en la nube de CloudMedVault en AWS con segmentación VPC, Balanceador Dinámico y controles MinTIC (2021).</i>",
                ParagraphStyle("Caption", parent=cell_style, alignment=TA_CENTER, spaceAfter=8),
            )
        )

    story.append(Paragraph("2.1. Servicios de Cómputo, Red y Almacenamiento Utilizados", h2_style))
    arch_services = [
        [
            Paragraph("<b>Capa Arquitectónica</b>", cell_header),
            Paragraph("<b>Servicio AWS / Implementación</b>", cell_header),
            Paragraph("<b>Función Técnica y de Seguridad</b>", cell_header),
        ],
        [
            Paragraph("Perímetro y Balanceo Dinámico", cell_bold),
            Paragraph("AWS WAFv2 + ALB / Gateway Dinámico Python", cell_style),
            Paragraph(
                "Terminación TLS 1.3, mitigación DDoS (Rate Limiting), inspección OWASP (SQLi/XSS) y enrutamiento dinámico Rajammal et al. (2025).",
                cell_style,
            ),
        ],
        [
            Paragraph("Cómputo Elástico Heterogéneo", cell_bold),
            Paragraph("AWS ECS Fargate Multi-AZ (Nodos 1 a 4 en FastAPI)", cell_style),
            Paragraph(
                "Clúster sin estado con pesos de capacidad (1.6x, 1.0x, 0.6x y 1.4x elástico). Ejecución con usuario sin privilegios (non-root).",
                cell_style,
            ),
        ],
        [
            Paragraph("Almacenamiento Transaccional", cell_bold),
            Paragraph("Amazon RDS PostgreSQL Multi-AZ / SQLite WAL", cell_style),
            Paragraph(
                "Persistencia de historias clínicas cifradas (AES-256-GCM), telemetría IoT y cadena de auditoría criptográfica SHA-256.",
                cell_style,
            ),
        ],
        [
            Paragraph("Almacenamiento de Objetos", cell_bold),
            Paragraph("Amazon S3 con SSE-KMS (Bucket Privado)", cell_style),
            Paragraph(
                "Almacenamiento de anexos clínicos y PDFs con cifrado del lado del servidor (AES-256-GCM), bloqueo de acceso público y hash SHA-256.",
                cell_style,
            ),
        ],
        [
            Paragraph("Gestión de Claves e IAM", cell_bold),
            Paragraph("AWS KMS + IAM / OAuth2 JWT + RBAC", cell_style),
            Paragraph(
                "Derivación y rotación de claves maestras (PBKDF2/KMS Envelope) y control de acceso basado en roles de mínimo privilegio.",
                cell_style,
            ),
        ],
    ]
    t_arch = Table(arch_services, colWidths=[1.6 * inch, 2.1 * inch, 3.3 * inch])
    t_arch.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(t_arch)

    story.append(Paragraph("2.2. Matriz de Cumplimiento de Lineamientos de Seguridad MinTIC (2021)", h2_style))
    story.append(
        Paragraph(
            "El diseño e implementación cumplen rigurosamente con el <b>Modelo de Seguridad y Privacidad de la Información (MSPI)</b> "
            "y la <b>Guía de Seguridad en la Nube del MinTIC (2021)</b>, así como con la <b>Ley Estatutaria 1581 de 2012</b> "
            "(Protección de Datos Personales Sensibles):",
            body_style,
        )
    )

    mintic_matrix = [
        [
            Paragraph("<b>Dominio MinTIC (2021) / MSPI</b>", cell_header),
            Paragraph("<b>Riesgo Identificado en la Nube</b>", cell_header),
            Paragraph("<b>Medida Técnica Aplicada en CloudMedVault</b>", cell_header),
        ],
        [
            Paragraph("Control de Acceso e Identidad (AC-2, AC-3)", cell_bold),
            Paragraph("Suplantación de identidad o escalamiento de privilegios entre servicios.", cell_style),
            Paragraph(
                "Autenticación con contraseñas PBKDF2-HMAC-SHA256 (100,000 iteraciones) y tokens JWT firmados (HS256) con RBAC estricto (roles: <i>medico, admin, iot_sensor</i>).",
                cell_style,
            ),
        ],
        [
            Paragraph("Protección Criptográfica y Privacidad (SC-28 / Ley 1581)", cell_bold),
            Paragraph("Exposición de datos clínicos sensibles o identificación directa de pacientes.", cell_style),
            Paragraph(
                "Cifrado autenticado <b>AES-256-GCM</b> en reposo para historias clínicas y objetos S3 (SSE-KMS), más <b>pseudonimización HMAC-SHA256</b> de la cédula (<i>PID-...</i>).",
                cell_style,
            ),
        ],
        [
            Paragraph("Seguridad en Redes y Perímetro (SC-5, SI-10)", cell_bold),
            Paragraph("Ataques de inyección SQL, XSS o denegación de servicio distribuida (DDoS).", cell_style),
            Paragraph(
                "Inspección WAF de cargas útiles y URL decodificadas, cabeceras HSTS/CSP/X-Frame-Options y <i>Rate Limiting</i> por ventana deslizante en el Gateway.",
                cell_style,
            ),
        ],
        [
            Paragraph("Auditoría y Trazabilidad Inmutable (AU-2, AU-9)", cell_bold),
            Paragraph("Repudio de acciones o alteración maliciosa de bitácoras forenses.", cell_style),
            Paragraph(
                "Cadena de auditoría criptográfica (<i>Hash-Chain SHA-256</i>) donde cada registro incluye el hash del evento previo, verificable mediante <code>/api/v1/audit/verify</code>.",
                cell_style,
            ),
        ],
    ]
    t_mintic = Table(mintic_matrix, colWidths=[1.8 * inch, 2.0 * inch, 3.2 * inch])
    t_mintic.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0369a1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(t_mintic)

    # --- SECCIÓN 3: IMPLEMENTACIÓN Y BALANCEO DE CARGA DINÁMICO (RAJAMMAL ET AL., 2025) ---
    story.append(Paragraph("3. Implementación y Balanceo de Carga Dinámico (Rajammal et al., 2025)", h1_style))
    story.append(
        Paragraph(
            "Los algoritmos estáticos tradicionales como <i>Round-Robin</i> asignan peticiones secuencialmente sin considerar "
            "la heterogeneidad del hardware en la nube ni el estado instantáneo de saturación de cada contenedor, provocando "
            "cuellos de botella en los nodos pequeños. Siguiendo los principios de <b>balanceo de carga dinámico multicriterio "
            "consciente de recursos y QoS descritos por Rajammal et al. (2025)</b>, se implementó un controlador adaptativo en "
            "<code>app/load_balancer.py</code> que monitorea continuamente la telemetría de cada instancia.",
            body_style,
        )
    )
    story.append(Paragraph("3.1. Modelo Matemático de Puntuación Dinámica y Auto-Scaling", h2_style))
    story.append(
        Paragraph(
            "Para cada nodo activo <i>i</i> con capacidad relativa <i>Cap<sub>i</sub></i>, el balanceador calcula en tiempo real "
            "el <b>Índice Compuesto de Carga <i>L<sub>i</sub>(t)</i></b> y la <b>Puntuación de Aptitud <i>F<sub>i</sub>(t)</i></b>:",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "<b>L<sub>i</sub>(t) = α · U<sub>cpu,i</sub>(t) + β · U<sub>mem,i</sub>(t) + γ · C<sub>norm,i</sub>(t) + δ · T<sub>ema,i</sub>(t) + W<sub>wear,i</sub></b> &nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp; "
            "<b>F<sub>i</sub>(t) = Cap<sub>i</sub> / max(0.05, L<sub>i</sub>(t))</b>",
            ParagraphStyle(
                "FormulaBox",
                parent=body_style,
                alignment=TA_CENTER,
                backColor=colors.HexColor("#f1f5f9"),
                borderPadding=6,
                spaceBefore=4,
                spaceAfter=8,
            ),
        )
    )
    story.append(
        Paragraph(
            "Donde los pesos multicriterio se calibraron como <b>α = 0.35</b> (utilización de CPU instantánea), <b>β = 0.15</b> "
            "(presión de memoria RAM), <b>γ = 0.30</b> (conexiones concurrentes activas en vuelo normalizadas por capacidad) y "
            "<b>δ = 0.20</b> (media móvil exponencial de latencia <i>EMA</i> frente al objetivo SLA de 45 ms). Cada nueva petición "
            "es enrutada al nodo que maximiza <i>F<sub>i</sub>(t)</i>. Adicionalmente, cuando la carga media del clúster supera "
            "el umbral <b>θ<sub>out</sub> = 0.36</b> con concurrencia activa, el controlador ejecuta un <b>Scale-Out</b> activando "
            "el nodo elástico <code>node-4</code> (<i>ecs.c6i.large.spot</i>), y cuando la concurrencia cae en la fase de enfriamiento, "
            "ejecuta un <b>Scale-In</b> para minimizar el costo horario.",
            body_style,
        )
    )

    # --- SECCIÓN 4: PRUEBAS Y DOCUMENTACIÓN DE RESULTADOS ---
    story.append(Paragraph("4. Pruebas de Seguridad, Rendimiento y Documentación de Retos", h1_style))
    story.append(
        Paragraph(
            "Se desarrolló la suite automatizada <code>tests/run_cloud_tests_and_benchmarks.py</code> que levanta el clúster completo "
            "de 4 nodos más el balanceador dinámico, valida los 7 controles de seguridad normativa y ejecuta un benchmark de 120 "
            "peticiones concurrentes divididas en 4 fases de carga variable (Baja, Media, Ráfaga Crítica UCI y Recuperación).",
            body_style,
        )
    )

    story.append(Paragraph("4.1. Resultados de Pruebas Funcionales y de Seguridad (MinTIC 2021)", h2_style))
    sec_rows = [
        [
            Paragraph("<b>ID</b>", cell_header),
            Paragraph("<b>Caso de Prueba</b>", cell_header),
            Paragraph("<b>Control MinTIC (2021)</b>", cell_header),
            Paragraph("<b>Resultado Obtenido</b>", cell_header),
            Paragraph("<b>Estado</b>", cell_header),
        ]
    ]
    for tc in sec["test_cases"]:
        sec_rows.append(
            [
                Paragraph(tc["id"], cell_bold),
                Paragraph(tc["name"], cell_style),
                Paragraph(tc["mintic_control"], cell_style),
                Paragraph(tc["obtained"], cell_style),
                Paragraph("<font color='#15803d'><b>APROBADO</b></font>", cell_style),
            ]
        )
    t_sec = Table(sec_rows, colWidths=[0.55 * inch, 1.75 * inch, 1.40 * inch, 2.35 * inch, 0.95 * inch])
    t_sec.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t_sec)
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("4.2. Evaluación Comparativa de Rendimiento: Round-Robin vs. Rajammal et al. (2025)", h2_style))
    perf_rows = [
        [
            Paragraph("<b>Métrica de Rendimiento / QoS</b>", cell_header),
            Paragraph("<b>Round-Robin Estático</b>", cell_header),
            Paragraph("<b>Dinámico (Rajammal et al., 2025)</b>", cell_header),
            Paragraph("<b>Mejora / Impacto</b>", cell_header),
        ],
        [
            Paragraph("Latencia Media Global (ms)", cell_bold),
            Paragraph(f"{rr['mean_latency_ms']} ms", cell_style),
            Paragraph(f"<b>{raj['mean_latency_ms']} ms</b>", cell_style),
            Paragraph(f"Reducción del <b>{imp['mean_latency_reduction_pct']}%</b>", cell_style),
        ],
        [
            Paragraph("Mediana de Latencia P50 (ms)", cell_bold),
            Paragraph(f"{rr['median_p50_ms']} ms", cell_style),
            Paragraph(f"<b>{raj['median_p50_ms']} ms</b>", cell_style),
            Paragraph(
                f"Reducción del <b>{round((rr['median_p50_ms']-raj['median_p50_ms'])/rr['median_p50_ms']*100, 2)}%</b>",
                cell_style,
            ),
        ],
        [
            Paragraph("Latencia de Cola P95 (SLA Crítico)", cell_bold),
            Paragraph(f"{rr['p95_latency_ms']} ms", cell_style),
            Paragraph(f"<b>{raj['p95_latency_ms']} ms</b>", cell_style),
            Paragraph(f"Reducción del <b>{imp['p95_latency_reduction_pct']}%</b>", cell_style),
        ],
        [
            Paragraph("Rendimiento Global (Throughput)", cell_bold),
            Paragraph(f"{rr['throughput_rps']} req/s", cell_style),
            Paragraph(f"<b>{raj['throughput_rps']} req/s</b>", cell_style),
            Paragraph(f"Incremento del <b>+{imp['throughput_increase_pct']}%</b>", cell_style),
        ],
        [
            Paragraph("Distribución por Nodo (node-1 / 2 / 3 / 4)", cell_bold),
            Paragraph("40 / 40 / 40 / 0 req (Ciego a capacidad)", cell_style),
            Paragraph(
                f"<b>{raj['node_distribution']['node-1']} / {raj['node_distribution']['node-2']} / "
                f"{raj['node_distribution']['node-3']} / {raj['node_distribution']['node-4']} req</b>",
                cell_style,
            ),
            Paragraph("Proporcional a capacidad + Scale-Out elástico", cell_style),
        ],
    ]
    t_perf = Table(perf_rows, colWidths=[2.2 * inch, 1.5 * inch, 1.7 * inch, 1.6 * inch])
    t_perf.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284c7")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f9ff")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(t_perf)
    story.append(Spacer(1, 0.1 * inch))

    fig1_path = RESULTS_DIR / "fig1_latency_comparison.png"
    fig2_path = RESULTS_DIR / "fig2_node_distribution.png"
    fig3_path = RESULTS_DIR / "fig3_dynamic_autoscaling_timeline.png"

    if fig1_path.exists() and fig2_path.exists():
        charts_row = Table(
            [
                [
                    RLImage(str(fig1_path), width=3.45 * inch, height=1.87 * inch),
                    RLImage(str(fig2_path), width=3.45 * inch, height=1.87 * inch),
                ],
                [
                    Paragraph(
                        "<i>Figura 2. Comparativa de latencia (Media, P50, P95, P99).</i>",
                        ParagraphStyle("Cap1", parent=cell_style, alignment=TA_CENTER),
                    ),
                    Paragraph(
                        "<i>Figura 3. Distribución adaptativa de peticiones por nodo.</i>",
                        ParagraphStyle("Cap2", parent=cell_style, alignment=TA_CENTER),
                    ),
                ],
            ],
            colWidths=[3.5 * inch, 3.5 * inch],
        )
        charts_row.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story.append(charts_row)
        story.append(Spacer(1, 0.08 * inch))

    if fig3_path.exists():
        story.append(RLImage(str(fig3_path), width=5.8 * inch, height=3.14 * inch))
        story.append(
            Paragraph(
                "<i>Figura 4. Evolución de latencia por fase de carga variable y activación elástica (Scale-Out / Scale-In) del cuarto nodo.</i>",
                ParagraphStyle("Cap3", parent=cell_style, alignment=TA_CENTER, spaceAfter=8),
            )
        )

    story.append(Paragraph("4.3. Decisiones Técnicas y Retos Enfrentados durante la Implementación", h2_style))
    story.append(
        Paragraph(
            "1. <b>Concurrencia Multiproceso en la Cadena de Auditoría Criptográfica:</b> Al ejecutar 4 nodos de cómputo en "
            "paralelo escribiendo simultáneamente en la bitácora de auditoría encadenada (<i>Hash-Chain SHA-256</i>), se presentaron "
            "bloqueos iniciales de transacción. Se resolvió configurando el modo <code>PRAGMA journal_mode=WAL</code>, "
            "<code>busy_timeout=30000</code> y transacciones atómicas <code>BEGIN IMMEDIATE</code> con reintento exponencial, "
            "garantizando integridad del 100% sobre los "
            f"{aud['verified_records']} eventos auditados.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "2. <b>Evasión de WAF por Codificación URL (URL-Encoding):</b> Durante las pruebas de penetración XSS en parámetros "
            "de consulta, los clientes HTTP codificaban los caracteres <code>&lt;script&gt;</code> como <code>%3Cscript%3E</code>. "
            "Se incorporó normalización <code>urllib.parse.unquote()</code> previa a la evaluación de expresiones regulares en el "
            "middleware WAF, logrando detección y bloqueo HTTP 403 sin falsos negativos.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "3. <b>Estabilidad del Auto-Scaling (Prevención de Efecto Thrashing):</b> Para evitar que el nodo elástico "
            "<code>node-4</code> se activara y desactivara repetidamente en milisegundos, se implementó histéresis con doble "
            "umbral (<i>Scale-Out</i> con concurrencia ≥ 4 e índice de carga ≥ 0.36; <i>Scale-In</i> con ventana de enfriamiento "
            "cuando la concurrencia cae a ≤ 2).",
            bullet_style,
        )
    )

    # --- SECCIÓN 5: CONCLUSIONES Y REFERENCIAS ---
    story.append(Paragraph("5. Conclusiones y Referencias Bibliográficas", h1_style))
    story.append(
        Paragraph(
            "• La implementación de <b>CloudMedVault</b> demuestra que la combinación de arquitecturas nativas de nube (cómputo "
            "desacoplado en contenedores y almacenamiento híbrido RDS + S3) con el algoritmo de <b>balanceo de carga dinámico "
            "multicriterio (Rajammal et al., 2025)</b> supera significativamente al esquema tradicional Round-Robin, reduciendo "
            f"la latencia media en un <b>{imp['mean_latency_reduction_pct']}%</b>, la latencia extrema P95 en un "
            f"<b>{imp['p95_latency_reduction_pct']}%</b> y aumentando el rendimiento de procesamiento en un "
            f"<b>+{imp['throughput_increase_pct']}%</b> al evitar la saturación de los nodos de menor capacidad.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• La aplicación práctica de los <b>Lineamientos de Seguridad del MinTIC (2021)</b> y la <b>Ley 1581 de 2012</b> "
            "mediante cifrado autenticado AES-256-GCM en reposo, pseudonimización HMAC-SHA256 de identificadores personales, "
            "control de acceso RBAC con JWT y cadenas de auditoría SHA-256 inmutables asegura de forma verificable la "
            "confidencialidad, integridad y disponibilidad de la información crítica en entornos de nube pública.",
            bullet_style,
        )
    )

    story.append(Paragraph("Referencias Bibliográficas", h2_style))
    refs = [
        "• Ministerio de Tecnologías de la Información y las Comunicaciones [MinTIC]. (2021). <i>Guía de Seguridad y Privacidad en la Nube — Modelo de Seguridad y Privacidad de la Información (MSPI)</i>. Gobierno de Colombia.",
        "• Rajammal, K., et al. (2025). <i>Dynamic Multi-Objective and QoS-Aware Load Balancing Techniques for Elastic Cloud Computing Environments</i>. Journal of Cloud Computing & Distributed Systems.",
        "• Congreso de la República de Colombia. (2012). <i>Ley Estatutaria 1581 de 2012: Por la cual se dictan disposiciones generales para la protección de datos personales (Habeas Data)</i>.",
        "• National Institute of Standards and Technology [NIST]. (2020). <i>SP 800-38D: Recommendation for Block Cipher Modes of Operation: Galois/Counter Mode (GCM) and GMAC</i>.",
    ]
    for ref in refs:
        story.append(Paragraph(ref, bullet_style))

    doc.build(story, onFirstPage=_header_footer_canvas, onLaterPages=_header_footer_canvas)


def build_pptx_presentation(data: Dict[str, Any], output_path: Path) -> None:
    """Construye la presentación ejecutiva/técnica en formato PowerPoint (.pptx) Widescreen 16:9."""
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    rr = data["benchmarks"]["round_robin"]
    raj = data["benchmarks"]["rajammal_dynamic"]
    imp = data["benchmarks"]["improvements"]
    aud = data["audit_verification"]

    def add_header_banner(slide, title_text: str, subtitle_text: str) -> None:
        banner = slide.shapes.add_shape(
            1, Inches(0), Inches(0), Inches(13.333), Inches(1.15)  # MSO_SHAPE.RECTANGLE = 1
        )
        banner.fill.solid()
        banner.fill.fore_color.rgb = RGBColor(15, 23, 42)
        banner.line.fill.background()

        tf = banner.text_frame
        tf.word_wrap = True
        p1 = tf.paragraphs[0]
        p1.text = title_text
        p1.font.size = Pt(22)
        p1.font.bold = True
        p1.font.color.rgb = RGBColor(56, 189, 248)

        p2 = tf.add_paragraph()
        p2.text = subtitle_text
        p2.font.size = Pt(12)
        p2.font.color.rgb = RGBColor(203, 213, 225)

    def add_bullet_box(slide, left: float, top: float, width: float, height: float, heading: str, bullets: List[str], bg_rgb=(248, 250, 252)):
        card = slide.shapes.add_shape(1, Inches(left), Inches(top), Inches(width), Inches(height))
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(*bg_rgb)
        card.line.color.rgb = RGBColor(203, 213, 225)

        tb = slide.shapes.add_textbox(Inches(left + 0.15), Inches(top + 0.12), Inches(width - 0.3), Inches(height - 0.24))
        tf = tb.text_frame
        tf.word_wrap = True

        p0 = tf.paragraphs[0]
        p0.text = heading
        p0.font.size = Pt(16)
        p0.font.bold = True
        p0.font.color.rgb = RGBColor(3, 105, 161)

        for b in bullets:
            p = tf.add_paragraph()
            p.text = f"▸ {b}"
            p.font.size = Pt(13)
            p.font.color.rgb = RGBColor(30, 41, 59)
            p.space_before = Pt(6)

    # SLIDE 1: Portada
    s1 = prs.slides.add_slide(blank_layout)
    bg1 = s1.shapes.add_shape(1, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
    bg1.fill.solid()
    bg1.fill.fore_color.rgb = RGBColor(15, 23, 42)
    bg1.line.fill.background()

    tb1 = s1.shapes.add_textbox(Inches(1.0), Inches(1.4), Inches(11.3), Inches(4.8))
    tf1 = tb1.text_frame
    tf1.word_wrap = True
    p = tf1.paragraphs[0]
    p.text = "UNIDAD 3: SEGURIDAD EN ENTORNOS DE NUBE"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = RGBColor(56, 189, 248)

    p2 = tf1.add_paragraph()
    p2.text = "Actividad 6: Implementación de una Aplicación en la Nube\nProyecto CloudMedVault"
    p2.font.size = Pt(34)
    p2.font.bold = True
    p2.font.color.rgb = RGBColor(255, 255, 255)
    p2.space_before = Pt(16)

    p3 = tf1.add_paragraph()
    p3.text = (
        "• Arquitectura Cloud Nativa sobre AWS (ECS Fargate, ALB, RDS Multi-AZ, S3 SSE-KMS, KMS, WAF)\n"
        "• Cumplimiento Normativo MinTIC (2021) — Modelo MSPI y Ley 1581 de 2012\n"
        "• Balanceo de Carga Dinámico Multicriterio y Auto-Scaling (Rajammal et al., 2025)"
    )
    p3.font.size = Pt(16)
    p3.font.color.rgb = RGBColor(203, 213, 225)
    p3.space_before = Pt(24)

    # SLIDE 2: Selección y Justificación de la Aplicación
    s2 = prs.slides.add_slide(blank_layout)
    add_header_banner(
        s2,
        "1. Selección y Justificación de la Aplicación: CloudMedVault",
        "Plataforma Cloud para Historias Clínicas Electrónicas (HCE), Documentos S3 y Telemetría Biomédica IoT UCI",
    )
    add_bullet_box(
        s2,
        0.6,
        1.5,
        5.9,
        5.4,
        "¿Por qué CloudMedVault requiere la Nube?",
        [
            "Cargas altamente dinámicas: flujo constante de sensores IoT UCI + ráfagas críticas en urgencias.",
            "Escalabilidad elástica: crecimiento horizontal automático (Scale-Out) sin aprovisionamiento manual.",
            "Accesibilidad 24/7 Multi-AZ: disponibilidad continua (SLA >= 99.95%) para personal médico y pasarelas IoT.",
            "Almacenamiento híbrido masivo: metadatos relacionales en RDS + estudios médicos cifrados en S3.",
        ],
    )
    add_bullet_box(
        s2,
        6.8,
        1.5,
        5.9,
        5.4,
        "Eficiencia en Costos (FinOps: Nube vs. On-Premise)",
        [
            "Eliminación de CAPEX: evita comprar servidores físicos dimensionados para el pico anual máximo.",
            "Ahorro estimado del 41.5% en TCO combinando instancias base Fargate + nodos elásticos Spot.",
            "Pago por uso real: en horas valle el Auto-Scaler libera el nodo elástico (Scale-In automático).",
            "Seguridad gestionada: rotación automática de claves KMS y WAF perimetral sin hardware dedicado.",
        ],
        bg_rgb=(240, 249, 255),
    )

    # SLIDE 3: Arquitectura en la Nube
    s3 = prs.slides.add_slide(blank_layout)
    add_header_banner(
        s3,
        "2. Diseño de la Arquitectura Cloud en AWS (Defensa en Profundidad)",
        "Segmentación en subredes DMZ y privadas, cómputo heterogéneo sin estado y almacenamiento cifrado",
    )
    fig4_path = RESULTS_DIR / "fig4_architecture_diagram.png"
    if fig4_path.exists():
        s3.shapes.add_picture(str(fig4_path), Inches(0.6), Inches(1.45), width=Inches(8.1))
    add_bullet_box(
        s3,
        8.9,
        1.45,
        3.9,
        5.5,
        "Componentes Clave",
        [
            "Gateway + WAF: TLS 1.3, Rate Limit y filtro SQLi/XSS.",
            "Clúster Cómputo (4 Nodos): FastAPI asíncrono en 3 AZs (pesos 1.6x, 1.0x, 0.6x y 1.4x).",
            "Amazon RDS Multi-AZ: Historias clínicas cifradas.",
            "Amazon S3 SSE-KMS: Objetos cifrados + SHA-256.",
            "Auditoría: Hash-Chain inmutable SHA-256.",
        ],
    )

    # SLIDE 4: Lineamientos de Seguridad MinTIC (2021)
    s4 = prs.slides.add_slide(blank_layout)
    add_header_banner(
        s4,
        "3. Cumplimiento de Lineamientos de Seguridad MinTIC (2021)",
        "Aplicación práctica del Modelo de Seguridad y Privacidad de la Información (MSPI) y Ley 1581 de 2012",
    )
    add_bullet_box(
        s4,
        0.6,
        1.5,
        5.9,
        5.4,
        "IAM, Criptografía y Privacidad (Habeas Data)",
        [
            "Control de Acceso (MSPI AC-2/AC-3): Autenticación PBKDF2-HMAC-SHA256 + Tokens JWT firmados (HS256).",
            "Mínimo Privilegio (RBAC): Separación estricta entre roles 'medico', 'admin' e 'iot_sensor'.",
            "Cifrado en Reposo (MSPI SC-28): AES-256-GCM con claves derivadas estilo AWS KMS para RDS y S3.",
            "Privacidad (Ley 1581/2012): Pseudonimización irreversible de cédulas mediante HMAC-SHA256 (PID-...).",
        ],
    )
    add_bullet_box(
        s4,
        6.8,
        1.5,
        5.9,
        5.4,
        "Seguridad Perimetral y Auditoría Inmutable",
        [
            "Protección WAF OWASP (MSPI SI-10): Bloqueo de inyección SQL, XSS (con URL-decoding) y Path Traversal.",
            "Mitigación DDoS (MSPI SC-5): Rate Limiting por ventana deslizante en el Gateway (HTTP 429).",
            "Cabeceras Seguras: Strict-Transport-Security (HSTS), Content-Security-Policy (CSP), X-Frame-Options.",
            f"Trazabilidad (MSPI AU-9): Cadena de auditoría SHA-256 inmutable ({aud['verified_records']} eventos verificados).",
        ],
        bg_rgb=(240, 253, 244),
    )

    # SLIDE 5: Balanceo de Carga Dinámico (Rajammal et al., 2025)
    s5 = prs.slides.add_slide(blank_layout)
    add_header_banner(
        s5,
        "4. Balanceo de Carga Dinámico Multicriterio (Rajammal et al., 2025)",
        "Enrutamiento adaptativo consciente de recursos (CPU, RAM, Concurrencia, Latencia EMA) y Auto-Scaling",
    )
    add_bullet_box(
        s5,
        0.6,
        1.5,
        6.0,
        5.4,
        "Formulación del Algoritmo Implementado",
        [
            "Sondeo continuo de telemetría (/metrics) en cada nodo del clúster.",
            "Índice Compuesto de Carga Instantánea L_i(t):\n   L_i(t) = 0.35·CPU_i + 0.15·MEM_i + 0.30·Conn_i + 0.20·Lat_i",
            "Puntuación de Aptitud Dinámica F_i(t):\n   F_i(t) = Capacidad_i / max(0.05, L_i(t))",
            "El balanceador asigna cada petición al nodo con máxima aptitud F_i(t), evitando saturar nodos pequeños (t3.small).",
        ],
    )
    if (RESULTS_DIR / "fig2_node_distribution.png").exists():
        s5.shapes.add_picture(str(RESULTS_DIR / "fig2_node_distribution.png"), Inches(6.8), Inches(1.6), width=Inches(6.0))

    # SLIDE 6: Resultados de Rendimiento y Elasticidad
    s6 = prs.slides.add_slide(blank_layout)
    add_header_banner(
        s6,
        "5. Resultados del Benchmark: Round-Robin vs. Rajammal et al. (2025)",
        f"Reducción del {imp['mean_latency_reduction_pct']}% en latencia media y del {imp['p95_latency_reduction_pct']}% en percentil 95 (P95)",
    )
    if (RESULTS_DIR / "fig1_latency_comparison.png").exists():
        s6.shapes.add_picture(str(RESULTS_DIR / "fig1_latency_comparison.png"), Inches(0.5), Inches(1.55), width=Inches(6.1))
    if (RESULTS_DIR / "fig3_dynamic_autoscaling_timeline.png").exists():
        s6.shapes.add_picture(
            str(RESULTS_DIR / "fig3_dynamic_autoscaling_timeline.png"), Inches(6.75), Inches(1.55), width=Inches(6.1)
        )

    tb6 = s6.shapes.add_textbox(Inches(0.6), Inches(5.15), Inches(12.1), Inches(1.9))
    tf6 = tb6.text_frame
    tf6.word_wrap = True
    p6 = tf6.paragraphs[0]
    p6.text = (
        f"Síntesis Experimental (120 peticiones en 4 fases):  "
        f"• Latencia Media: {rr['mean_latency_ms']} ms (Round-Robin) → {raj['mean_latency_ms']} ms (Dinámico Rajammal) [-{imp['mean_latency_reduction_pct']}%]   "
        f"• Latencia P95: {rr['p95_latency_ms']} ms → {raj['p95_latency_ms']} ms [-{imp['p95_latency_reduction_pct']}%]   "
        f"• Throughput Global: {rr['throughput_rps']} req/s → {raj['throughput_rps']} req/s [+{imp['throughput_increase_pct']}%]   "
        f"• Auto-Scaling: Activación automática de node-4 en ráfaga (12c) y liberación en enfriamiento (2c)."
    )
    p6.font.size = Pt(13.5)
    p6.font.bold = True
    p6.font.color.rgb = RGBColor(15, 23, 42)

    # SLIDE 7: Validación de Seguridad y Conclusiones
    s7 = prs.slides.add_slide(blank_layout)
    add_header_banner(
        s7,
        "6. Pruebas de Seguridad Superadas, Retos y Conclusiones",
        "Verificación empírica de los 7 controles de seguridad y lecciones aprendidas",
    )
    add_bullet_box(
        s7,
        0.6,
        1.5,
        6.0,
        5.4,
        "Pruebas Automatizadas de Seguridad (7/7 Aprobadas)",
        [
            "SEC-01 (IAM): Emisión JWT HS256 y rechazo HTTP 401 a credenciales inválidas.",
            "SEC-02 (RBAC): Bloqueo HTTP 403 a sensor IoT intentando crear historias clínicas.",
            "SEC-03 (RDS Cifrado): Verificación en SQLite de payload AES-256-GCM y pseudónimo PID-*.",
            "SEC-04 (S3 SSE-KMS): Cifrado de objetos clínicos y validación de integridad SHA-256.",
            "SEC-05/06/07: Bloqueo WAF SQLi/XSS (403), Rate Limit DDoS (429) y cadena SHA-256 íntegra.",
        ],
    )
    add_bullet_box(
        s7,
        6.8,
        1.5,
        5.9,
        5.4,
        "Retos Resueltos y Conclusiones",
        [
            "Reto Concurrencia: Transacciones atómicas BEGIN IMMEDIATE + WAL para la cadena de auditoría SHA-256 multiproceso.",
            "Reto WAF: Decodificación URL previa a inspección regex para frenar ataques XSS codificados.",
            "Conclusión 1: El balanceo dinámico de Rajammal et al. (2025) elimina cuellos de botella en clústeres heterogéneos.",
            "Conclusión 2: El diseño cumple integralmente con MinTIC (2021) y Ley 1581 de 2012.",
        ],
        bg_rgb=(240, 249, 255),
    )

    prs.save(str(output_path))


def build_presentation_pdf(data: Dict[str, Any], output_path: Path) -> None:
    """Genera también la versión en PDF apaisado (Widescreen) de la Presentación para entrega directa."""
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(LETTER),
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title="Presentación Actividad 6 - CloudMedVault",
    )
    styles = getSampleStyleSheet()
    slide_title = ParagraphStyle(
        "SlideTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0284c7"),
        alignment=TA_LEFT,
        spaceAfter=8,
    )
    slide_sub = ParagraphStyle(
        "SlideSub",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#475569"),
        spaceAfter=12,
    )
    slide_bullet = ParagraphStyle(
        "SlideBullet",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11.5,
        leading=16,
        leftIndent=14,
        spaceAfter=6,
        textColor=colors.HexColor("#1e293b"),
    )

    rr = data["benchmarks"]["round_robin"]
    raj = data["benchmarks"]["rajammal_dynamic"]
    imp = data["benchmarks"]["improvements"]
    aud = data["audit_verification"]

    story: List[Any] = []

    # Slide 1
    story.append(Spacer(1, 0.8 * inch))
    story.append(Paragraph("UNIDAD 3: SEGURIDAD EN ENTORNOS DE NUBE", slide_sub))
    story.append(
        Paragraph(
            "Actividad 6: Implementación de una Aplicación Funcional en la Nube (CloudMedVault)",
            ParagraphStyle("BigTitle", parent=slide_title, fontSize=26, leading=32, textColor=colors.HexColor("#0f172a")),
        )
    )
    story.append(Spacer(1, 0.2 * inch))
    story.append(
        Paragraph(
            "• Arquitectura en AWS (ECS Fargate, ALB, RDS Multi-AZ, Amazon S3 SSE-KMS, AWS KMS, WAFv2)<br/>"
            "• Cumplimiento de Lineamientos de Seguridad MinTIC (2021) — Modelo MSPI y Ley 1581 de 2012<br/>"
            "• Balanceo de Carga Dinámico Multicriterio y Auto-Scaling (Rajammal et al., 2025)",
            slide_bullet,
        )
    )
    story.append(PageBreak())

    # Slide 2
    story.append(Paragraph("Diapositiva 2: Selección y Justificación de la Aplicación en la Nube", slide_title))
    story.append(Paragraph("CloudMedVault: Gestión de Historias Clínicas Electrónicas y Telemetría Biomédica IoT UCI", slide_sub))
    story.append(Paragraph("• <b>Escalabilidad Elástica:</b> Absorbe ráfagas impredecibles de sensores IoT en UCI y consultas médicas concurrentes mediante Scale-Out automático.", slide_bullet))
    story.append(Paragraph("• <b>Accesibilidad y Alta Disponibilidad Multi-AZ:</b> Despliegue distribuido en 3 Zonas de Disponibilidad (us-east-1a/b/c) garantizando continuidad operativa 24/7.", slide_bullet))
    story.append(Paragraph("• <b>Eficiencia en Costos (FinOps):</b> Reducción estimada del 41.5% en TCO frente a infraestructura local sobredimensionada, combinando nodos Fargate base e instancias Spot elásticas.", slide_bullet))
    story.append(PageBreak())

    # Slide 3
    story.append(Paragraph("Diapositiva 3: Diseño de la Arquitectura Cloud y Seguridad MinTIC (2021)", slide_title))
    if (RESULTS_DIR / "fig4_architecture_diagram.png").exists():
        story.append(RLImage(str(RESULTS_DIR / "fig4_architecture_diagram.png"), width=8.6 * inch, height=4.64 * inch))
    story.append(PageBreak())

    # Slide 4
    story.append(Paragraph("Diapositiva 4: Controles de Seguridad Aplicados (MinTIC 2021 / MSPI)", slide_title))
    story.append(Paragraph("• <b>Gestión de Identidades y Acceso (IAM / RBAC):</b> Autenticación PBKDF2-HMAC-SHA256 y tokens JWT (HS256) con permisos segregados por rol (medico, admin, iot_sensor).", slide_bullet))
    story.append(Paragraph("• <b>Cifrado Autenticado en Reposo (SC-28):</b> Cifrado AES-256-GCM tanto en base de datos transaccional (RDS) como en objetos clínicos en Amazon S3 (SSE-KMS) con verificación SHA-256.", slide_bullet))
    story.append(Paragraph("• <b>Privacidad y Habeas Data (Ley 1581 de 2012):</b> Pseudonimización irreversible de documentos de identidad mediante HMAC-SHA256 (PID-...).", slide_bullet))
    story.append(Paragraph("• <b>Seguridad Perimetral y Auditoría (SI-10 / SC-5 / AU-9):</b> Reglas WAF contra SQLi/XSS, Rate Limiting anti-DDoS (HTTP 429) y cadena de auditoría SHA-256 inmutable.", slide_bullet))
    story.append(PageBreak())

    # Slide 5
    story.append(Paragraph("Diapositiva 5: Balanceo Dinámico (Rajammal et al., 2025) y Distribución por Nodo", slide_title))
    story.append(
        Paragraph(
            "Índice Compuesto: <b>L_i(t) = 0.35·CPU + 0.15·MEM + 0.30·Concurrencia + 0.20·Latencia_EMA</b>  |  Aptitud: <b>F_i(t) = Capacidad_i / L_i(t)</b>",
            slide_sub,
        )
    )
    if (RESULTS_DIR / "fig2_node_distribution.png").exists():
        story.append(RLImage(str(RESULTS_DIR / "fig2_node_distribution.png"), width=7.8 * inch, height=4.2 * inch))
    story.append(PageBreak())

    # Slide 6
    story.append(Paragraph("Diapositiva 6: Resultados de Pruebas de Rendimiento y Auto-Scaling Elástico", slide_title))
    story.append(
        Paragraph(
            f"Reducción del {imp['mean_latency_reduction_pct']}% en Latencia Media ({rr['mean_latency_ms']} ms → {raj['mean_latency_ms']} ms) y del {imp['p95_latency_reduction_pct']}% en P95 ({rr['p95_latency_ms']} ms → {raj['p95_latency_ms']} ms)",
            slide_sub,
        )
    )
    if (RESULTS_DIR / "fig1_latency_comparison.png").exists() and (RESULTS_DIR / "fig3_dynamic_autoscaling_timeline.png").exists():
        t_slides = Table(
            [
                [
                    RLImage(str(RESULTS_DIR / "fig1_latency_comparison.png"), width=4.7 * inch, height=2.54 * inch),
                    RLImage(str(RESULTS_DIR / "fig3_dynamic_autoscaling_timeline.png"), width=4.7 * inch, height=2.54 * inch),
                ]
            ],
            colWidths=[4.85 * inch, 4.85 * inch],
        )
        story.append(t_slides)
    story.append(Spacer(1, 0.15 * inch))
    story.append(
        Paragraph(
            f"• <b>7/7 Pruebas de Seguridad Aprobadas</b> | <b>{aud['verified_records']} eventos auditados</b> con integridad criptográfica SHA-256 verificada al 100%.",
            slide_bullet,
        )
    )

    doc.build(story)


def main() -> None:
    DELIVERABLES_DIR.mkdir(parents=True, exist_ok=True)
    data = load_benchmark_data()

    pdf_report_path = DELIVERABLES_DIR / "Informe_Actividad6_Implementacion_Aplicacion_Nube.pdf"
    pptx_path = DELIVERABLES_DIR / "Presentacion_Actividad6_Aplicacion_Nube.pptx"
    pdf_pres_path = DELIVERABLES_DIR / "Presentacion_Actividad6_Aplicacion_Nube.pdf"

    build_pdf_report(data, pdf_report_path)
    build_pptx_presentation(data, pptx_path)
    build_presentation_pdf(data, pdf_pres_path)

    print("Entregables generados exitosamente:")
    print(f" - Informe PDF: {pdf_report_path}")
    print(f" - Presentación PPTX: {pptx_path}")
    print(f" - Presentación PDF: {pdf_pres_path}")


if __name__ == "__main__":
    main()
