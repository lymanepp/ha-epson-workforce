"""Epson status page parser."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag

MAX_STATUS_LENGTH = 40

# --- value-pattern fallbacks (language-agnostic) ---
RE_EPSON_DEVNAME = re.compile(r"\bEPSON[0-9A-F]{6}\b", re.IGNORECASE)
RE_IPV4 = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
)
RE_MAC = re.compile(r"\b([0-9A-F]{2}:){5}[0-9A-F]{2}\b", re.IGNORECASE)


# ----------------------------
# Lightweight HTML page parser
# ----------------------------
def _classes(node: Tag) -> list[str]:
    return list(node.get("class") or [])


def _height_from_style(node: Tag) -> int | None:
    """Extract an integer height out of inline style, e.g. 'height: 34px'."""
    style_val = node.get("style")
    if isinstance(style_val, str):
        style = style_val.lower()
    elif isinstance(style_val, list):
        style = " ".join(style_val).lower()
    else:
        return None
    m = re.search(r"height\s*:\s*(\d+)", style)
    return int(m.group(1)) if m else None


def _percent_from_linear_gradient(style_val: str | list[str] | None) -> int | None:
    """Parse 'linear-gradient(...)' style and return fill percent (0-100).
    Example: linear-gradient(... 0%, 34%, 34%, 100%) -> 34
    """
    if not style_val:
        return None
    style = " ".join(style_val) if isinstance(style_val, list) else str(style_val)
    if "linear-gradient" not in style:
        return None
    # Capture percent stops in order (allow decimals), use the 2nd stop.
    nums = [float(n) for n in re.findall(r"(\d{1,3}(?:\.\d+)?)\s*%", style)]
    if len(nums) < 2:  # noqa: PLR2004
        return None
    val = int(round(nums[1]))
    return max(0, min(100, val))


def _clean_key(t: str) -> str:
    t = t.replace("\xa0:", "").replace(" :", ":").strip()
    if t.endswith(":"):
        t = t[:-1].strip()
    return t


def _clean_value(t: str) -> str:
    return t.replace("\xa0", " ").strip()


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

        # Base payload
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

        # Name: prefer table fields, then pattern fallback, then model.
        name = (
            network.get("Device Name")
            or network.get("Printer Name")
            or self._extract_device_name()
            or model
        )
        if name:
            out["name"] = name

        # MAC/IP: prefer table fields, fall back to text search
        mac = (
            network.get("MAC Address")
            or network.get("MAC address")
            or self._extract_mac_from_text()
        )
        if mac:
            out["mac_address"] = mac

        ip = network.get("IP Address") or self._extract_ip_from_text()
        if ip:
            out["ip_address"] = ip

        return out

    # --- model / status ---
    def _parse_model(self) -> str | None:
        # Title or header span, e.g. "ET-8500 Series" / "WF-7720 Series"
        t = self.soup.find("title")
        if isinstance(t, Tag) and t.text.strip():
            return f"Epson {t.text.strip()}"
        head_span = self.soup.find("span", class_="header")
        if isinstance(head_span, Tag) and head_span.get_text(strip=True):
            return f"Epson {head_span.get_text(strip=True)}"
        return None

    def _parse_statuses(self) -> dict[str, str | None]:
        out: dict[str, str | None] = {}

        # Printer status (modern pages)
        fs_prt = self.soup.find("fieldset", id="PRT_STATUS")
        if isinstance(fs_prt, Tag):
            txt = fs_prt.get_text(" ", strip=True)
            out["printer_status"] = self._clean_status(txt)

        # Scanner status (when present)
        fs_scn = self.soup.find("fieldset", id="SCN_STATUS")
        if isinstance(fs_scn, Tag):
            txt = fs_scn.get_text(" ", strip=True)
            out["scanner_status"] = self._clean_status(txt)

        # Fallback for older layout (e.g., WF-3540): .information span -> "Available."
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
        # Drop leading "Printer Status:" / "Scanner Status:" labels if present
        s = re.sub(
            r"^(?:printer|scanner)\s+status\s*[:\-]?\s*", "", s, flags=re.IGNORECASE
        )
        # Trim a tiny trailing period for short phrases like "Available."
        if len(s) <= MAX_STATUS_LENGTH and s.endswith("."):
            s = s[:-1]
        return s or None

    # --- inks / maintenance ---
    def _parse_inks_and_maintenance(self) -> tuple[dict[str, int], int | None]:
        """Parse tank heights and the maintenance/waste box level.

        Heights are 0-50px for tanks; map to 0-100%.
        """
        inks: dict[str, int] = {}
        maintenance: int | None = None

        for li in self.soup.select("li.tank"):
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
            pct = self._li_bar_percent(li)
            if pct is None:
                # XP-2200 series: level encoded via linear-gradient on inner div.tank
                pct = self._li_gradient_percent(li)
                if pct is None:
                    continue
            if is_maintenance:
                maintenance = pct
            elif label:
                inks[label] = pct

        return inks, maintenance

    def _li_bar_percent(self, li: Tag) -> int | None:
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
                return int(h) * 2
            h2 = _height_from_style(img)
            if h2 is not None:
                return int(h2) * 2

        return None

    def _li_gradient_percent(self, li: Tag) -> int | None:
        """
        Return 0-100 ink percentage from a 'background: linear-gradient(...)' on inner
        div.tank.
        """
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
        return _percent_from_linear_gradient(bar_div.get("style"))

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
                val = _clean_value(td_val.get_text(" ", strip=True))
                if key:
                    data[key] = val
        return data

    # --- misc fallbacks (value-pattern based) ---
    def _extract_mac_from_text(self) -> str | None:
        txt = self.soup.get_text(" ", strip=True)
        m = RE_MAC.search(txt)
        return m.group(0) if m else None

    def _extract_ip_from_text(self) -> str | None:
        txt = self.soup.get_text(" ", strip=True)
        m = RE_IPV4.search(txt)
        return m.group(0) if m else None

    def _extract_device_name(self) -> str | None:
        # e.g. EPSON0C9E89 / EPSON06274A / EPSON053D87
        txt = self.soup.get_text(" ", strip=True)
        m = RE_EPSON_DEVNAME.search(txt)
        return m.group(0).upper() if m else None
