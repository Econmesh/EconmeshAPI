# ruff: noqa: E501 — templates HTML/CSS do PDF ficam mais legíveis em linhas longas.
"""PDF do Relatório de Diagnóstico de Maturidade Circular (``PdfReport``).

Reutiliza o PyMuPDF já adotado no projeto (contratos/acordos usam ``Story``):

* capa desenhada com a logo oficial da ECONMESH;
* conteúdo em HTML/CSS paginado pelo ``fitz.Story`` (quebra de página
  automática; tabelas, gráficos e cards não são cortados no meio);
* gráficos vetoriais desenhados com PyMuPDF e rasterizados em alta resolução
  (não dependem do navegador);
* cabeçalho, rodapé e paginação "Página X de Y" carimbados depois.

O PDF é renderizado a partir do ``MaturityReport`` persistido — os mesmos
dados do relatório web.
"""

from __future__ import annotations

import io
import math
import re
import unicodedata
from datetime import UTC, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import fitz

from src.modules.maturity_diagnostics.report_schema import (
    MaturityReport,
    ReportAxis,
)

# ---------------------------------------------------------------------------
# Identidade visual — cores extraídas da logo oficial (assets/econmesh-logo.png)
# ---------------------------------------------------------------------------
BRAND_GREEN = "#00593E"
BRAND_LEAF = "#5BA033"
BRAND_ORANGE = "#F07D12"
INK = "#1F2A24"
MUTED = "#5F6B66"
SURFACE = "#F2F7F4"
BORDER = "#D5E3DB"
TRACK = "#E4ECE8"
CRITICAL = "#B42318"
WARNING = "#B54708"

_ASSETS = Path(__file__).parent / "assets"
LOGO_PATH = _ASSETS / "econmesh-logo.png"

PAGE = fitz.paper_rect("a4")  # 595 x 842 pt
MARGIN_X = 48
CONTENT_TOP = 78
CONTENT_BOTTOM = 70


def _sao_paulo_tz() -> ZoneInfo | timezone:
    """Fuso de São Paulo; sem base de fusos no SO (ex.: Windows sem ``tzdata``),
    usa UTC−3 fixo — o Brasil não adota horário de verão desde 2019."""
    try:
        return ZoneInfo("America/Sao_Paulo")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=-3), "America/Sao_Paulo")


_TZ = _sao_paulo_tz()

_MONTHS = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
    "agosto", "setembro", "outubro", "novembro", "dezembro",
)  # fmt: skip


