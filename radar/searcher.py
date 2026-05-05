# File: radar/searcher.py
"""
Modul B: Multi-Source Search Engine Integrator
Sumber: DuckDuckGo News + Google News RSS + DuckDuckGo Web
"""

import time
import re
import requests
import feedparser
from datetime import datetime, timedelta
from duckduckgo_search import DDGS


# ─── HELPER ────────────────────────────────────────────────────────────────────

def _normalisasi_url(url: str) -> str:
    """Hapus parameter tracking agar deduplikasi lebih akurat."""
    for param in ["?utm_source", "?ref=", "&utm", "?from=", "#"]:
        if param in url:
            url = url.split(param)[0]
    return url.rstrip("/")


def _parse_tanggal(tanggal_str: str) -> str:
    """Normalisasi berbagai format tanggal ke YYYY-MM-DD."""
    if not tanggal_str:
        return ""
    # Format RSS biasa: "Mon, 05 May 2026 10:30:00 +0700"
    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"]:
        try:
            return datetime.strptime(tanggal_str[:len(fmt)+5], fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    # Fallback: ambil 4 digit tahun saja
    tahun = re.search(r'\d{4}', tanggal_str)
    return tahun.group() if tahun else tanggal_str[:10]


def _dalam_rentang_tanggal(tanggal_artikel: str, mulai: str, selesai: str) -> bool:
    """Cek apakah tanggal artikel masuk dalam rentang yang diminta."""
    if not tanggal_artikel or len(tanggal_artikel) < 10:
        return True  # Kalau tanggal tidak jelas, loloskan saja
    try:
        dt = datetime.strptime(tanggal_artikel[:10], "%Y-%m-%d")
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


# ─── SUMBER 1: DUCKDUCKGO NEWS ─────────────────────────────────────────────────

def cari_duckduckgo_news(
    keywords: list[str],
    tanggal_mulai: str,
    tanggal_selesai: str,
    max_per_keyword: int = 8
) -> list[dict]:
    """
    Sumber 1: DuckDuckGo News Search.
    Gratis, tanpa API key, tanpa limit akun.
    """
    hasil = []
    selisih_hari = (datetime.strptime(tanggal_selesai, "%Y-%m-%d") -
                    datetime.strptime(tanggal_mulai, "%Y-%m-%d")).days
    timelimit = "d" if selisih_hari <= 7 else "w" if selisih_hari <= 30 else "m"

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
                time.sleep(0.8)  # Jeda agar IP tidak diblokir sementara
            except Exception as e:
                print(f"      [DDG News] Error: {e}")
                time.sleep(2)
                continue

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
    Sumber 2: Google News RSS Feed.
    100% GRATIS UNLIMITED — tidak ada API key, tidak ada limit bulanan.
    Menggunakan endpoint publik RSS Google News dengan filter bahasa Indonesia.
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

            # Encode keyword untuk URL
            keyword_encoded = requests.utils.quote(keyword)

            # Endpoint Google News RSS — gratis tanpa batas
            # hl=id → bahasa Indonesia | gl=ID → negara Indonesia | ceid=ID:id → region
            rss_url = (
                f"https://news.google.com/rss/search"
                f"?q={keyword_encoded}"
                f"&hl=id&gl=ID&ceid=ID:id"
            )

            # Fetch RSS feed
            resp = requests.get(rss_url, headers=headers, timeout=20)
            if resp.status_code != 200:
                print(f"      [Google RSS] HTTP {resp.status_code} untuk '{keyword}'")
                continue

            # Parse RSS dengan feedparser
            feed = feedparser.parse(resp.content)
            count = 0

            for entry in feed.entries:
                if count >= max_per_keyword:
                    break

                # Ambil URL asli (bukan redirect Google)
                url_raw = entry.get("link", "")
                # Google News RSS kadang wrap URL-nya, ambil yang asli
                if "news.google.com" in url_raw:
                    # Coba ambil dari tag <source>
                    url_raw = entry.get("source", {}).get("href", url_raw) or url_raw

                url = _normalisasi_url(url_raw)
                judul = entry.get("title", "")
                tgl   = _parse_tanggal(entry.get("published", ""))

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
    """
    Sumber 3: DuckDuckGo Web Search (bukan News).
    Dipakai sebagai fallback jika News + RSS gabungan < 5 artikel.
    Menambahkan filter tahun ke keyword secara manual.
    """
    hasil = []
    tahun = tanggal_mulai[:4]

    with DDGS() as ddgs:
        for keyword in keywords[:3]:  # Batasi 3 keyword agar tidak terlalu lambat
            try:
                # Tambahkan tahun ke keyword agar lebih relevan secara waktu
                keyword_tahun = f"{keyword} {tahun}"
                print(f"      [DDG Web] '{keyword_tahun}'...")
                web_results = list(ddgs.text(keyword_tahun, max_results=max_per_keyword))
                for item in web_results:
                    url = _normalisasi_url(item.get("href", ""))
                    if url:
                        hasil.append({
                            "url":           url,
                            "judul":         item.get("title", ""),
                            "tanggal":       "",  # Web search tidak ada tanggal
                            "sumber":        "",
                            "sumber_search": "DuckDuckGo Web"
                        })
                time.sleep(1)
            except Exception as e:
                print(f"      [DDG Web] Error: {e}")
                continue

    print(f"   → DuckDuckGo Web: {len(hasil)} artikel")
    return hasil


# ─── FUNGSI UTAMA ──────────────────────────────────────────────────────────────

def cari_berita_multi_sumber(
    keywords_per_wilayah: dict,
    wilayah: str,
    tanggal_mulai: str,
    tanggal_selesai: str
) -> list[dict]:
    """
    Fungsi utama Modul B — 100% Gratis Unlimited.
    Strategi:
    1. DuckDuckGo News → selalu jalan
    2. Google News RSS → selalu jalan
    3. DuckDuckGo Web  → hanya jika gabungan < 5 artikel
    """
    keywords = keywords_per_wilayah.get(wilayah, [])
    if not keywords:
        return []
    
    # Ubah tampilan terminal agar staf BPS tenang melihat kata "Kota"
    tampilan_wilayah = "KOTA MAGELANG" if wilayah == "magelang" else wilayah.upper()

    print(f"\n   📡 Mencari di wilayah: {tampilan_wilayah} ({len(keywords)} keyword)")
    print(f"   📅 Rentang: {tanggal_mulai} s.d. {tanggal_selesai}")

    # Sumber 1: DuckDuckGo News (selalu)
    hasil_ddg = cari_duckduckgo_news(keywords, tanggal_mulai, tanggal_selesai)

    # Sumber 2: Google News RSS (selalu)
    hasil_rss = cari_google_news_rss(keywords, tanggal_mulai, tanggal_selesai)

    # Gabungkan + deduplikasi
    gabungan = _deduplikasi(hasil_ddg + hasil_rss)

    # Sumber 3: DDG Web — hanya jika kurang
    if len(gabungan) < 5:
        print(f"   ⚠️ Gabungan DDG+RSS hanya {len(gabungan)} artikel → aktifkan DDG Web...")
        hasil_web = cari_duckduckgo_web(keywords, tanggal_mulai, tanggal_selesai)
        gabungan  = _deduplikasi(gabungan + hasil_web)

    print(f"\n   📦 Total unik sebelum filter DB: {len(gabungan)} artikel")
    return gabungan