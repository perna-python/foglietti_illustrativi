"""
Ricerca Farmaci AIFA
=====================

Applicazione desktop per la ricerca di farmaci nella banca dati AIFA
(Agenzia Italiana del Farmaco) e il download di foglietto illustrativo (FI)
e riassunto delle caratteristiche del prodotto (RCP).

Requisiti:
    pip install flet==0.86.5 httpx

Avvio:
    python ricerca_farmaci.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Callable, Optional

import flet as ft
import httpx

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ricerca_farmaci")


# --------------------------------------------------------------------------- #
# Configurazione API (INVARIATA)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class APIConfig:
    """Endpoint e parametri dell'API pubblica AIFA (Banca Dati Farmaci)."""

    base_url: str = "https://api.aifa.gov.it/aifa-bdf-eif-be/1.0.0"
    request_timeout: float = 15.0
    min_query_length: int = 3
    search_debounce_ms: int = 400

    @property
    def search_endpoint(self) -> str:
        return f"{self.base_url}/formadosaggio/ricerca"

    def documents_endpoint(self, codice_sis: str, aic6: str) -> str:
        return f"{self.base_url}/organizzazione/{codice_sis}/farmaci/{aic6}/stampati"


# --------------------------------------------------------------------------- #
# Design system: palette, spaziature, tipografia
# --------------------------------------------------------------------------- #
# Palette contenuta, molto spazio bianco, bordi sottili, shadow leggere,
# corner radius 16-20px, coerente sia in light che in dark mode.

LIGHT_PALETTE = {
    "bg": "#f5f6f8",
    "surface": "#ffffff",
    "surface_alt": "#f8f9fb",
    "border": "#e6e8ec",
    "primary": "#3D6BFF",
    "primary_soft": "#EEF2FF",
    "text": "#14161a",
    "text_muted": "#6b7280",
    "text_faint": "#9aa1ac",
    "success": "#0f9d58",
    "success_soft": "#E8F7EE",
    "danger": "#e0332f",
    "danger_soft": "#FDECEC",
    "warning": "#b7791f",
    "warning_soft": "#FFF6E0",
    "purple": "#7c4dff",
    "purple_soft": "#F1ECFF",
    "shadow_opacity": 0.06,
}

DARK_PALETTE = {
    "bg": "#0f1115",
    "surface": "#181b20",
    "surface_alt": "#1e2228",
    "border": "#2a2f38",
    "primary": "#7c9bff",
    "primary_soft": "#1c2440",
    "text": "#f2f3f5",
    "text_muted": "#a2a9b4",
    "text_faint": "#6e7480",
    "success": "#3ddc84",
    "success_soft": "#12291d",
    "danger": "#ff6b66",
    "danger_soft": "#391a1a",
    "warning": "#f2c14e",
    "warning_soft": "#332b12",
    "purple": "#b39bff",
    "purple_soft": "#241f3d",
    "shadow_opacity": 0.35,
}

RADIUS_LG = 20
RADIUS_MD = 16
RADIUS_SM = 10
SPACING_XS = 4
SPACING_SM = 8
SPACING_MD = 16
SPACING_LG = 24
SPACING_XL = 40


def card_shadow(palette: dict) -> ft.BoxShadow:
    return ft.BoxShadow(
        spread_radius=0,
        blur_radius=18,
        offset=ft.Offset(0, 6),
        color=ft.Colors.with_opacity(palette["shadow_opacity"], ft.Colors.BLACK),
    )


def soft_shadow(palette: dict) -> ft.BoxShadow:
    return ft.BoxShadow(
        spread_radius=0,
        blur_radius=8,
        offset=ft.Offset(0, 2),
        color=ft.Colors.with_opacity(palette["shadow_opacity"], ft.Colors.BLACK),
    )


# --------------------------------------------------------------------------- #
# Modelli dati (LOGICA E CAMPI INVARIATI)
# --------------------------------------------------------------------------- #
# Si usano dataclass con parsing "difensivo" (via .get) invece di indicizzare
# direttamente il dict di risposta: l'API AIFA non garantisce la presenza di
# tutti i campi per ogni farmaco, e un KeyError in produzione manda in crash
# l'intera schermata di dettaglio.
#
# Rispetto alla versione originale sono stati aggiunti solo due metodi di
# (de)serializzazione (to_dict / from_dict), usati esclusivamente per
# salvare preferiti/cronologia su disco: non toccano in alcun modo la
# logica di business o il parsing dei dati AIFA.

@dataclass
class Confezione:
    aic: str = "-"
    descrizione: str = "-"
    classe_rimborsabilita: str = "-"
    descrizione_rimborsabilita: str = "-"
    stato_amministrativo: str = "-"
    prescrizioni: list[str] = field(default_factory=list)
    in_carenza: bool = False
    carenza_inizio: str = "-"
    carenza_fine_presunta: str = "-"
    carenza_motivazione: str = "-"

    @classmethod
    def from_dict(cls, d: dict) -> "Confezione":
        return cls(
            aic=d.get("aic", "-"),
            descrizione=d.get("denominazionePackage", "-"),
            classe_rimborsabilita=d.get("classeRimborsabilita", "-"),
            descrizione_rimborsabilita=d.get("descrizioneRimborsabilita", "-"),
            stato_amministrativo=d.get("descrizioneStatoAmministrativo", "-"),
            prescrizioni=d.get("descrizioniRf") or [],
            in_carenza=bool(d.get("flagCarenza", False)),
            carenza_inizio=d.get("carenzaInizio") or "-",
            carenza_fine_presunta=d.get("carenzaFinePresunta") or "-",
            carenza_motivazione=d.get("carenzaMotivazione") or "-",
        )


