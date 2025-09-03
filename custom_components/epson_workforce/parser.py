"""Epson status page parser."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag


# ----------------------------
# Lightweight HTML page parser
# ----------------------------
def _classes(node: Tag) -> list[str]:
    return list(node.get("class") or [])


def _height_from_style(node: Tag) -> int | None:
    style_val = node.get("style")
    if isinstance(style_val, str):
        style = style_val.lower()
    elif isinstance(style_val, list):
        style = " ".join(style_val).lower()
    else:
        return None

    m = re.search(r"height\s*:\s*(\d+)", style)
    return int(m.group(1)) if m else None


def _clean_key(t: str) -> str:
    t = t.replace("\xa0:", "").replace(" :", ":").strip()
    if t.endswith(":"):
        t = t[:-1].strip()
    return t


class EpsonHTMLParser:
    """Minimal, robust parser for Epson status pages across multiple models/skins."""

    def __init__(self, html_text: str, source: str = ""):
        self.source = source
        self.soup: BeautifulSoup = BeautifulSoup(html_text, "html.parser")

    def parse(self) -> dict[str, Any]:
        model = self._parse_model()
        statuses = self._parse_statuses()
        inks, maintenance = self._parse_inks_and_maintenance()
        network = self._parse_table_by_container_id("info-network")
        wifi_direct = self._parse_table_by_container_id("info-wfd")
        mac = network.get("MAC Address") or self._extract_mac_from_text()

        out: dict[str, Any] = {
            "source": self.source or model,
            "model": model,
            **statuses,  # e.g., {"printer_status": "...", "scanner_status": "..."}
            "inks": inks,
            "maintenance_box": maintenance,
            "network": network,
        }
        if wifi_direct:
            out["wifi_direct"] = wifi_direct
        if mac:
            out["mac_address"] = mac
        return out

    # --- model / status ---
    def _parse_model(self) -> str | None:
        t = self.soup.find("title")
        if isinstance(t, Tag) and t.text.strip():
            return f"Epson {t.text.strip()}"
        head_span = self.soup.find("span", class_="header")
        if isinstance(head_span, Tag) and head_span.get_text(strip=True):
            return f"Epson {head_span.get_text(strip=True)}"
        return None

    def _parse_statuses(self) -> dict[str, str | None]:
        out: dict[str, str | None] = {}

        fs = self.soup.find("fieldset", id="PRT_STATUS")
        if isinstance(fs, Tag):
            txt = fs.get_text(" ", strip=True)
            out["printer_status"] = self._clean_status(txt)

        # Fallback for printer status: .information span
        if not out.get("printer_status"):
            info = self.soup.find("div", class_="information")
            if isinstance(info, Tag):
                span = info.find("span")
                if isinstance(span, Tag):
                    out["printer_status"] = self._clean_status(
                        span.get_text(strip=True)
                    )

        return out

    @staticmethod
    def _clean_status(s: str | None) -> str | None:
        if not s:
            return None
        s = s.strip()
        s = re.sub(
            r"^(?:printer|scanner)\s+status\s*[:\-]?\s*", "", s, flags=re.IGNORECASE
        )
        if len(s) <= 40 and s.endswith("."):
            s = s[:-1]
        return s or None

    # --- inks / maintenance ---
    def _parse_inks_and_maintenance(self) -> tuple[dict[str, int], int | None]:
        inks: dict[str, int] = {}
        maintenance: int | None = None

        for li in self.soup.select("li.tank"):
            # if not isinstance(li, Tag):
            #    continue
            # label
            label = None
            for d in li.find_all("div"):
                if not isinstance(d, Tag):
                    continue
                if any(c.lower() == "clrname" for c in _classes(d)):
                    txt = d.get_text(strip=True)
                    if txt:
                        label = txt.upper()
                        break

            # maintenance row?
            is_maintenance = any(
                any(c.lower() == "mbicn" for c in _classes(d))
                for d in li.find_all("div")
                if isinstance(d, Tag)
            )

            # bar height
            height_px = self._li_bar_height(li)
            if height_px is None:
                continue
            pct = max(0, min(100, height_px * 2))

            if is_maintenance:
                maintenance = pct
            elif label:
                inks[label] = pct

        return inks, maintenance

    def _li_bar_height(self, li: Tag) -> int | None:
        # find inner div.tank (the visual container)
        bar_div = None
        for d in li.find_all("div"):
            if not isinstance(d, Tag):
                continue
            if any(c.lower() == "tank" for c in _classes(d)):
                bar_div = d
                break
        if bar_div is None:
            return None
        # prefer <img class="color"> then any <img>
        img = bar_div.find("img", class_="color") or bar_div.find("img")
        if isinstance(img, Tag):
            h = img.get("height")
            if isinstance(h, str) and h.isdigit():
                return int(h)
            h2 = _height_from_style(img)
            if h2 is not None:
                return h2
        # fallback: any descendant with inline height
        for desc in bar_div.descendants:
            if isinstance(desc, Tag):
                h3 = _height_from_style(desc)
                if h3 is not None:
                    return h3
        return None

    # --- key/value tables ---
    def _parse_table_by_container_id(self, container_id: str) -> dict[str, str]:
        data: dict[str, str] = {}
        root = self.soup.find(id=container_id)
        if not isinstance(root, Tag):
            return data
        for tr in root.find_all("tr"):
            if not isinstance(tr, Tag):
                continue
            td_key = tr.find(
                "td", class_=lambda c: isinstance(c, str) and "item-key" in c
            )
            td_val = tr.find(
                "td", class_=lambda c: isinstance(c, str) and "item-value" in c
            )
            if isinstance(td_key, Tag) and isinstance(td_val, Tag):
                key = _clean_key(td_key.get_text(" ", strip=True))
                val = td_val.get_text(" ", strip=True)
                if key:
                    data[key] = val
        return data

    # --- misc ---
    def _extract_mac_from_text(self) -> str | None:
        txt = self.soup.get_text(" ", strip=True)
        m = re.search(r"\b([0-9A-F]{2}:){5}[0-9A-F]{2}\b", txt, flags=re.IGNORECASE)
        return m.group(0) if m else None
