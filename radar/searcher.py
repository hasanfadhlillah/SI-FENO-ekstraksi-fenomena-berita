# File: radar/searcher.py
"""
Modul B: Multi-Source Search Engine Integrator
Sumber: DuckDuckGo News + Google News RSS + DuckDuckGo Web
PERBAIKAN: Fix DDG package name + resolve Google News redirect URLs
"""

import time
import re
import base64
import requests
import feedparser
from datetime import datetime
from ddgs import DDGS   # ← DIPERBAIKI: dari duckduckgo_search → ddgs


# ─── HELPER ────────────────────────────────────────────────────────────────────

def _normalisasi_url(url: str) -> str:
    """Hapus parameter tracking agar deduplikasi lebih akurat."""
    for param in ["?utm_source", "?ref=", "&utm", "?from=", "#"]:
        if param in url:
            url = url.split(param)[0]
    return url.rstrip("/")


def _resolve_google_news_url(google_url: str) -> str:
    """
    FUNGSI KUNCI: Decode/resolve URL redirect Google News RSS ke URL artikel asli.
    Google News RSS membungkus URL dalam format:
    https://news.google.com/rss/articles/CBMi[base64_encoded_data]
    
    Strategi:
    1. Coba decode base64 dari path URL (cepat, tanpa request)
    2. Jika gagal, follow redirect HTTP (lebih lambat tapi reliable)
    """
    if not google_url or "news.google.com" not in google_url:
        return google_url  # Bukan URL Google, kembalikan apa adanya

    # STRATEGI 1: Follow HTTP redirect (paling reliable)
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(google_url, headers=headers, timeout=10, allow_redirects=True)
        final_url = resp.url
        
        # Pastikan bukan halaman Google sendiri
        if "google.com" not in final_url and final_url != google_url:
            return _normalisasi_url(final_url)
    except Exception:
        pass

    # STRATEGI 2: Coba decode dari encoded path (tanpa request, cepat)
    try:
        # Format: /rss/articles/[encoded] atau /articles/[encoded]
        match = re.search(r'/articles/([A-Za-z0-9_-]+)', google_url)
        if match:
            encoded = match.group(1)
            # Tambahkan padding base64 jika perlu
            padding = 4 - len(encoded) % 4
            if padding != 4:
                encoded += "=" * padding
            decoded = base64.urlsafe_b64decode(encoded).decode("utf-8", errors="ignore")
            # Cari URL di dalam decoded string
            url_match = re.search(r'https?://[^\s\x00-\x1f]+', decoded)
            if url_match:
                return _normalisasi_url(url_match.group(0))
    except Exception:
        pass

    # Jika semua gagal, kembalikan URL Google aslinya
    return google_url