def _rgb(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(_TZ)


def _date(dt: datetime | None) -> str:
    local = _local(dt)
    return local.strftime("%d/%m/%Y") if local else "—"


def _month_year(dt: datetime | None) -> str:
    local = _local(dt)
    if local is None:
        return ""
    return f"{_MONTHS[local.month - 1].capitalize()} de {local.year}"


def _num(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "—"
    text = f"{value:,.{digits}f}".rstrip("0").rstrip(".") if digits else f"{value:,.0f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _cnpj(tax_id: str) -> str:
    d = "".join(ch for ch in tax_id if ch.isdigit())
    if len(d) != 14:
        return tax_id
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def _e(text: object) -> str:
    return escape("" if text is None else str(text))


def report_filename(report: MaturityReport) -> str:
    name = unicodedata.normalize("NFKD", report.company.trade_name or report.company.legal_name)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.encode("ascii", "ignore").decode()).strip("-")
    stamp = (_local(report.diagnostic.completed_at) or _local(report.generated_at))
    return f"diagnostico-maturidade-circular-{slug.lower() or 'empresa'}-{stamp:%Y%m%d}.pdf"


# ---------------------------------------------------------------------------
# Gráficos (vetoriais → PNG em alta resolução)
# ---------------------------------------------------------------------------
_CHART_SCALE = 3.0  # 216 dpi


def _text(page: fitz.Page, rect: fitz.Rect, text: str, *, size: float = 9,
          color: str = INK, bold: bool = False, align: str = "left") -> None:
    weight = "bold" if bold else "normal"
    page.insert_htmlbox(
        rect,
        f'<div style="font-family:sans-serif;font-size:{size}pt;color:{color};'
        f'font-weight:{weight};text-align:{align};line-height:1.15">'
        f"{'<br/>'.join(_e(line) for line in text.split(chr(10)))}</div>",
    )


def _render(page: fitz.Page) -> bytes:
    pix = page.get_pixmap(matrix=fitz.Matrix(_CHART_SCALE, _CHART_SCALE), alpha=False)
    return pix.tobytes("png")


def chart_axes_radar(axes: list[ReportAxis]) -> bytes:
    """Radar da maturidade por eixo (somente eixos avaliados)."""
    evaluated = [a for a in axes if a.status == "evaluated" and a.percent is not None]
    doc = fitz.open()
    width, height = 520, 340
    page = doc.new_page(width=width, height=height)
    cx, cy, radius = width / 2, height / 2 + 6, 112
    n = len(evaluated)
    angles = [-math.pi / 2 + i * 2 * math.pi / n for i in range(n)]
    shape = page.new_shape()
    for ring in (25, 50, 75, 100):
        points = [
            fitz.Point(cx + radius * ring / 100 * math.cos(a), cy + radius * ring / 100 * math.sin(a))
            for a in angles
        ]
        shape.draw_polyline([*points, points[0]])
        shape.finish(color=_rgb(BORDER), width=0.6)
    for a in angles:
        shape.draw_line((cx, cy), (cx + radius * math.cos(a), cy + radius * math.sin(a)))
        shape.finish(color=_rgb(BORDER), width=0.6)
    data = [
        fitz.Point(
            cx + radius * (axis.percent or 0) / 100 * math.cos(a),
            cy + radius * (axis.percent or 0) / 100 * math.sin(a),
        )
        for axis, a in zip(evaluated, angles, strict=True)
    ]
    shape.draw_polyline([*data, data[0]])
    shape.finish(color=_rgb(BRAND_GREEN), fill=_rgb(BRAND_LEAF), fill_opacity=0.28, width=2)
    for point in data:
        shape.draw_circle(point, 3.5)
        shape.finish(color=(1, 1, 1), fill=_rgb(BRAND_GREEN), width=1.2)
    shape.commit()
    for ring in (50, 100):
        _text(page, fitz.Rect(cx + 3, cy - radius * ring / 100 - 11, cx + 40, cy - radius * ring / 100),
              f"{ring}%", size=6.5, color=MUTED)
    for axis, a in zip(evaluated, angles, strict=True):
        lx = cx + (radius + 18) * math.cos(a)
        ly = cy + (radius + 18) * math.sin(a)
        box_w = 120
        if abs(math.cos(a)) < 0.2:
            rect = fitz.Rect(lx - box_w / 2, ly - (26 if math.sin(a) < 0 else -2), lx + box_w / 2, ly + 30)
            align = "center"
        elif math.cos(a) > 0:
            rect = fitz.Rect(lx, ly - 12, lx + box_w, ly + 24)
            align = "left"
        else:
            rect = fitz.Rect(lx - box_w, ly - 12, lx, ly + 24)
            align = "right"
        _text(page, rect, f"{axis.short_title}\n{_num(axis.percent)}%", size=9.5, bold=True,
              align=align)
    png = _render(page)
    doc.close()
    return png


def chart_hbars(items: list[tuple[str, float | None, str]], *, title: str | None = None) -> bytes:
    """Barras horizontais 0–100% (rótulo, percentual, texto à direita)."""
    doc = fitz.open()
    row_h = 30
    top = 26 if title else 8
    width, height = 480, top + row_h * len(items) + 8
    page = doc.new_page(width=width, height=height)
    if title:
        _text(page, fitz.Rect(0, 2, width, 22), title, size=9.5, bold=True)
    label_w, value_w = 150, 70
    bar_x0, bar_x1 = label_w + 8, width - value_w - 6
    shape = page.new_shape()
    for i, (_, percent, _) in enumerate(items):
        y = top + i * row_h + 10
        shape.draw_rect(fitz.Rect(bar_x0, y, bar_x1, y + 10))
        shape.finish(fill=_rgb(TRACK), color=None, width=0)
        if percent:
            x = bar_x0 + (bar_x1 - bar_x0) * min(percent, 100) / 100
            shape.draw_rect(fitz.Rect(bar_x0, y, x, y + 10))
            shape.finish(fill=_rgb(BRAND_GREEN), color=None, width=0)
    shape.commit()
    for i, (label, _, value) in enumerate(items):
        y = top + i * row_h
        _text(page, fitz.Rect(0, y + 5, label_w, y + 28), label, size=8.5, align="right")
        _text(page, fitz.Rect(bar_x1 + 6, y + 6, width, y + 28), value, size=8.5, bold=True)
    png = _render(page)
    doc.close()
    return png


def chart_score_ring(percent: float | None, center_text: str, caption: str) -> bytes:
    """Anel com o percentual do score geral."""
    doc = fitz.open()
    size = 170
    page = doc.new_page(width=size, height=size)
    c = fitz.Point(size / 2, size / 2)
    r = 66
    shape = page.new_shape()
    shape.draw_circle(c, r)
    shape.finish(color=_rgb(TRACK), width=13)
    value = max(0.0, min(percent or 0.0, 100.0))
    if value > 0:
        steps = max(2, int(value * 1.2))
        start = -math.pi / 2
        points = [
            fitz.Point(c.x + r * math.cos(start + 2 * math.pi * value / 100 * t / steps),
                       c.y + r * math.sin(start + 2 * math.pi * value / 100 * t / steps))
            for t in range(steps + 1)
        ]
        shape.draw_polyline(points)
        shape.finish(color=_rgb(BRAND_GREEN), width=13, lineCap=1, closePath=False)
    shape.commit()
    _text(page, fitz.Rect(20, c.y - 26, size - 20, c.y + 8), center_text, size=24, bold=True,
          color=BRAND_GREEN, align="center")
    _text(page, fitz.Rect(20, c.y + 6, size - 20, c.y + 26), caption, size=8, color=MUTED,
          align="center")
    png = _render(page)
    doc.close()
    return png


# ---------------------------------------------------------------------------
# HTML do conteúdo
# ---------------------------------------------------------------------------
_CSS = f"""
* {{ font-family: sans-serif; }}
body {{ font-size: 9.5pt; color: {INK}; line-height: 1.45; margin: 0; padding: 0; }}
h1 {{ font-size: 17pt; color: {BRAND_GREEN}; margin: 0 0 4pt 0; }}
h2 {{ font-size: 13.5pt; color: {BRAND_GREEN}; margin: 18pt 0 8pt 0; padding-bottom: 4pt;
      border-bottom: 1.5pt solid {BRAND_LEAF}; }}
h3 {{ font-size: 10.5pt; color: {INK}; margin: 12pt 0 5pt 0; }}
p {{ margin: 0 0 6pt 0; }}
.newpage {{ page-break-before: always; }}
.muted {{ color: {MUTED}; }}
.small {{ font-size: 8pt; }}
.eyebrow {{ font-size: 7.5pt; color: {MUTED}; text-transform: uppercase; letter-spacing: 0.6pt; }}
table {{ width: 100%; border-collapse: collapse; margin: 0 0 8pt 0; }}
th {{ background-color: {BRAND_GREEN}; color: #ffffff; font-size: 8pt; text-align: left;
      padding: 4pt 6pt; }}
td {{ border-bottom: 0.6pt solid {BORDER}; padding: 4pt 6pt; vertical-align: top; font-size: 8.8pt; }}
.card {{ background-color: {SURFACE}; border-left: 2.5pt solid {BRAND_LEAF};
         padding: 6pt 9pt; margin: 0 0 6pt 0; }}
.field {{ margin: 0 0 5pt 0; }}
.qa {{ margin: 0 0 5pt 0; padding-left: 4pt; }}
.subhead {{ font-size: 8pt; font-weight: bold; color: {BRAND_GREEN}; text-transform: uppercase;
            margin: 8pt 0 4pt 0; letter-spacing: 0.4pt; }}
.score {{ font-size: 13pt; font-weight: bold; color: {BRAND_GREEN}; }}
table.plain td {{ border: none; padding: 0; }}
.kpi td {{ border-top: 2pt solid {BRAND_LEAF}; padding: 5pt 7pt 5pt 0; }}
.kpi p {{ margin: 0; }}
.kpi .value {{ font-size: 15pt; font-weight: bold; color: {BRAND_GREEN}; }}
.kpi .label {{ font-size: 6.5pt; color: {MUTED}; text-transform: uppercase; }}
.tag {{ font-size: 7.5pt; font-weight: bold; }}
.ok {{ color: {BRAND_GREEN}; }}
.warn {{ color: {WARNING}; }}
.crit {{ color: {CRITICAL}; }}
.num {{ font-size: 15pt; font-weight: bold; color: {BRAND_ORANGE}; }}
.center {{ text-align: center; }}
"""


def bar_png(percent: int) -> bytes:
    """Barra de progresso (0–100) em PNG — usada inline no HTML do PDF."""
    doc = fitz.open()
    width, height = 400, 7
    page = doc.new_page(width=width, height=height)
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(0, 0, width, height))
    shape.finish(fill=_rgb(TRACK), color=None, width=0)
    if percent > 0:
        shape.draw_rect(fitz.Rect(0, 0, width * min(percent, 100) / 100, height))
        shape.finish(fill=_rgb(BRAND_GREEN), color=None, width=0)
    shape.commit()
    png = _render(page)
    doc.close()
    return png


