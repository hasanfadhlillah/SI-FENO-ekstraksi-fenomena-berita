# File: scraper.py
import requests
from html.parser import HTMLParser

# ─── Detektor Cloudflare ───────────────────────────────────────────────────────
CLOUDFLARE_TITLES = [
    "attention required", "just a moment",
    "checking your browser", "enable javascript", "403 forbidden"
]

def _is_cloudflare_block(judul: str, teks: str) -> bool:
    """Mendeteksi apakah Jina mengembalikan halaman Cloudflare, bukan artikel asli."""
    j = judul.lower()
    t = teks.lower()
    return (
        any(kw in j for kw in CLOUDFLARE_TITLES) or
        ("ray id" in t and "cloudflare" in t) or
        len(teks) < 500  # Teks terlalu pendek = bukan artikel
    )

# ─── Ekstraktor HTML Sederhana (tanpa library tambahan) ───────────────────────
class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.teks = []
        self._skip = False
        self._skip_tags = {'script', 'style', 'nav', 'footer', 'head', 'noscript'}

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip = True

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip = False

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.teks.append(data.strip())

def _html_ke_teks(html: str) -> str:
    p = _HTMLTextExtractor()
    p.feed(html)
    return "\n".join(p.teks)

# ─── 3 Metode Scraping ────────────────────────────────────────────────────────
def _metode_jina(url: str) -> dict | None:
    """Metode 1: Jina Reader API (bypass Cloudflare otomatis)."""
    try:
        resp = requests.get(
            f"https://r.jina.ai/{url}",
            headers={"Accept": "application/json", "X-Return-Format": "markdown"},
            timeout=45
        )
        if resp.status_code != 200:
            return None
        data = resp.json().get("data", {})
        return {
            "judul": data.get("title", ""),
            "teks": data.get("content", "")
        }
    except Exception:
        return None

def _metode_direct(url: str) -> dict | None:
    """Metode 2: Request langsung dengan header browser asli."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
            "Referer": "https://www.google.com/",
        }
        resp = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        if resp.status_code != 200:
            return None
        teks = _html_ke_teks(resp.text)
        # Ambil judul dari tag <title>
        judul = ""
        if "<title>" in resp.text:
            start = resp.text.find("<title>") + 7
            end = resp.text.find("</title>", start)
            judul = resp.text[start:end].strip()
        return {"judul": judul, "teks": teks}
    except Exception:
        return None

def _metode_google_cache(url: str) -> dict | None:
    """Metode 3: Google Cache sebagai fallback terakhir."""
    try:
        cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(cache_url, headers=headers, timeout=30)
        if resp.status_code != 200:
            return None
        teks = _html_ke_teks(resp.text)
        return {"judul": "Dari Google Cache", "teks": teks}
    except Exception:
        return None

# ─── Fungsi Utama ─────────────────────────────────────────────────────────────
def scrape_berita(url: str) -> dict:
    """
    Scraper berlapis 3:
    Jina Reader → Direct Request → Google Cache
    """
    metode_list = [
        ("Jina Reader API",   _metode_jina),
        ("Direct Request",    _metode_direct),
        ("Google Cache",      _metode_google_cache),
    ]

    for nama_metode, fungsi in metode_list:
        print(f"   -> [Mencoba] {nama_metode}...")
        hasil = fungsi(url)

        if hasil is None:
            print(f"   -> [Gagal] {nama_metode}: Tidak ada respons.")
            continue

        judul = hasil.get("judul", "")
        teks  = hasil.get("teks", "")

        if _is_cloudflare_block(judul, teks):
            print(f"   -> [Diblokir] {nama_metode}: Kena Cloudflare challenge.")
            continue

        if len(teks) < 200:
            print(f"   -> [Gagal] {nama_metode}: Teks terlalu pendek ({len(teks)} karakter).")
            continue

        # Sukses!
        print(f"   -> [✅ Sukses] via {nama_metode}!")
        return {
            "status":  "sukses",
            "metode":  nama_metode,
            "url":     url,
            "judul":   judul or "Judul diekstrak AI",
            "tanggal": "Diekstrak otomatis oleh AI",
            "teks":    teks
        }

    # Semua metode gagal
    return {
        "status": "error",
        "pesan": (
            "Semua metode scraping gagal. "
            "Situs ini diproteksi sangat ketat (Cloudflare Enterprise / Login Required). "
            "Coba salin teks artikel secara manual."
        )
    }