@dataclass
class RisultatoFarmaco:
    """Rappresenta una forma/dosaggio di farmaco, come restituita dalla ricerca."""

    denominazione: str
    descrizione_forma_dosaggio: str
    codice_sis: str
    aic6: str
    forma_farmaceutica: str = "-"
    principi_attivi: list[str] = field(default_factory=list)
    vie_somministrazione: list[str] = field(default_factory=list)
    codice_atc: list[str] = field(default_factory=list)
    dopante: bool = False
    influenza_guida: bool = False
    interazione_alcol: bool = False
    interazione_potassio: bool = False
    confezioni: list[Confezione] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "RisultatoFarmaco":
        medicinale = d.get("medicinale", {})
        return cls(
            denominazione=medicinale.get("denominazioneMedicinale", "Sconosciuto"),
            descrizione_forma_dosaggio=d.get("descrizioneFormaDosaggio", "-"),
            codice_sis=medicinale.get("codiceSis", ""),
            aic6=medicinale.get("aic6", ""),
            forma_farmaceutica=d.get("formaFarmaceutica", "-"),
            principi_attivi=d.get("principiAttiviIt") or [],
            vie_somministrazione=d.get("vieSomministrazione") or [],
            codice_atc=d.get("codiceAtc") or [],
            dopante=bool(d.get("flagDopante", False)),
            influenza_guida=bool(d.get("flagGuida", False)),
            interazione_alcol=bool(d.get("flagAlcol", False)),
            interazione_potassio=bool(d.get("flagPotassio", False)),
            confezioni=[Confezione.from_dict(c) for c in d.get("confezioni", [])],
        )

    @property
    def titolo_ricerca(self) -> str:
        return f"{self.denominazione} - {self.descrizione_forma_dosaggio}"

    # -- Serializzazione per preferiti / cronologia (solo persistenza UI) -- #

    def to_cache_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_cache_dict(cls, d: dict) -> "RisultatoFarmaco":
        confezioni = [Confezione(**c) for c in d.get("confezioni", [])]
        payload = {**d, "confezioni": confezioni}
        return cls(**payload)


class APIError(RuntimeError):
    """Errore applicativo per fallimenti di rete o risposte HTTP non valide."""


# --------------------------------------------------------------------------- #
# Servizio API (LOGICA INVARIATA)
# --------------------------------------------------------------------------- #