def _bar(percent: float | None, used: set[int]) -> str:
    value = round(max(0.0, min(percent or 0.0, 100.0)))
    used.add(value)
    return f"<p style='margin:3pt 0 3pt 0'><img src='bar_{value}.png' width='499' height='8'/></p>"


_ORIGIN = {
    "registry": ("Dado cadastral", "ok"),
    "adjusted": ("Ajustado no diagnóstico", "warn"),
    "diagnostic": ("Coletado no diagnóstico", "muted"),
}
_SEVERITY = {
    "critical": ("Risco crítico", "crit"),
    "high": ("Atenção", "warn"),
    "moderate": ("Atenção moderada", "warn"),
}
_TIER_TONE = {"high": "ok", "medium": "warn", "low": "crit"}


class _Blocks:
    """Blocos indivisíveis do conteúdo.

    Títulos ficam pendentes e são anexados ao bloco seguinte (nunca ficam
    sozinhos no pé da página); cada bloco só é quebrado entre páginas se for
    maior que uma página inteira.
    """

    def __init__(self) -> None:
        self.items: list[tuple[str, bool]] = []
        self._pending: list[str] = []
        self._break = False

    def head(self, html: str, *, new_page: bool = False) -> None:
        self._pending.append(html)
        self._break = self._break or new_page

    def append(self, html: str) -> None:
        self.items.append(("".join(self._pending) + html, self._break))
        self._pending = []
        self._break = False


