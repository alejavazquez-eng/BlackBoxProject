"""Analiza la interfaz web extrayendo estructura, formularios, navegación y acciones."""

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from docgen.models import (
    FormField,
    NavigationItem,
    WebForm,
    WebInterfaceAnalysis,
)


def analyze_web_interface(url: str, timeout: int = 15) -> WebInterfaceAnalysis:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; DocGen/1.0; +https://github.com/docgen)"
        )
    }

    try:
        response = requests.get(url, headers=headers, timeout=timeout, verify=False)
        response.raise_for_status()
    except requests.RequestException as exc:
        return WebInterfaceAnalysis(
            url=url,
            title=None,
            description=f"No se pudo acceder a la URL: {exc}",
            raw_text_summary=str(exc),
        )

    soup = BeautifulSoup(response.text, "lxml")

    return WebInterfaceAnalysis(
        url=url,
        title=_extract_title(soup),
        description=_extract_description(soup),
        navigation=_extract_navigation(soup, url),
        forms=_extract_forms(soup),
        data_tables=_extract_data_tables(soup),
        buttons_and_actions=_extract_buttons(soup),
        api_hints=_extract_api_hints(response.text),
        raw_text_summary=_extract_text_summary(soup),
    )


def _extract_title(soup: BeautifulSoup) -> str | None:
    if soup.title:
        return soup.title.string
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else None


def _extract_description(soup: BeautifulSoup) -> str | None:
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"]
    # Primer párrafo significativo
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) > 40:
            return text[:300]
    return None


def _extract_navigation(soup: BeautifulSoup, base_url: str) -> list[NavigationItem]:
    nav_items: list[NavigationItem] = []

    nav_elements = soup.find_all(["nav", "header"])
    if not nav_elements:
        nav_elements = [soup]

    seen_hrefs: set[str] = set()
    for nav in nav_elements[:3]:
        for link in nav.find_all("a", href=True)[:30]:
            href = link["href"]
            text = link.get_text(strip=True)
            if not text or href in seen_hrefs:
                continue
            seen_hrefs.add(href)
            full_href = urljoin(base_url, href) if not href.startswith("http") else href
            nav_items.append(NavigationItem(text=text, href=full_href))

    return nav_items[:20]


def _extract_forms(soup: BeautifulSoup) -> list[WebForm]:
    forms: list[WebForm] = []

    for form in soup.find_all("form"):
        fields: list[FormField] = []

        for inp in form.find_all(["input", "select", "textarea"]):
            name = inp.get("name") or inp.get("id", "")
            if not name or inp.get("type") in ("hidden", "submit", "button", "reset"):
                continue

            label_text = _find_label(soup, inp)
            field_type = inp.get("type", inp.name or "text")

            options: list[str] = []
            if inp.name == "select":
                options = [o.get_text(strip=True) for o in inp.find_all("option")][:10]

            fields.append(
                FormField(
                    name=name,
                    type=field_type,
                    label=label_text,
                    required=inp.has_attr("required"),
                    options=options,
                )
            )

        forms.append(
            WebForm(
                action=form.get("action"),
                method=(form.get("method") or "GET").upper(),
                fields=fields,
            )
        )

    return forms


def _find_label(soup: BeautifulSoup, inp) -> str | None:
    field_id = inp.get("id")
    if field_id:
        lbl = soup.find("label", attrs={"for": field_id})
        if lbl:
            return lbl.get_text(strip=True)
    parent = inp.parent
    if parent:
        lbl = parent.find("label")
        if lbl:
            return lbl.get_text(strip=True)
    return None


def _extract_data_tables(soup: BeautifulSoup) -> list[dict]:
    tables_info: list[dict] = []

    for table in soup.find_all("table")[:5]:
        headers: list[str] = []
        thead = table.find("thead")
        if thead:
            headers = [th.get_text(strip=True) for th in thead.find_all(["th", "td"])]
        elif table.find("tr"):
            first_row = table.find("tr")
            headers = [th.get_text(strip=True) for th in first_row.find_all("th")]

        rows: list[list[str]] = []
        for tr in table.find_all("tr")[1:4]:
            row = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if row:
                rows.append(row)

        if headers or rows:
            tables_info.append({"headers": headers, "sample_rows": rows})

    return tables_info


def _extract_buttons(soup: BeautifulSoup) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    seen: set[str] = set()

    for btn in soup.find_all(["button", "a"], limit=50):
        text = btn.get_text(strip=True)
        if not text or text in seen:
            continue
        seen.add(text)

        entry = {"text": text, "tag": btn.name}
        if btn.name == "a" and btn.get("href"):
            entry["href"] = btn["href"]
        if btn.get("type"):
            entry["type"] = btn["type"]
        if btn.get("data-action") or btn.get("data-target"):
            entry["data"] = str(btn.attrs)

        actions.append(entry)

    return actions[:25]


def _extract_api_hints(html: str) -> list[str]:
    """Busca patrones que sugieran endpoints de API en el HTML."""
    hints: set[str] = set()

    # URLs tipo API en fetch/axios/XMLHttpRequest
    api_patterns = [
        r'(?:fetch|axios\.[a-z]+|url\s*[:=])\s*[\'"`]([/][^\s\'"`]+)[\'"`]',
        r'(?:action|href)\s*=\s*[\'"]([/]api/[^\s\'"]+)[\'"]',
        r'"(?:endpoint|url|api_url|base_url)"\s*:\s*"([^"]+)"',
    ]

    for pattern in api_patterns:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            path = match.group(1)
            if len(path) < 100 and not path.endswith((".js", ".css", ".png")):
                hints.add(path)

    return sorted(hints)[:20]


def _extract_text_summary(soup: BeautifulSoup) -> str:
    # Elimina scripts, estilos y metadatos
    for tag in soup(["script", "style", "meta", "link", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    # Colapsa espacios múltiples
    text = re.sub(r"\s+", " ", text)
    return text[:3000]