class AIFAService:
    """
    Wrapper asincrono per l'API AIFA.

    Usa un unico httpx.AsyncClient riutilizzato per tutta la sessione
    (invece di aprirne uno nuovo a ogni chiamata) e non blocca mai
    l'event loop di Flet, a differenza di httpx sincrono usato dentro
    handler async.
    """

    def __init__(self, config: APIConfig):
        self._config = config
        self._client = httpx.AsyncClient(timeout=config.request_timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def search_medicines(self, query: str) -> list[RisultatoFarmaco]:
        params = {"query": query, "spellingCorrection": "true", "page": "0"}
        try:
            response = await self._client.get(self._config.search_endpoint, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Ricerca fallita per %r: %s", query, exc)
            raise APIError("Impossibile contattare il servizio AIFA. Riprova più tardi.") from exc

        payload = response.json()
        items = payload.get("data", {}).get("content", [])
        return [RisultatoFarmaco.from_dict(item) for item in items]

    async def download_document(self, codice_sis: str, aic6: str, doc_type: str) -> bytes:
        """Scarica un documento (FI o RCP) e ne restituisce i byte grezzi."""
        url = self._config.documents_endpoint(codice_sis, aic6)
        try:
            response = await self._client.get(url, params={"ts": doc_type})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Download %s fallito per aic6=%s: %s", doc_type, aic6, exc)
            raise APIError("Impossibile scaricare il documento richiesto.") from exc
        return response.content


# --------------------------------------------------------------------------- #
# Persistenza leggera (preferiti / cronologia / tema)
# --------------------------------------------------------------------------- #
# Usa lo storage locale del client se disponibile (page.shared_preferences
# nelle build più recenti di Flet, page.client_storage nelle precedenti);
# se non è disponibile (o fallisce) ricade su un dizionario in memoria, così
# l'app resta comunque utilizzabile per l'intera sessione.

class LocalStore:
    KEY_FAVORITES = "aifa.favorites"
    KEY_HISTORY = "aifa.history"
    KEY_DARK_MODE = "aifa.dark_mode"

    def __init__(self, page: ft.Page):
        self._page = page
        self._memory: dict[str, str] = {}
        self._backend = ft.SharedPreferences()
        self._page.services.append(self._backend)

    async def _get_raw(self, key: str) -> Optional[str]:
        if self._backend is not None:
            try:
                return await self._backend.get(key)
            except Exception:  # noqa: BLE001 - storage best-effort
                logger.debug("Storage locale non disponibile per get(%s)", key)
        return self._memory.get(key)

    async def _set_raw(self, key: str, value: str) -> None:
        if self._backend is not None:
            try:
                await self._backend.set(key, value)
                self._memory[key] = value
                return
            except Exception:  # noqa: BLE001 - storage best-effort
                logger.debug("Storage locale non disponibile per set(%s)", key)
        self._memory[key] = value

    async def load_favorites(self) -> list[RisultatoFarmaco]:
        raw = await self._get_raw(self.KEY_FAVORITES)
        if not raw:
            return []
        try:
            return [RisultatoFarmaco.from_cache_dict(d) for d in json.loads(raw)]
        except Exception:  # noqa: BLE001
            logger.warning("Impossibile leggere i preferiti salvati, verranno ignorati")
            return []

    async def save_favorites(self, favorites: list[RisultatoFarmaco]) -> None:
        raw = json.dumps([f.to_cache_dict() for f in favorites])
        await self._set_raw(self.KEY_FAVORITES, raw)

    async def load_history(self) -> list[RisultatoFarmaco]:
        raw = await self._get_raw(self.KEY_HISTORY)
        if not raw:
            return []
        try:
            return [RisultatoFarmaco.from_cache_dict(d) for d in json.loads(raw)]
        except Exception:  # noqa: BLE001
            logger.warning("Impossibile leggere la cronologia salvata, verrà ignorata")
            return []

    async def save_history(self, history: list[RisultatoFarmaco]) -> None:
        raw = json.dumps([h.to_cache_dict() for h in history])
        await self._set_raw(self.KEY_HISTORY, raw)

    async def load_dark_mode(self) -> bool:
        raw = await self._get_raw(self.KEY_DARK_MODE)
        return raw == "1"

    async def save_dark_mode(self, value: bool) -> None:
        await self._set_raw(self.KEY_DARK_MODE, "1" if value else "0")


# --------------------------------------------------------------------------- #
# Helper di dominio (badge, evidenziazione testo, apertura file)
# --------------------------------------------------------------------------- #

def classify_prescrizione(text: str, palette: dict) -> tuple[str, str]:
    """Restituisce (colore_sfondo, colore_testo) per una badge di prescrizione."""
    t = (text or "").upper()
    if "OSP" in t:
        return palette["warning_soft"], palette["warning"]
    if "RR" in t or "RICETTA RIPETIBILE" in t:
        return palette["primary_soft"], palette["primary"]
    if "RNR" in t:
        return palette["primary_soft"], palette["primary"]
    if "SOP" in t:
        return palette["success_soft"], palette["success"]
    if "OTC" in t:
        return palette["success_soft"], palette["success"]
    return palette["surface_alt"], palette["text_muted"]


def highlighted_text(full_text: str, query: str, size: int, weight, color: str) -> ft.Text:
    """Restituisce un ft.Text con la porzione corrispondente alla ricerca evidenziata."""
    query = (query or "").strip()
    if not query or len(query) < 2:
        return ft.Text(full_text, size=size, weight=weight, color=color)

    lower_text = full_text.lower()
    lower_query = query.lower()
    idx = lower_text.find(lower_query)
    if idx == -1:
        return ft.Text(full_text, size=size, weight=weight, color=color)

    before, match, after = (
        full_text[:idx],
        full_text[idx: idx + len(query)],
        full_text[idx + len(query):],
    )
    spans = []
    if before:
        spans.append(ft.TextSpan(before))
    spans.append(
        ft.TextSpan(
            match,
            style=ft.TextStyle(bgcolor=ft.Colors.with_opacity(0.35, ft.Colors.YELLOW), weight=ft.FontWeight.BOLD),
        )
    )
    if after:
        spans.append(ft.TextSpan(after))
    return ft.Text(spans=spans, size=size, weight=weight, color=color)


def open_path(path: Optional[str]) -> None:
    """Apre un file o una cartella con l'applicazione predefinita del sistema."""
    if not path:
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception:  # noqa: BLE001 - apertura file è best-effort
        logger.exception("Impossibile aprire il percorso %s", path)


# --------------------------------------------------------------------------- #
# Componenti UI riutilizzabili
# --------------------------------------------------------------------------- #

def Badge(text: str, bg: str, fg: str, icon: Optional[str] = None) -> ft.Container:
    row_controls: list[ft.Control] = []
    if icon:
        row_controls.append(ft.Icon(icon, size=13, color=fg))
    row_controls.append(ft.Text(text, size=11, weight=ft.FontWeight.W_600, color=fg))
    return ft.Container(
        content=ft.Row(row_controls, spacing=4, tight=True),
        bgcolor=bg,
        padding=ft.Padding.symmetric(horizontal=9, vertical=5),
        border_radius=999,
    )


def SectionTitle(title: str, subtitle: Optional[str], palette: dict) -> ft.Column:
    controls: list[ft.Control] = [ft.Text(title, size=13, weight=ft.FontWeight.W_700, color=palette["text_muted"])]
    if subtitle:
        controls.append(ft.Text(subtitle, size=12, color=palette["text_faint"]))
    return ft.Column(controls, spacing=2)


def InfoTile(
    icon: str,
    label: str,
    value: str,
    palette: dict,
    page: Optional[ft.Page] = None,
    copyable: bool = False,
) -> ft.Container:
    value_text = ft.Text(value or "-", size=14, weight=ft.FontWeight.W_500, color=palette["text"], selectable=True)

    trailing: list[ft.Control] = []
    if copyable and page is not None and value and value != "-":
        async def _copy(e: ft.ControlEvent, v=value, lbl=label) -> None:
            try:
                await ft.Clipboard().set(v)
            except Exception:  # noqa: BLE001
                page.set_clipboard(v)  # fallback per build meno recenti
            page.show_dialog(
                ft.SnackBar(content=ft.Text(f"{lbl} copiato negli appunti"), bgcolor=palette["success"])
            )

        trailing.append(
            ft.IconButton(
                icon=ft.Icons.CONTENT_COPY,
                icon_size=15,
                icon_color=palette["text_faint"],
                tooltip=f"Copia {label.lower()}",
                on_click=lambda e, v=value, lbl=label: page.run_task(_copy, e, v, lbl),
            )
        )

    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(icon, size=17, color=palette["text_faint"]),
                ft.Column(
                    [
                        ft.Text(label, size=11, color=palette["text_faint"], weight=ft.FontWeight.W_600),
                        value_text,
                    ],
                    spacing=1,
                    expand=True,
                ),
                *trailing,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        bgcolor=palette["surface_alt"],
        border_radius=RADIUS_SM,
    )


def EmptyState(icon: str, title: str, subtitle: str, palette: dict) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Icon(icon, size=40, color=palette["primary"]),
                    width=84,
                    height=84,
                    bgcolor=palette["primary_soft"],
                    border_radius=999,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Text(title, size=17, weight=ft.FontWeight.W_700, color=palette["text"]),
                ft.Text(subtitle, size=13, color=palette["text_muted"], text_align=ft.TextAlign.CENTER),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
        padding=SPACING_XL,
    )


def ExpandableSection(
    page: ft.Page,
    title: str,
    icon: str,
    content: ft.Control,
    palette: dict,
    expanded: bool = True,
) -> ft.Container:
    """Sezione a scomparsa (accordion) usata nel pannello di dettaglio."""
    chevron = ft.Icon(
        ft.Icons.EXPAND_MORE,
        size=20,
        color=palette["text_faint"],
        rotate=ft.Rotate(0 if expanded else 3.14159),
        animate_rotation=ft.Animation(180, ft.AnimationCurve.EASE_OUT),
    )
    body = ft.Container(
        content=content,
        padding=ft.Padding.only(top=12),
        visible=expanded,
        animate_opacity=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
        opacity=1 if expanded else 0,
    )

    def toggle(e: ft.ControlEvent) -> None:
        body.visible = not body.visible
        body.opacity = 1 if body.visible else 0
        chevron.rotate = ft.Rotate(0 if body.visible else 3.14159)
        page.update()

    header = ft.Container(
        content=ft.Row(
            [
                ft.Icon(icon, size=18, color=palette["primary"]),
                ft.Text(title, size=15, weight=ft.FontWeight.W_700, color=palette["text"], expand=True),
                chevron,
            ]
        ),
        on_click=toggle,
        ink=True,
        border_radius=RADIUS_SM,
        padding=ft.Padding.symmetric(vertical=6, horizontal=6),
    )

    return ft.Container(
        content=ft.Column([header, body], spacing=0),
        bgcolor=palette["surface"],
        border=ft.Border.all(1, palette["border"]),
        border_radius=RADIUS_MD,
        padding=16,
        margin=ft.Margin.only(bottom=12),
    )