def build_report_blocks(  # noqa: PLR0915
    report: MaturityReport, bars: set[int] | None = None
) -> list[tuple[str, bool]]:
    """Blocos HTML do conteúdo (capa à parte): ``[(html, quebra_antes)]``.

    ``bars`` recebe os percentuais das barras usadas (renderizadas como PNG).
    """
    used: set[int] = bars if bars is not None else set()
    parts = _Blocks()
    head = parts.head
    counter = 0

    def section(title: str, *, new_page: bool = False) -> None:
        nonlocal counter
        counter += 1
        head(f"<h2>{counter}. {_e(title)}</h2>", new_page=new_page and counter > 1)

    def card(inner: str) -> None:
        parts.append(f"<div class='card'>{inner}</div>")

    summary = report.summary

    # 1. Identificação ------------------------------------------------------
    section("Identificação da Empresa")
    parts.append(
        "<p class='small muted'>Origem das informações: <span class='ok tag'>Dado cadastral</span>"
        " · <span class='warn tag'>Ajustado no diagnóstico</span> · "
        "<span class='muted tag'>Coletado no diagnóstico</span></p>"
    )
    for field in report.identification:
        label, tone = _ORIGIN[field.origin]
        parts.append(
            f"<p class='field'><span class='eyebrow'>{_e(field.label)}</span><br/>"
            f"<b>{_e(field.value or '—')}</b> &nbsp;<span class='tag {tone}'>{label}</span></p>"
        )
    parts.append(
        f"<p class='field'><span class='eyebrow'>Agente DMC responsável</span><br/>"
        f"<b>{_e(report.agent.name or report.agent.email or '—')}</b></p>"
        f"<p class='field'><span class='eyebrow'>Data do diagnóstico</span><br/>"
        f"<b>{_date(report.diagnostic.completed_at)}</b></p>"
    )

    # 2. Resumo executivo ---------------------------------------------------
    section("Resumo Executivo", new_page=True)
    level = summary.maturity_level
    if level:
        level_html = (
            f"<b>Nível {level.level} — {_e(level.name)}</b><br/>"
            f"<span class='muted small'>{_e(level.description)}</span>"
        )
    else:
        reason = (
            "A régua oficial de maturidade ainda não está cadastrada."
            if not summary.maturity_scale_defined
            else "A classificação é aplicada apenas com todos os eixos avaliados."
        )
        level_html = f"<b>Nível: não classificado</b><br/><span class='muted small'>{reason}</span>"
    parts.append(
        "<table class='plain'><tr><td style='width:170pt'><img src='score.png' width='150'/></td>"
        "<td style='vertical-align:middle'>"
        "<p class='eyebrow'>Maturidade circular — score geral (EMS)</p>"
        f"<p style='font-size:12pt'><b>{_e(summary.headline)}</b></p>"
        f"<p>{level_html}</p>"
        + (
            "<p class='small warn'>Score parcial: nem todos os eixos foram avaliados.</p>"
            if summary.partial
            else ""
        )
        + "</td></tr></table>"
    )
    kpis = [
        ("Score geral", _num(summary.overall_score, 2), f"de {_num(summary.overall_max, 2)}")
    ]
    for axis in report.axes:
        if axis.status == "evaluated":
            kpis.append((axis.short_title, f"{_num(axis.percent)}%", "do eixo"))
        else:
            kpis.append((axis.short_title, "—", "Em manutenção"))
    cells = "".join(
        f"<td><p class='label'>{_e(label)}</p><p class='value'>{_e(value)}</p>"
        f"<p class='small muted'>{_e(caption)}</p></td>"
        for label, value, caption in kpis
    )
    parts.append(f"<table class='kpi'><tr>{cells}</tr></table>")
    for paragraph in report.conclusions[:2]:
        parts.append(f"<p>{_e(paragraph)}</p>")

    # 3. Visão geral --------------------------------------------------------
    section("Visão Geral da Maturidade Circular")
    evaluated = [a for a in report.axes if a.status == "evaluated"]
    if evaluated:
        caption = (
            "Maturidade por eixo (% do máximo ponderado). Eixos não avaliados não são plotados."
        )
        parts.append(
            f"<p class='center'><img src='axes.png' width='400'/></p>"
            f"<p class='center small muted'>{caption}</p>"
        )
    for axis in report.axes:
        if axis.status == "evaluated":
            status = (
                f"<span class='ok tag'>Avaliado</span> · {_num(axis.percent)}% · "
                f"{_num(axis.ems_points)} de {_num(axis.ems_max)} pontos no EMS"
            )
        else:
            status = "<span class='warn tag'>Em manutenção</span> · não avaliado"
        parts.append(f"<p class='field'><b>{_e(axis.title)}</b><br/>{status}</p>")
    if not report.scope.complete:
        card(f"<p class='small' style='margin:0'>{_e(report.scope.text)}</p>")

    # 4. Resultados por eixo ------------------------------------------------
    section("Resultados por Eixo")
    for axis in report.axes:
        if axis.status != "evaluated":
            card(
                f"<p style='margin:0'><b>{_e(axis.title)}</b> — "
                "<span class='warn tag'>Em manutenção</span></p>"
                "<p class='small muted' style='margin:0'>Eixo não avaliado neste diagnóstico.</p>"
            )
            continue
        card(
            f"<p style='margin:0'><b>{_e(axis.title)}</b> &nbsp;"
            f"<span class='score'>{_num(axis.percent)}%</span></p>"
            f"<p class='small muted' style='margin:0'>{_e(axis.description or '')}</p>"
            f"{_bar(axis.percent, used)}"
            f"<p class='small muted' style='margin:0'>{axis.scored_questions} indicadores "
            f"pontuados · {_num(axis.ems_points)} de {_num(axis.ems_max)} pontos no EMS · "
            f"{_e(axis.reading or '')}</p>"
        )

    # 5. Pilares ------------------------------------------------------------
    section("Resultados por Pilar")
    parts.append("<p class='center'><img src='pillars.png' width='420'/></p>")
    for pillar in report.pillars:
        weight = (
            f"Peso no modelo: {_num(pillar.ems_weight)}%" if pillar.ems_weight is not None else ""
        )
        card(
            f"<p style='margin:0'><b>{_e(pillar.name)}</b> &nbsp;"
            f"<span class='score'>{pillar.points}</span>"
            f"<span class='muted'> / {pillar.max_points}</span></p>"
            f"<p class='small muted' style='margin:0'>{_e(weight)} · {pillar.answered} de "
            f"{pillar.total} indicadores respondidos</p>"
            f"{_bar(pillar.percent, used)}"
            f"<p class='small muted' style='margin:0'>{_num(pillar.percent)}% do máximo do pilar · "
            f"contribuição de {_num(pillar.ems_points, 2)} de {_num(pillar.ems_max, 2)} pontos no "
            f"EMS · {_e(pillar.reading or '')}</p>"
        )

    # 6. Indicadores --------------------------------------------------------
    section("Indicadores Avaliados", new_page=True)
    by_pillar: dict[str, list] = {}
    for indicator in report.indicators:
        by_pillar.setdefault(indicator.pillar_id or "", []).append(indicator)
    for pillar in report.pillars:
        items = by_pillar.get(pillar.pillar_id, [])
        if not items:
            continue
        head(f"<h3>{_e(pillar.name)}</h3>")
        for ind in items:
            tone = _TIER_TONE.get(ind.tier, "muted")
            points = "—" if ind.points is None else str(ind.points)
            card(
                f"<p style='margin:0'><span class='muted small'>{_e(ind.code or '')}</span> "
                f"<b>{_e(ind.title)}</b> &nbsp;<span class='tag {tone}' style='font-size:10pt'>"
                f"{points}/{ind.max_points} pontos</span></p>"
                f"<p class='small muted' style='margin:0'>{_e(ind.label)}</p>"
                f"{_bar(ind.percent, used)}"
                f"<p style='margin:0'><b>Resposta:</b> {_e(ind.answer or 'Não respondida')}</p>"
                f"<p class='small' style='margin:2pt 0 0 0'>{_e(ind.interpretation or '')}</p>"
                f"<p class='small muted' style='margin:2pt 0 0 0'>Peso no pilar: "
                f"{_num(ind.pillar_weight)}% · Peso no EMS: {_num(ind.ems_weight, 2)}%</p>"
            )

    # 7–9. Destaques, atenção, oportunidades -------------------------------
    section("Pontos de Destaque", new_page=True)
    if report.strengths:
        for item in report.strengths:
            card(
                f"<p style='margin:0' class='ok'><b>✓ {_e(item.title)}</b></p>"
                f"<p class='small' style='margin:0'>{_e(item.text)}</p>"
            )
    else:
        parts.append("<p class='muted'>Nenhum indicador atingiu a faixa de destaque.</p>")

    section("Pontos de Atenção")
    if report.attention_points:
        for item in report.attention_points:
            label, tone = _SEVERITY.get(item.severity or "moderate", ("Atenção", "warn"))
            card(
                f"<p style='margin:0' class='{tone}'><b>! {_e(item.title)}</b> "
                f"<span class='tag'>({label})</span></p>"
                f"<p class='small' style='margin:0'>{_e(item.text)}</p>"
            )
    else:
        parts.append("<p class='muted'>Nenhum ponto de atenção identificado nas respostas.</p>")

    section("Oportunidades de Melhoria")
    if report.opportunities:
        for opp in report.opportunities:
            card(
                f"<p style='margin:0'><span class='num'>{opp.number:02d}</span> &nbsp;"
                f"<b>{_e(opp.title)}</b></p>"
                f"<p class='small' style='margin:0'>{_e(opp.text)}</p>"
            )
        parts.append(
            "<p class='small muted'>Oportunidades derivadas das respostas registradas; não "
            "constituem recomendação técnica definitiva.</p>"
        )
    else:
        parts.append("<p class='muted'>Nenhuma oportunidade derivada das respostas.</p>")

    # 10. Análise -----------------------------------------------------------
    section("Análise do Diagnóstico", new_page=True)
    for title, items in (
        ("Dados observados", report.analysis.observed_data),
        ("Indicadores calculados", report.analysis.calculated_indicators),
        ("Interpretação", report.analysis.interpretation),
        ("Oportunidades", report.analysis.opportunities),
    ):
        head(f"<h3>{title}</h3>")
        if items:
            parts.append("<ul>" + "".join(f"<li>{_e(i)}</li>" for i in items) + "</ul>")
        else:
            parts.append("<p class='muted small'>Sem registros.</p>")

    # 11. Conclusão ---------------------------------------------------------
    section("Conclusão do Diagnóstico")
    for paragraph in report.conclusions:
        parts.append(f"<p>{_e(paragraph)}</p>")

    # 12. Escopo ------------------------------------------------------------
    section("Escopo e Limitações")
    parts.append(f"<p>{_e(report.scope.text)}</p>")
    evaluated_list = "".join(f"<li>{_e(a)}</li>" for a in report.scope.evaluated_axes)
    pending_list = "".join(f"<li>{_e(a)}</li>" for a in report.scope.pending_axes)
    head("<h3>Eixos avaliados</h3>")
    parts.append(f"<ul>{evaluated_list or '<li>—</li>'}</ul>")
    head("<h3>Eixos não avaliados</h3>")
    parts.append(f"<ul>{pending_list or '<li>Nenhum</li>'}</ul>")

    # 13. Metodologia -------------------------------------------------------
    section("Metodologia", new_page=True)
    m = report.methodology
    parts.append(f"<p>{_e(m.objective)}</p>")

    def bullet_block(title: str, items: list[str]) -> None:
        head(f"<h3>{_e(title)}</h3>")
        parts.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")

    bullet_block(
        "Eixos",
        [
            f"<b>{_e(a.title)}</b>{': ' + _e(a.description) if a.description else ''}"
            for a in m.axes
        ],
    )
    bullet_block(
        "Pilares de cálculo",
        [f"<b>{_e(p.title)}</b> {_e(p.description or '')}" for p in m.pillars],
    )
    bullet_block("Pontuação", [_e(x) for x in m.scoring])
    if m.maturity_scale:
        bullet_block(
            "Níveis de maturidade",
            [f"<b>{_e(i.title)}</b> {_e(i.description or '')}" for i in m.maturity_scale],
        )
    v = report.versions
    head("<h3>Significado dos resultados</h3>")
    parts.append(
        "<ul>" + "".join(f"<li>{_e(x)}</li>" for x in m.results) + "</ul>"
        + (f"<p class='small muted'>{_e(m.maturity_scale_note)}</p>" if m.maturity_scale_note else "")
        + f"<p class='small muted'>Versões — questionário {_e(v.diagnostic_version)} · "
        f"metodologia {_e(v.methodology_version)} · relatório {_e(v.report_version)}</p>"
    )

    # 14. Respostas ---------------------------------------------------------
    section("Resumo das Respostas", new_page=True)
    for step in report.answers:
        head(f"<h3>{_e(step.title)}</h3>")
        if step.status == "maintenance":
            parts.append("<p class='small warn'>Em manutenção — não avaliado.</p>")
            continue
        for sec in step.sections:
            head(f"<p class='subhead'>{_e(sec.title)}</p>")
            for ans in sec.answers:
                score = ""
                if ans.scored:
                    points = "—" if ans.points is None else str(ans.points)
                    score = (
                        f" &nbsp;<span class='tag ok'>{points}/{ans.max_points} pts"
                        f"{' · ' + _e(ans.pillar_code) if ans.pillar_code else ''}</span>"
                    )
                parts.append(
                    f"<p class='qa'><span class='muted small'>{_e(ans.code or '')}</span> "
                    f"{_e(ans.label)}<br/><b>{_e(ans.answer or '—')}</b>{score}</p>"
                )

    return parts.items


