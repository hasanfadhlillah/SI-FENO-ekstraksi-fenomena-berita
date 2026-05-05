# File: radar/fallback.py
"""
Modul F: Auto-Expand Fallback & Anti-Buntu
Mengatur logika fallback wilayah dan saran keyword manual jika semua level gagal.
"""

# Urutan level fallback wilayah beserta instruksi manipulasi keyword
URUTAN_FALLBACK = [
    {
        "level": 1, 
        "nama": "Kota Magelang",        
        "key": "magelang", 
        "replace": None
    },
    {
        "level": 2, 
        "nama": "Kabupaten Magelang",   
        "key": "magelang", 
        "replace": ("kota magelang", "kabupaten magelang") # Otomatis ubah keyword
    },
    {
        "level": 3, 
        "nama": "Eks-Karesidenan Kedu", 
        "key": "magelang", 
        "replace": ("kota magelang", "karesidenan kedu") # Otomatis ubah keyword
    },
    {
        "level": 4, 
        "nama": "Provinsi Jawa Tengah", 
        "key": "jateng",   
        "replace": None
    },
    {
        "level": 5, 
        "nama": "Nasional / Indonesia", 
        "key": "nasional", 
        "replace": None
    },
]

# Sumber berita lokal yang disarankan (untuk pesan anti-buntu)
SUMBER_LOKAL = [
    "radarsemarang.jawapos.com/magelang",
    "suaramerdeka.com",
    "magelangkota.go.id",
    "jatengprov.go.id",
    "antaranews.com/jawa-tengah",
    "tribunjateng.com",
    "detik.com/jateng",
]


def dapatkan_level_fallback_berikutnya(level_sekarang: int) -> dict | None:
    """
    Return konfigurasi level fallback berikutnya, atau None jika sudah habis.
    """
    for fb in URUTAN_FALLBACK:
        if fb["level"] > level_sekarang:
            return fb
    return None


def siapkan_keyword_fallback(konfig_level: dict, keywords_per_wilayah: dict) -> list[str]:
    """
    Fungsi BARU: Menyiapkan list keyword yang sudah disesuaikan dengan wilayah fallback.
    Melakukan replace string "kota magelang" menjadi "kabupaten magelang" jika diinstruksikan.
    """
    base_key = konfig_level["key"]
    base_keywords = keywords_per_wilayah.get(base_key, [])

    atur_replace = konfig_level.get("replace")

    # Jika tidak ada instruksi replace (misal level 1, 4, 5), kembalikan aslinya
    if not atur_replace:
        return base_keywords

    # Lakukan find & replace untuk menyesuaikan nama wilayah
    kata_lama, kata_baru = atur_replace
    keyword_baru = []
    for kw in base_keywords:
        # PENTING: Lakukan replace dengan case-insensitive yang aman (menggunakan lower)
        # Tapi karena di Modul A kita sudah set lower, langsung replace saja aman
        kw_modifikasi = kw.replace(kata_lama, kata_baru)
        keyword_baru.append(kw_modifikasi)

    return keyword_baru


def buat_pesan_anti_buntu(nama_kategori: str, keywords_per_wilayah: dict) -> dict:
    """
    Membuat saran keyword manual untuk ditampilkan ke user ketika semua level gagal.
    """
    semua_keyword = []
    # Kumpulkan beberapa keyword dari Kota Magelang sebagai contoh
    for kw in keywords_per_wilayah.get("magelang", []):
        semua_keyword.append(kw)

    saran_google = [f'"{kw}"' for kw in semua_keyword[:6]]

    return {
        "status": "buntu",
        "pesan_utama": f"❌ Tidak ditemukan berita fenomena statistik untuk kategori '{nama_kategori}' di semua level wilayah.",
        "saran_keyword": semua_keyword[:8],
        "saran_google":  " OR ".join(saran_google[:3]),
        "saran_sumber":  SUMBER_LOKAL,
        "tips": [
            "Coba cari di Google News dengan rentang waktu yang lebih lebar.",
            "Periksa website resmi dinas terkait (mis: portal data Pemkot Magelang).",
            "Mungkin tidak ada fenomena ekonomi pada triwulan ini untuk sektor tersebut.",
        ]
    }