def PackageCard(confezione: Confezione, palette: dict, page: ft.Page) -> ft.Container:
    tiles = [
        InfoTile(ft.Icons.NUMBERS, "AIC", confezione.aic, palette, page, copyable=True),
        InfoTile(ft.Icons.DESCRIPTION, "Descrizione", confezione.descrizione, palette),
        InfoTile(
            ft.Icons.EURO,
            "Classe",
            f"{confezione.classe_rimborsabilita} - {confezione.descrizione_rimborsabilita}",
            palette,
        ),
        InfoTile(ft.Icons.INFO_OUTLINE, "Stato", confezione.stato_amministrativo, palette),
        InfoTile(
            ft.Icons.RECEIPT_LONG,
            "Prescrizione",
            ", ".join(confezione.prescrizioni) or "-",
            palette,
            page,
            copyable=bool(confezione.prescrizioni),
        ),
    ]
    badges = [Badge(p, *classify_prescrizione(p, palette)) for p in confezione.prescrizioni]
    if confezione.in_carenza:
        badges.append(Badge("Farmaco carente", palette["danger_soft"], palette["danger"], ft.Icons.WARNING_ROUNDED))

    content: list[ft.Control] = []
    if badges:
        content.append(ft.Row(badges, spacing=6, wrap=True))
    content.extend(tiles)

    return ft.Container(
        content=ft.Column(content, spacing=8),
        bgcolor=palette["surface_alt"],
        border=ft.Border.all(1, palette["border"]),
        border_radius=RADIUS_MD,
        padding=14,
        margin=ft.Margin.only(bottom=10),
    )


def ShortageCard(confezione: Confezione, palette: dict) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.REPORT_PROBLEM_ROUNDED, color=palette["danger"], size=20),
                        ft.Text("Farmaco carente", color=palette["danger"], weight=ft.FontWeight.BOLD, size=15),
                    ]
                ),
                InfoTile(ft.Icons.CALENDAR_TODAY, "Inizio carenza", confezione.carenza_inizio, palette),
                InfoTile(ft.Icons.EVENT_AVAILABLE, "Fine prevista", confezione.carenza_fine_presunta, palette),
                InfoTile(ft.Icons.INFO_OUTLINE, "Motivazione", confezione.carenza_motivazione, palette),
            ],
            spacing=8,
        ),
        bgcolor=palette["danger_soft"],
        border=ft.Border.all(1, ft.Colors.with_opacity(0.3, palette["danger"])),
        border_radius=RADIUS_MD,
        padding=14,
        margin=ft.Margin.only(bottom=12),
    )


def WarningsCard(warnings: list[tuple[str, str]], palette: dict) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.SHIELD_MOON_OUTLINED, color=palette["warning"], size=18),
                        ft.Text("Avvertenze", weight=ft.FontWeight.BOLD, size=15, color=palette["warning"]),
                    ]
                ),
                ft.Row(
                    [Badge(text, palette["surface"], palette["warning"], icon) for text, icon in warnings],
                    spacing=8,
                    wrap=True,
                ),
            ],
            spacing=10,
        ),
        bgcolor=palette["warning_soft"],
        border=ft.Border.all(1, ft.Colors.with_opacity(0.3, palette["warning"])),
        border_radius=RADIUS_MD,
        padding=14,
        margin=ft.Margin.only(bottom=12),
    )


def DownloadPanel(
    result: RisultatoFarmaco,
    palette: dict,
    on_download: Callable[[str, ft.Control], None],
    last_paths: dict[str, str],
) -> ft.Container:
    fi_btn = ft.Button(
        content=ft.Row([ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, color="white"), ft.Text("Foglietto Illustrativo", color="white")], tight=True),
        style=ft.ButtonStyle(bgcolor=palette["primary"], shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
        expand=True,
    )
    rcp_btn = ft.Button(
        content=ft.Row([ft.Icon(ft.Icons.SUMMARIZE_OUTLINED, color="white"), ft.Text("Riassunto Caratteristiche", color="white")], tight=True),
        style=ft.ButtonStyle(bgcolor=palette["success"], shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
        expand=True,
    )
    fi_btn.on_click = lambda e: on_download("FI", fi_btn)
    rcp_btn.on_click = lambda e: on_download("RCP", rcp_btn)

    quick_actions: list[ft.Control] = []
    for doc_type, label in (("FI", "FI"), ("RCP", "RCP")):
        path = last_paths.get(doc_type)
        if path:
            quick_actions.append(
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CHECK_CIRCLE, size=14, color=palette["success"]),
                        ft.Text(f"{label} salvato", size=12, color=palette["text_muted"]),
                        ft.TextButton("Apri file", on_click=lambda e, p=path: open_path(p)),
                        ft.TextButton(
                            "Apri cartella", on_click=lambda e, p=path: open_path(os.path.dirname(p))
                        ),
                    ],
                    spacing=2,
                )
            )

    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Download", size=13, weight=ft.FontWeight.W_700, color=palette["text_muted"]),
                ft.Row([fi_btn, rcp_btn], spacing=10),
                *quick_actions,
            ],
            spacing=10,
        ),
        bgcolor=palette["surface"],
        border=ft.Border.all(1, palette["border"]),
        border_radius=RADIUS_MD,
        padding=16,
        margin=ft.Margin.only(bottom=12),
    )