def build_report_html(report: MaturityReport) -> str:
    """HTML contínuo do conteúdo (útil para inspeção/testes)."""
    body = "".join(html for html, _ in build_report_blocks(report))
    title = f"{_e(report.company.legal_name)} — Diagnóstico de Maturidade Circular"
    return f"<html><head><title>{title}</title></head><body>{body}</body></html>"


# ---------------------------------------------------------------------------
# Montagem
# ---------------------------------------------------------------------------
def _cover(doc: fitz.Document, report: MaturityReport) -> None:
    page = doc.new_page(width=PAGE.width, height=PAGE.height)
    w, h = PAGE.width, PAGE.height
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(0, 0, w, 10))
    shape.finish(fill=_rgb(BRAND_GREEN), color=None, width=0)
    shape.draw_rect(fitz.Rect(0, h - 210, w, h))
    shape.finish(fill=_rgb(BRAND_GREEN), color=None, width=0)
    shape.draw_rect(fitz.Rect(0, h - 216, w * 0.62, h - 210))
    shape.finish(fill=_rgb(BRAND_LEAF), color=None, width=0)
    shape.draw_rect(fitz.Rect(w * 0.62, h - 216, w, h - 210))
    shape.finish(fill=_rgb(BRAND_ORANGE), color=None, width=0)
    shape.commit()
    page.insert_image(fitz.Rect(w / 2 - 150, 120, w / 2 + 150, 195), filename=str(LOGO_PATH))
    company = report.company
    page.insert_htmlbox(
        fitz.Rect(60, 270, w - 60, 560),
        f"""<div style="font-family:sans-serif;text-align:center;color:{INK}">
        <p style="font-size:10pt;letter-spacing:2pt;color:{MUTED};margin:0">RELATÓRIO DIAGNÓSTICO</p>
        <p style="font-size:30pt;font-weight:bold;color:{BRAND_GREEN};line-height:1.1;margin:14pt 0 0 0">
        DIAGNÓSTICO DE<br/>MATURIDADE CIRCULAR</p>
        <p style="font-size:16pt;font-weight:bold;margin:34pt 0 4pt 0">{_e(company.legal_name)}</p>
        <p style="font-size:10pt;color:{MUTED};margin:0">CNPJ {_e(_cnpj(company.tax_id))}
        {(' · ' + _e(company.sector)) if company.sector else ''}</p>
        <p style="font-size:12pt;margin:26pt 0 0 0">{_e(_month_year(report.diagnostic.completed_at))}</p>
        </div>""",
    )
    agent = report.agent.name or report.agent.email or "—"
    page.insert_htmlbox(
        fitz.Rect(60, h - 170, w - 60, h - 40),
        f"""<div style="font-family:sans-serif;color:#ffffff;font-size:9.5pt">
        <table style="width:100%"><tr>
        <td style="width:50%"><span style="font-size:7.5pt;color:#cfe6d9">AGENTE DMC</span><br/>{_e(agent)}</td>
        <td><span style="font-size:7.5pt;color:#cfe6d9">DATA DO DIAGNÓSTICO</span><br/>{_date(report.diagnostic.completed_at)}</td>
        </tr><tr><td style="padding-top:12pt"><span style="font-size:7.5pt;color:#cfe6d9">RESPONSÁVEL NA EMPRESA</span><br/>{_e(report.contact.name or '—')}</td>
        <td style="padding-top:12pt"><span style="font-size:7.5pt;color:#cfe6d9">RELATÓRIO GERADO EM</span><br/>{_date(report.generated_at)}</td></tr></table>
        </div>""",
    )