def _parse_tanggal(tanggal_str: str) -> str:
    """Normalisasi berbagai format tanggal ke YYYY-MM-DD."""
    if not tanggal_str:
        return ""
    for fmt in [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d"
    ]:
        try:
            # Potong string ke panjang format + buffer
            return datetime.strptime(tanggal_str[:35], fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    tahun = re.search(r'\d{4}', tanggal_str)
    return tahun.group() if tahun else tanggal_str[:10]


def _dalam_rentang_tanggal(tanggal_artikel: str, mulai: str, selesai: str) -> bool:
    """Cek apakah tanggal artikel masuk dalam rentang yang diminta."""
    if not tanggal_artikel or len(tanggal_artikel) < 10:
        return True
    try:
        dt         = datetime.strptime(tanggal_artikel[:10], "%Y-%m-%d")
        dt_mulai   = datetime.strptime(mulai,   "%Y-%m-%d")
        dt_selesai = datetime.strptime(selesai, "%Y-%m-%d")
        return dt_mulai <= dt <= dt_selesai
    except Exception:
        return True


def _deduplikasi(list_artikel: list[dict]) -> list[dict]:
    """Hapus duplikat berdasarkan URL."""
    url_seen = set()
    hasil = []
    for item in list_artikel:
        url = item.get("url", "")
        if url and url not in url_seen:
            url_seen.add(url)
            hasil.append(item)
    return hasil


def _buang_homepage(list_artikel: list[dict]) -> list[dict]:
    """Filter homepage + URL Google News yang belum ter-resolve."""
    hasil = []
    for item in list_artikel:
        url = item.get("url", "")
        if not url:
            continue

        # ─── PERBAIKAN: Buang URL Google News yang belum ter-resolve ───
        if "news.google.com" in url:
            print(f"      [Filter] Buang URL Google belum ter-resolve: {url[:60]}")
            continue

        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            path   = parsed.path.strip("/")
            if len(path) >= 10:
                hasil.append(item)
            else:
                print(f"      [Filter] Buang homepage: {url}")
        except Exception:
            hasil.append(item)
    return hasil


# ─── SUMBER 1: DUCKDUCKGO NEWS ─────────────────────────────────────────────────

def cari_duckduckgo_news(
    keywords: list[str],
    tanggal_mulai: str,
    tanggal_selesai: str,
    max_per_keyword: int = 8
) -> list[dict]:
    """Sumber 1: DuckDuckGo News. Gratis unlimited."""
    hasil = []
    selisih_hari = (
        datetime.strptime(tanggal_selesai, "%Y-%m-%d") -
        datetime.strptime(tanggal_mulai,   "%Y-%m-%d")
    ).days
    timelimit = "d" if selisih_hari <= 7 else "w" if selisih_hari <= 30 else "m"

    try:
        with DDGS() as ddgs:
            for keyword in keywords:
                try:
                    print(f"      [DDG News] '{keyword}'...")
                    berita = list(ddgs.news(keyword, max_results=max_per_keyword, timelimit=timelimit))
                    for item in berita:
                        url = _normalisasi_url(item.get("url", ""))
                        tgl = _parse_tanggal(item.get("date", ""))
                        if url and _dalam_rentang_tanggal(tgl, tanggal_mulai, tanggal_selesai):
                            hasil.append({
                                "url":           url,
                                "judul":         item.get("title", ""),
                                "tanggal":       tgl,
                                "sumber":        item.get("source", ""),
                                "sumber_search": "DuckDuckGo News"
                            })
                    time.sleep(1.0)
                except Exception as e:
                    print(f"      [DDG News] Error '{keyword}': {e}")
                    time.sleep(3)
                    continue
    except Exception as e:
        print(f"      [DDG News] Gagal inisialisasi: {e}")

    print(f"   → DuckDuckGo News: {len(hasil)} artikel")
    return hasil


# ─── SUMBER 2: GOOGLE NEWS RSS ─────────────────────────────────────────────────

def cari_google_news_rss(
    keywords: list[str],
    tanggal_mulai: str,
    tanggal_selesai: str,
    max_per_keyword: int = 10
) -> list[dict]:
    """
    Sumber 2: Google News RSS Feed. 100% GRATIS UNLIMITED.
    DIPERBAIKI: Resolve redirect URL Google ke URL artikel asli.
    """
    hasil = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    for keyword in keywords:
        try:
            print(f"      [Google RSS] '{keyword}'...")
            keyword_encoded = requests.utils.quote(keyword)
            rss_url = (
                f"https://news.google.com/rss/search"
                f"?q={keyword_encoded}"
                f"&hl=id&gl=ID&ceid=ID:id"
            )

            resp = requests.get(rss_url, headers=headers, timeout=20)
            if resp.status_code != 200:
                print(f"      [Google RSS] HTTP {resp.status_code}")
                continue

            feed  = feedparser.parse(resp.content)
            count = 0

            for entry in feed.entries:
                if count >= max_per_keyword:
                    break

                # ─── PERBAIKAN UTAMA: Resolve URL Google ke URL artikel asli ───
                url_google = entry.get("link", "")
                if not url_google:
                    continue

                # Follow redirect untuk dapat URL artikel asli
                url_asli = _resolve_google_news_url(url_google)
                url = _normalisasi_url(url_asli)

                judul = entry.get("title", "")
                # Bersihkan " - Nama Media" dari judul RSS Google
                if " - " in judul:
                    judul = judul.rsplit(" - ", 1)[0].strip()

                tgl = _parse_tanggal(entry.get("published", ""))

                if url and _dalam_rentang_tanggal(tgl, tanggal_mulai, tanggal_selesai):
                    hasil.append({
                        "url":           url,
                        "judul":         judul,
                        "tanggal":       tgl,
                        "sumber":        entry.get("source", {}).get("title", ""),
                        "sumber_search": "Google News RSS"
                    })
                    count += 1

            time.sleep(0.5)

        except Exception as e:
            print(f"      [Google RSS] Error: {e}")
            time.sleep(1)
            continue

    print(f"   → Google News RSS: {len(hasil)} artikel")
    return hasil


# ─── SUMBER 3: DUCKDUCKGO WEB (FALLBACK) ──────────────────────────────────────

def cari_duckduckgo_web(
    keywords: list[str],
    tanggal_mulai: str,
    tanggal_selesai: str,
    max_per_keyword: int = 5
) -> list[dict]:
    """Sumber 3: DDG Web Search. Fallback jika News+RSS < 5 artikel."""
    hasil = []
    tahun = tanggal_mulai[:4]

    try:
        with DDGS() as ddgs:
            for keyword in keywords[:3]:
                try:
                    keyword_tahun = f"{keyword} {tahun}"
                    print(f"      [DDG Web] '{keyword_tahun}'...")
                    web_results = list(ddgs.text(keyword_tahun, max_results=max_per_keyword))
                    for item in web_results:
                        url = _normalisasi_url(item.get("href", ""))
                        if url:
                            hasil.append({
                                "url":           url,
                                "judul":         item.get("title", ""),
                                "tanggal":       "",
                                "sumber":        "",
                                "sumber_search": "DuckDuckGo Web"
                            })
                    time.sleep(1)
                except Exception as e:
                    print(f"      [DDG Web] Error: {e}")
                    continue
    except Exception as e:
        print(f"      [DDG Web] Gagal inisialisasi: {e}")

    print(f"   → DuckDuckGo Web: {len(hasil)} artikel")
    return hasil


# ─── FUNGSI UTAMA ──────────────────────────────────────────────────────────────

def cari_berita_multi_sumber(
    keywords_per_wilayah: dict,
    wilayah: str,
    tanggal_mulai: str,
    tanggal_selesai: str
) -> list[dict]:
    """Fungsi utama Modul B — 100% Gratis Unlimited."""
    keywords = keywords_per_wilayah.get(wilayah, [])
    if not keywords:
        return []

    tampilan = "KOTA MAGELANG" if wilayah == "magelang" else wilayah.upper()
    print(f"\n   📡 Mencari di wilayah: {tampilan} ({len(keywords)} keyword)")
    print(f"   📅 Rentang: {tanggal_mulai} s.d. {tanggal_selesai}")

    hasil_ddg = cari_duckduckgo_news(keywords, tanggal_mulai, tanggal_selesai)
    hasil_rss = cari_google_news_rss(keywords, tanggal_mulai, tanggal_selesai)

    gabungan = _deduplikasi(hasil_ddg + hasil_rss)

    # ─── PERBAIKAN TAMBAHAN: Buang homepage sebelum scraping ───
    gabungan = _buang_homepage(gabungan)

    if len(gabungan) < 5:
        print(f"   ⚠️ Gabungan DDG+RSS hanya {len(gabungan)} → aktifkan DDG Web...")
        hasil_web = cari_duckduckgo_web(keywords, tanggal_mulai, tanggal_selesai)
        gabungan  = _deduplikasi(gabungan + hasil_web)
        gabungan  = _buang_homepage(gabungan)

    print(f"\n   📦 Total unik artikel (sudah filter homepage): {len(gabungan)}")
    return gabungan