def ResultCard(
    result: RisultatoFarmaco,
    query: str,
    palette: dict,
    is_favorite: bool,
    on_click: Callable[[], None],
    on_toggle_favorite: Callable[[], None],
) -> ft.Container:
    principi = ", ".join(result.principi_attivi[:3])
    if len(result.principi_attivi) > 3:
        principi += "…"

    badges: list[ft.Control] = []
    prescrizioni_uniche = {p for c in result.confezioni for p in c.prescrizioni}
    for p in list(prescrizioni_uniche)[:2]:
        badges.append(Badge(p, *classify_prescrizione(p, palette)))
    if any(c.in_carenza for c in result.confezioni):
        badges.append(Badge("Carente", palette["danger_soft"], palette["danger"], ft.Icons.WARNING_ROUNDED))
    if result.dopante:
        badges.append(Badge("Dopante", palette["purple_soft"], palette["purple"]))

    fav_button = ft.IconButton(
        icon=ft.Icons.STAR if is_favorite else ft.Icons.STAR_BORDER,
        icon_color=palette["warning"] if is_favorite else palette["text_faint"],
        icon_size=19,
        tooltip="Rimuovi dai preferiti" if is_favorite else "Aggiungi ai preferiti",
        on_click=lambda e: on_toggle_favorite(),
    )

    card = ft.Container(
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Icon(ft.Icons.MEDICATION_ROUNDED, color=palette["primary"], size=20),
                    width=40,
                    height=40,
                    bgcolor=palette["primary_soft"],
                    border_radius=RADIUS_SM,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column(
                    [
                        highlighted_text(result.denominazione, query, 15, ft.FontWeight.W_700, palette["text"]),
                        ft.Text(result.descrizione_forma_dosaggio, size=12, color=palette["text_muted"]),
                        ft.Text(principi or "-", size=12, color=palette["text_faint"], italic=True),
                        ft.Row(badges, spacing=6, wrap=True) if badges else ft.Container(height=0),
                    ],
                    spacing=3,
                    expand=True,
                ),
                fav_button,
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
            spacing=12,
        ),
        bgcolor=palette["surface"],
        border=ft.Border.all(1, palette["border"]),
        border_radius=RADIUS_MD,
        padding=14,
        margin=ft.Margin.only(bottom=10),
        ink=True,
        on_click=lambda e: on_click(),
        animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
        shadow=soft_shadow(palette),
        scale=1,
        animate_scale=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
    )

    def on_hover(e: ft.ControlEvent) -> None:
        card.scale = 1.01 if e.data == "true" else 1
        card.shadow = card_shadow(palette) if e.data == "true" else soft_shadow(palette)
        card.update()

    card.on_hover = on_hover
    return card