def _content(report: MaturityReport) -> bytes:
    evaluated = [a for a in report.axes if a.status == "evaluated"]
    archive = fitz.Archive()
    summary = report.summary
    archive.add(
        chart_score_ring(
            summary.overall_percent,
            _num(summary.overall_score, 2),
            f"de {_num(summary.overall_max, 2)} pontos",
        ),
        "score.png",
    )
    if len(evaluated) >= 3:
        archive.add(chart_axes_radar(report.axes), "axes.png")
    elif evaluated:
        archive.add(
            chart_hbars([(a.short_title, a.percent, f"{_num(a.percent)}%") for a in evaluated],
                        title="Resultado por eixo (% do máximo ponderado)"),
            "axes.png",
        )
    archive.add(
        chart_hbars(
            [(p.name.split("—")[-1].strip() or p.code, p.percent,
              f"{p.points}/{p.max_points}") for p in report.pillars],
            title="Pontuação por pilar de cálculo",
        ),
        "pillars.png",
    )
    bars: set[int] = set()
    blocks = build_report_blocks(report, bars)
    for value in bars:
        archive.add(bar_png(value), f"bar_{value}.png")
    return _layout(blocks, archive)


def _layout(blocks: list[tuple[str, bool]], archive: fitz.Archive) -> bytes:
    """Pagina blocos sem cortá-los: se não couber no restante, vai para a próxima página."""
    frame = fitz.Rect(MARGIN_X, CONTENT_TOP, PAGE.width - MARGIN_X, PAGE.height - CONTENT_BOTTOM)
    buffer = io.BytesIO()
    writer = fitz.DocumentWriter(buffer)
    device = writer.begin_page(PAGE)
    cursor = frame.y0
    gap = 2

    def new_page() -> None:
        nonlocal device, cursor
        writer.end_page()
        device = writer.begin_page(PAGE)
        cursor = frame.y0

    for html, page_break in blocks:
        if page_break and cursor > frame.y0:
            new_page()
        measure = fitz.Story(html=html, user_css=_CSS, archive=archive)
        _, filled = measure.place(fitz.Rect(frame.x0, 0, frame.x1, 100_000))
        height = fitz.Rect(filled).height
        if cursor + height > frame.y1 and cursor > frame.y0:
            new_page()
        story = fitz.Story(html=html, user_css=_CSS, archive=archive)
        more = 1
        while more:
            more, placed = story.place(fitz.Rect(frame.x0, cursor, frame.x1, frame.y1))
            story.draw(device)
            cursor = fitz.Rect(placed).y1 + gap
            if more:  # bloco maior que uma página: continua na seguinte
                new_page()
    writer.end_page()
    writer.close()
    return buffer.getvalue()