def SearchHero(palette: dict, subtitle: str) -> ft.Column:
    return ft.Column(
        [
            ft.Container(
                content=ft.Icon(ft.Icons.MEDICAL_SERVICES_ROUNDED, color=palette["primary"], size=34),
                width=72,
                height=72,
                bgcolor=palette["primary_soft"],
                border_radius=999,
                alignment=ft.Alignment.CENTER,
            ),
            ft.Text("Ricerca Farmaci AIFA", size=22, weight=ft.FontWeight.W_800, color=palette["text"]),
            ft.Text(subtitle, size=13, color=palette["text_muted"], text_align=ft.TextAlign.CENTER),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=8,
    )


# --------------------------------------------------------------------------- #
# Applicazione UI
# --------------------------------------------------------------------------- #

class MedicineApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.config = APIConfig()
        self.service = AIFAService(self.config)
        self.store = LocalStore(page)

        # -- stato applicativo -- #
        self.dark_mode: bool = False
        self.palette: dict = LIGHT_PALETTE
        self._search_debounce_task: Optional[asyncio.Task] = None
        self._last_results: list[RisultatoFarmaco] = []
        self._filtered_results: list[RisultatoFarmaco] = []
        self._selected: Optional[RisultatoFarmaco] = None
        self._active_tab: str = "ricerca"  # ricerca | preferiti | cronologia
        self._favorites: list[RisultatoFarmaco] = []
        self._history: list[RisultatoFarmaco] = []
        self._search_cache: dict[str, list[RisultatoFarmaco]] = {}
        self._last_downloaded: dict[str, str] = {}
        self._filters = {
            "solo_carenti": False,
            "solo_sop": False,
            "solo_rr": False,
            "solo_osp": False,
            "solo_dopanti": False,
        }
        self._compare_selection: list[RisultatoFarmaco] = []

        # -- controlli riutilizzati fra i vari render -- #
        self.search_field = self._build_search_field()
        self.loading_indicator = ft.ProgressRing(width=18, height=18, stroke_width=2, visible=False)
        self.search_results_area = ft.Column(
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        self.favorite_results_area = ft.Column(
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        self.history_results_area = ft.Column(
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        self.detail_area = ft.Column(
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        self.search_view = ft.Container()
        self.favorite_view = ft.Container()
        self.history_view = ft.Container()
        self.left_column = ft.Column(expand=True, spacing=SPACING_MD)
        self.file_picker = ft.FilePicker()
        self.theme_switch = ft.IconButton(
            icon=ft.Icons.DARK_MODE_OUTLINED,
            tooltip="Attiva tema scuro",
            on_click=self._on_theme_toggle,
        )
        self.filter_chips_row = ft.Row(spacing=8, wrap=True)
        self.tabs = None
        self.compare_banner = ft.Container(visible=False)

        self._setup_page()
        self.page.on_disconnect = self._on_disconnect

        self.page.run_task(self._bootstrap)

    # -- Setup ------------------------------------------------------------- #

    def _setup_page(self) -> None:
        self.page.title = "Ricerca Farmaci AIFA"
        self.page.padding = 0
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.bgcolor = self.palette["bg"]
        self.page.window.width = 1200
        self.page.window.height = 800
        self.page.window.min_width = 720
        self.page.window.min_height = 560
        self.page.fonts = {
            "Roboto": "https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;600;700;800&display=swap"
        }
        self.page.window.icon = "assets/icon.ico"

    async def _bootstrap(self) -> None:
        """Carica preferiti/cronologia/tema salvati, poi disegna l'interfaccia."""
        self._favorites = await self.store.load_favorites()
        self._history = await self.store.load_history()
        self.dark_mode = await self.store.load_dark_mode()
        self.palette = DARK_PALETTE if self.dark_mode else LIGHT_PALETTE
        self._apply_theme_chrome()
        self._render_all()

    def _apply_theme_chrome(self) -> None:
        self.page.theme_mode = ft.ThemeMode.DARK if self.dark_mode else ft.ThemeMode.LIGHT
        self.page.bgcolor = self.palette["bg"]
        self.theme_switch.icon = ft.Icons.LIGHT_MODE_OUTLINED if self.dark_mode else ft.Icons.DARK_MODE_OUTLINED
        self.theme_switch.tooltip = "Attiva tema chiaro" if self.dark_mode else "Attiva tema scuro"

    def _build_search_field(self) -> ft.TextField:
        return ft.TextField(
            hint_text="Cerca per nome farmaco o codice AIC…",
            on_change=self._on_search_changed,
            on_submit=self._on_search_submitted,
            autofocus=True,
            prefix_icon=ft.Icons.SEARCH_ROUNDED,
            border_radius=RADIUS_MD,
            filled=True,
            expand=True,
            text_size=16,
            height=54,
            content_padding=ft.Padding.symmetric(horizontal=16, vertical=14),
        )

    def _build_tabs(self):

        self.search_view.content = ft.Column(
            [
                self.search_field,
                self.filter_chips_row,
                self.compare_banner,
                self.search_results_area,
            ],
            expand=True,
            spacing=SPACING_MD,
        )

        self.favorite_view.content = ft.Column(
            [
                self.favorite_results_area,
            ],
            expand=True,
        )

        self.history_view.content = ft.Column(
            [
                self.history_results_area,
            ],
            expand=True,
        )

        return ft.Tabs(
            length=3,
            expand=True,
            selected_index=0,
            on_change=self._on_tab_change,
            content=ft.Column(
                expand=True,
                controls=[
                    ft.TabBar(
                        tab_alignment=ft.TabAlignment.CENTER,
                        tabs=[
                            ft.Tab(
                                label="Ricerca",
                                icon=ft.Icons.SEARCH,
                            ),
                            ft.Tab(
                                label="Preferiti",
                                icon=ft.Icons.STAR,
                            ),
                            ft.Tab(
                                label="Cronologia",
                                icon=ft.Icons.HISTORY,
                            ),
                        ],
                    ),

                    ft.TabBarView(
                        expand=True,
                        controls=[
                            self.search_view,
                            self.favorite_view,
                            self.history_view,
                        ],
                    ),
                ],
            ),
        )

    # -- Layout globale ------------------------------------------------------ #

    def _render_all(self) -> None:
        p = self.palette
        self.search_field.bgcolor = p["surface"]
        self.search_field.border_color = p["border"]
        self.search_field.color = p["text"]

        header = ft.Container(
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.MEDICATION_ROUNDED, color=p["primary"], size=26),
                            ft.Text("Ricerca Farmaci AIFA", size=18, weight=ft.FontWeight.W_800, color=p["text"]),
                        ],
                        spacing=10,
                    ),
                    ft.Row([self.loading_indicator, self.theme_switch], spacing=6),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=ft.Padding.symmetric(horizontal=SPACING_LG, vertical=SPACING_MD),
            bgcolor=p["surface"],
            border=ft.Border(bottom=ft.BorderSide(1, p["border"])),
        )

        self._render_filters()
        self.tabs = self._build_tabs()

        left_panel = ft.Container(
            content=ft.Column(
                [
                    self.tabs,
                ],
                spacing=SPACING_MD,
                expand=True,
            ),
            padding=SPACING_LG,
            width=440,
            bgcolor=p["bg"],
        )

        right_panel = ft.Container(
            content=self.detail_area,
            padding=SPACING_LG,
            expand=True,
            bgcolor=p["surface_alt"],
        )

        body = ft.Row(
            [left_panel, ft.VerticalDivider(width=1, color=p["border"]), right_panel],
            expand=True,
            spacing=0,
        )

        self.page.controls.clear()
        self.page.add(ft.Column([header, ft.Container(content=body, expand=True)], expand=True, spacing=0))
        self._render_results_area()
        self._render_detail_area()
        self.page.update()

    def _on_theme_toggle(self, e: ft.ControlEvent) -> None:
        self.dark_mode = not self.dark_mode
        self.palette = DARK_PALETTE if self.dark_mode else LIGHT_PALETTE
        self._apply_theme_chrome()
        self.page.run_task(self.store.save_dark_mode, self.dark_mode)
        self._render_all()

    def _on_tab_change(self, e: ft.ControlEvent) -> None:
        self._active_tab = [
            "ricerca",
            "preferiti",
            "cronologia",
        ][self.tabs.selected_index]

        self._render_results_area()
        self.page.update()

    # -- Filtri --------------------------------------------------------------- #

    def _render_filters(self) -> None:
        p = self.palette

        def chip(label: str, key: str, icon: str) -> ft.Container:
            active = self._filters[key]
            c = ft.Container(
                content=ft.Row(
                    [ft.Icon(icon, size=13, color=p["surface"] if active else p["text_muted"]),
                     ft.Text(label, size=12, weight=ft.FontWeight.W_600, color=p["surface"] if active else p["text_muted"])],
                    spacing=4,
                    tight=True,
                ),
                bgcolor=p["primary"] if active else p["surface"],
                border=ft.Border.all(1, p["primary"] if active else p["border"]),
                border_radius=999,
                padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                on_click=lambda e, k=key: self._toggle_filter(k),
                ink=True,
            )
            return c

        self.filter_chips_row.controls = [
            chip("Solo carenti", "solo_carenti", ft.Icons.WARNING_ROUNDED),
            chip("Solo SOP", "solo_sop", ft.Icons.LOCAL_PHARMACY_OUTLINED),
            chip("Solo RR", "solo_rr", ft.Icons.RECEIPT_LONG),
            chip("Solo ospedalieri", "solo_osp", ft.Icons.LOCAL_HOSPITAL_OUTLINED),
            chip("Solo dopanti", "solo_dopanti", ft.Icons.SPORTS_OUTLINED),
        ]

    def _toggle_filter(self, key: str) -> None:
        self._filters[key] = not self._filters[key]
        self._render_filters()
        self._render_results_area()
        self.page.update()

    def _apply_filters(self, results: list[RisultatoFarmaco]) -> list[RisultatoFarmaco]:
        f = self._filters
        if not any(f.values()):
            return results

        def keep(r: RisultatoFarmaco) -> bool:
            prescr = {p.upper() for c in r.confezioni for p in c.prescrizioni}
            if f["solo_carenti"] and not any(c.in_carenza for c in r.confezioni):
                return False
            if f["solo_sop"] and not any("SOP" in p for p in prescr):
                return False
            if f["solo_rr"] and not any("RR" in p for p in prescr):
                return False
            if f["solo_osp"] and not any("OSP" in p for p in prescr):
                return False
            if f["solo_dopanti"] and not r.dopante:
                return False
            return True

        return [r for r in results if keep(r)]

    # -- Ricerca (con debounce, cache offline, ricerca per AIC) --------------- #

    def _on_search_submitted(self, e: ft.ControlEvent) -> None:
        self.page.run_task(self._run_search, self.search_field.value or "")

    def _on_search_changed(self, e: ft.ControlEvent) -> None:
        # Annulla la ricerca pianificata precedente: evita una chiamata API
        # per ogni singolo carattere digitato.
        if self._search_debounce_task and not self._search_debounce_task.done():
            self._search_debounce_task.cancel()
        self._search_debounce_task = self.page.run_task(self._debounced_search, self.search_field.value or "")

    async def _debounced_search(self, query: str) -> None:
        try:
            await asyncio.sleep(self.config.search_debounce_ms / 1000)
        except asyncio.CancelledError:
            return
        await self._run_search(query)

    async def _run_search(self, query: str) -> None:
        query = query.strip()
        if len(query) < self.config.min_query_length:
            self._last_results = []
            self._render_results_area()
            self.page.update()
            return

        self.loading_indicator.visible = True
        self.page.update()

        cache_key = query.lower()
        try:
            self._last_results = await self.service.search_medicines(query)
            self._search_cache[cache_key] = self._last_results
        except APIError as exc:
            if cache_key in self._search_cache:
                self._last_results = self._search_cache[cache_key]
                self._show_info(f"{exc} Mostro gli ultimi risultati salvati per questa ricerca (offline).")
            else:
                self._last_results = []
                self._show_error(str(exc))
        finally:
            self.loading_indicator.visible = False
            self._render_results_area()
            self.page.update()

    # -- Rendering lista risultati / preferiti / cronologia -------------------- #

    def _render_results_area(self) -> None:
        p = self.palette
        if self._active_tab == "ricerca":
            area = self.search_results_area

        elif self._active_tab == "preferiti":
            area = self.favorite_results_area

        else:
            area = self.history_results_area

        area.controls.clear()

        if self._active_tab == "preferiti":
            self._render_list(
                self._favorites,
                empty_text="Nessun farmaco tra i preferiti.",
                show_query=False,
                target=self.favorite_results_area,
            )
            return
        if self._active_tab == "cronologia":
            self._render_list(
                self._history,
                empty_text="Nessuna ricerca recente.",
                show_query=False,
                target=self.history_results_area,
            )
            return

        query = (self.search_field.value or "").strip()
        if len(query) < self.config.min_query_length:
            area.controls.append(
                ft.Container(
                    content=SearchHero(
                        p,
                        f"Digita almeno {self.config.min_query_length} caratteri: nome del farmaco o codice AIC.",
                    ),
                    padding=SPACING_XL,
                    alignment=ft.Alignment.CENTER,
                    expand=True,
                )
            )
            return

        self._filtered_results = self._apply_filters(self._last_results)
        self._render_list(
            self._filtered_results,
            empty_text="Nessun risultato trovato.",
            show_query=True,
            query=query,
            target=self.search_results_area,
        )

    def _render_list(
        self,
        items,
        empty_text,
        show_query,
        query="",
        target=None,
    ):
        p = self.palette
        if not items:
            target.controls.append(
                EmptyState(ft.Icons.SEARCH_OFF_ROUNDED, empty_text, "Prova con un altro termine di ricerca.", p)
            )
            return

        for result in items:
            is_fav = self._is_favorite(result)
            target.controls.append(
                ResultCard(
                    result,
                    query if show_query else "",
                    p,
                    is_fav,
                    on_click=lambda r=result: self._show_details(r),
                    on_toggle_favorite=lambda r=result: self._toggle_favorite(r),
                )
            )

    # -- Preferiti -------------------------------------------------------------- #

    def _is_favorite(self, result: RisultatoFarmaco) -> bool:
        return any(f.aic6 == result.aic6 for f in self._favorites)

    def _toggle_favorite(self, result: RisultatoFarmaco) -> None:
        if self._is_favorite(result):
            self._favorites = [f for f in self._favorites if f.aic6 != result.aic6]
        else:
            self._favorites.insert(0, result)
        self.page.run_task(self.store.save_favorites, self._favorites)
        self._render_results_area()
        if self._selected and self._selected.aic6 == result.aic6:
            self._render_detail_area()
        self.page.update()

    def _add_to_history(self, result: RisultatoFarmaco) -> None:
        self._history = [h for h in self._history if h.aic6 != result.aic6]
        self._history.insert(0, result)
        self._history = self._history[:50]
        self.page.run_task(self.store.save_history, self._history)

    # -- Dettaglio farmaco ------------------------------------------------------ #

    def _show_details(self, result: RisultatoFarmaco) -> None:
        self._selected = result
        self._add_to_history(result)
        self._last_downloaded = {}
        self._render_detail_area()
        self.page.update()

    def _render_detail_area(self) -> None:
        p = self.palette
        self.detail_area.controls.clear()
        if self._selected is None:
            self.detail_area.controls.append(
                EmptyState(
                    ft.Icons.MEDICATION_LIQUID_OUTLINED,
                    "Nessun farmaco selezionato",
                    "Cerca un farmaco a sinistra e seleziona una card per vederne i dettagli.",
                    p,
                )
            )
            return
        self.detail_area.controls.append(self._build_detail_card(self._selected))

    def _build_detail_card(self, result: RisultatoFarmaco) -> ft.Container:
        p = self.palette
        is_fav = self._is_favorite(result)

        header = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(result.denominazione, size=24, weight=ft.FontWeight.W_800, color=p["text"]),
                        ft.Text(result.descrizione_forma_dosaggio, size=14, color=p["text_muted"]),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.IconButton(
                    icon=ft.Icons.STAR if is_fav else ft.Icons.STAR_BORDER,
                    icon_color=p["warning"] if is_fav else p["text_faint"],
                    tooltip="Rimuovi dai preferiti" if is_fav else "Aggiungi ai preferiti",
                    on_click=lambda e: self._toggle_favorite(result),
                ),
                ft.IconButton(
                    icon=ft.Icons.IOS_SHARE,
                    tooltip="Esporta informazioni",
                    on_click=lambda e: self.page.run_task(self._export_info, result),
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        general_content = ft.Column(
            [
                InfoTile(ft.Icons.MEDICATION_LIQUID, "Forma farmaceutica", result.forma_farmaceutica, p),
                InfoTile(
                    ft.Icons.SCIENCE_OUTLINED,
                    "Principi attivi",
                    ", ".join(result.principi_attivi) or "-",
                    p,
                    self.page,
                    copyable=bool(result.principi_attivi),
                ),
                InfoTile(
                    ft.Icons.HEALING_OUTLINED,
                    "Via somministrazione",
                    ", ".join(result.vie_somministrazione) or "-",
                    p,
                ),
                InfoTile(
                    ft.Icons.CATEGORY_OUTLINED,
                    "Codice ATC",
                    ", ".join(result.codice_atc) or "-",
                    p,
                    self.page,
                    copyable=bool(result.codice_atc),
                ),
            ],
            spacing=8,
        )

        sections: list[ft.Control] = [
            header,
            ft.Container(height=8),
            ExpandableSection(self.page, "Informazioni generali", ft.Icons.INFO_OUTLINE, general_content, p, expanded=True),
        ]

        packages_content = ft.Column(
            [PackageCard(c, p, self.page) for c in result.confezioni] or [ft.Text("Nessuna confezione disponibile.", color=p["text_muted"])],
            spacing=0,
        )
        sections.append(
            ExpandableSection(self.page, "Confezioni", ft.Icons.INVENTORY_2_OUTLINED, packages_content, p, expanded=True)
        )

        for c in result.confezioni:
            if c.in_carenza:
                sections.append(ShortageCard(c, p))

        warnings = self._collect_warnings(result)
        if warnings:
            sections.append(WarningsCard(warnings, p))

        sections.append(
            DownloadPanel(
                result,
                p,
                on_download=lambda doc_type, btn: self.page.run_task(self._download, result, doc_type, btn),
                last_paths=self._last_downloaded,
            )
        )

        return ft.Container(
            content=ft.Column(sections, spacing=4),
            padding=SPACING_LG,
            bgcolor=p["surface"],
            border_radius=RADIUS_LG,
            border=ft.Border.all(1, p["border"]),
            shadow=card_shadow(p),
        )

    @staticmethod
    def _collect_warnings(result: RisultatoFarmaco) -> list[tuple[str, str]]:
        warnings = []
        if result.dopante:
            warnings.append(("Sostanza dopante", ft.Icons.SPORTS_OUTLINED))
        if result.influenza_guida:
            warnings.append(("Influenza la guida", ft.Icons.DIRECTIONS_CAR_FILLED_OUTLINED))
        if result.interazione_alcol:
            warnings.append(("Interazione con alcol", ft.Icons.LOCAL_BAR_OUTLINED))
        if result.interazione_potassio:
            warnings.append(("Interazione con potassio", ft.Icons.SCIENCE_OUTLINED))
        return warnings

    # -- Download documenti (invariato nella logica, + apri file/cartella) ---- #

    async def _download(self, result: RisultatoFarmaco, doc_type: str, button: ft.Control) -> None:
        button.disabled = True
        self.page.update()
        suggested_name = "foglietto_illustrativo.pdf" if doc_type == "FI" else "riassunto_caratteristiche.pdf"
        try:
            file_name = f"{result.aic6}_{suggested_name}"
            pdf_bytes = await self.service.download_document(result.codice_sis, result.aic6, doc_type)
            saved_path = await self.file_picker.save_file(
                dialog_title="Salva documento",
                file_name=file_name,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["pdf"],
                src_bytes=pdf_bytes,
            )
            if saved_path:
                self._last_downloaded[doc_type] = saved_path
            self._show_success(f"Documento '{file_name}' scaricato correttamente.")
            self._render_detail_area()
        except APIError as exc:
            self._show_error(str(exc))
        except Exception:  # noqa: BLE001 - protezione UI da errori imprevisti del file picker
            logger.exception("Errore imprevisto durante il salvataggio del documento")
            self._show_error("Errore imprevisto durante il salvataggio del documento.")
        finally:
            button.disabled = False
            self.page.update()

    async def _download_both(self, result: RisultatoFarmaco) -> None:
        await self._download(result, "FI", ft.Container())
        await self._download(result, "RCP", ft.Container())

    # -- Esportazione informazioni (nuova funzionalità, nessuna chiamata API) - #

    async def _export_info(self, result: RisultatoFarmaco) -> None:
        lines = [
            f"{result.denominazione} - {result.descrizione_forma_dosaggio}",
            f"Forma farmaceutica: {result.forma_farmaceutica}",
            f"Principi attivi: {', '.join(result.principi_attivi) or '-'}",
            f"Via di somministrazione: {', '.join(result.vie_somministrazione) or '-'}",
            f"Codice ATC: {', '.join(result.codice_atc) or '-'}",
            "",
            "Confezioni:",
        ]
        for c in result.confezioni:
            lines.append(f" - AIC {c.aic}: {c.descrizione} ({c.stato_amministrativo})")
            if c.in_carenza:
                lines.append(f"   ⚠ Carente dal {c.carenza_inizio}, fine prevista {c.carenza_fine_presunta}")
        lines.append("")
        lines.append(f"Esportato il {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        content = "\n".join(lines).encode("utf-8")

        try:
            await self.file_picker.save_file(
                dialog_title="Esporta informazioni farmaco",
                file_name=f"{result.aic6}_info.txt",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["txt"],
                src_bytes=content,
            )
            self._show_success("Informazioni esportate correttamente.")
        except Exception:  # noqa: BLE001
            logger.exception("Errore durante l'esportazione")
            self._show_error("Errore imprevisto durante l'esportazione.")

    # -- Feedback utente ------------------------------------------------------ #

    def _show_error(self, message: str) -> None:
        self.page.show_dialog(
            ft.SnackBar(content=ft.Text(message, color="white"), bgcolor=self.palette["danger"])
        )

    def _show_success(self, message: str) -> None:
        self.page.show_dialog(
            ft.SnackBar(content=ft.Text(message, color="white"), bgcolor=self.palette["success"])
        )

    def _show_info(self, message: str) -> None:
        self.page.show_dialog(
            ft.SnackBar(content=ft.Text(message, color="white"), bgcolor=self.palette["primary"])
        )

    # -- Ciclo di vita --------------------------------------------------------- #

    async def _on_disconnect(self, e: ft.ControlEvent) -> None:
        await self.service.close()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main(page: ft.Page) -> None:
    MedicineApp(page)


if __name__ == "__main__":
    ft.run(main)