def _stamp(doc: fitz.Document, report: MaturityReport) -> None:
    total = doc.page_count
    generated = _date(report.generated_at)
    company = report.company.trade_name or report.company.legal_name
    for index in range(1, total):
        page = doc[index]
        w, h = page.rect.width, page.rect.height
        page.insert_image(fitz.Rect(MARGIN_X, 26, MARGIN_X + 104, 52), filename=str(LOGO_PATH))
        page.insert_htmlbox(
            fitz.Rect(w / 2 - 40, 30, w - MARGIN_X, 52),
            f'<div style="font-family:sans-serif;font-size:7.5pt;color:{MUTED};text-align:right">'
            f"Diagnóstico de Maturidade Circular<br/><b>{_e(company)}</b></div>",
        )
        shape = page.new_shape()
        shape.draw_line((MARGIN_X, 58), (w - MARGIN_X, 58))
        shape.finish(color=_rgb(BRAND_LEAF), width=0.8)
        shape.draw_line((MARGIN_X, h - 52), (w - MARGIN_X, h - 52))
        shape.finish(color=_rgb(BORDER), width=0.6)
        shape.commit()
        page.insert_htmlbox(
            fitz.Rect(MARGIN_X, h - 46, w - MARGIN_X, h - 18),
            f'<table style="width:100%;font-family:sans-serif;font-size:7.5pt;color:{MUTED}"><tr>'
            f'<td><b style="color:{BRAND_GREEN}">ECONMESH</b> · Diagnóstico de Maturidade Circular'
            f"<br/>Relatório gerado em {generated}</td>"
            f'<td style="text-align:right;vertical-align:bottom">Página {index + 1} de {total}</td>'
            "</tr></table>",
        )


def render_report_pdf(report: MaturityReport) -> bytes:
    doc = fitz.open()
    _cover(doc, report)
    content = fitz.open(stream=_content(report), filetype="pdf")
    doc.insert_pdf(content)
    content.close()
    _stamp(doc, report)
    doc.set_metadata(
        {
            "title": f"Diagnóstico de Maturidade Circular — {report.company.legal_name}",
            "author": "ECONMESH",
            "subject": "Relatório de Diagnóstico de Maturidade Circular",
            "creator": f"ECONMESH · relatório {report.versions.report_version}",
        }
    )
    data = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return data


__all__ = [
    "build_report_html",
    "chart_axes_radar",
    "chart_hbars",
    "chart_score_ring",
    "render_report_pdf",
    "report_filename",
]
