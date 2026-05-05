# File: radar/pipeline.py
"""
Pipeline Utama SI-FENO RADAR
Mengintegrasikan semua modul: A (Query) → B (Search) → C (DB) → D (Scrape) → E (Screen) → F (Fallback)
"""

import os
from datetime import datetime
from dotenv import load_dotenv

from .database       import (inisialisasi_database, filter_url_baru,
                              simpan_artikel, update_status_kategori, ambil_artikel_valid)
from .query_expander import dapatkan_keywords
from .searcher       import cari_berita_multi_sumber
from .fetcher        import fetch_parallel
from .screener       import screening_batch
from .fallback       import (URUTAN_FALLBACK, dapatkan_level_fallback_berikutnya, 
                              buat_pesan_anti_buntu, siapkan_keyword_fallback)

# Di bagian ATAS file pipeline.py
load_dotenv()

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

# Gabungkan key untuk dikirim ke screener
API_KEYS_DICT = {
    "groq": GROQ_KEY,
    "gemini": GEMINI_KEY
}

# ─── Helper ────────────────────────────────────────────────────────────────────

def _hitung_triwulan(tanggal_mulai: str) -> str:
    """Konversi tanggal ke label triwulan. Format: 'TW1-2026'"""
    dt   = datetime.strptime(tanggal_mulai, "%Y-%m-%d")
    tw   = (dt.month - 1) // 3 + 1
    return f"TW{tw}-{dt.year}"


# ─── Fungsi Inti Pipeline (1 Kategori, 1 Level Wilayah) ───────────────────────

def _jalankan_pipeline_satu_level(
    nama_kategori: str,
    keywords_dict: dict,
    level_cfg: dict,
    tanggal_mulai: str,
    tanggal_selesai: str,
    triwulan: str,
    min_skor: int = 6,
    paksa_proses_ulang: bool = False,
) -> list[dict]:
    """
    Jalankan pipeline untuk 1 level wilayah.
    Return list artikel yang lolos screening.
    """
    wilayah_nama = level_cfg["nama"]
    wilayah_key = level_cfg["key"]
    
    print(f"\n{'='*55}")
    print(f"  🌍 Level Wilayah: {wilayah_nama}")
    print(f"{'='*55}")

    # PERBAIKAN 1: Terapkan fungsi replace untuk perlindungan Kota/Kabupaten Magelang!
    keyword_list = siapkan_keyword_fallback(level_cfg, keywords_dict)
    
    # Bungkus ke dalam dictionary agar formatnya sesuai dengan input searcher.py
    keywords_siap = {wilayah_key: keyword_list}

    # Gerbang 2: Search
    hasil_search = cari_berita_multi_sumber(
        keywords_siap, wilayah_key, tanggal_mulai, tanggal_selesai
    )
    if not hasil_search:
        print(f"  ⚠️ 0 artikel ditemukan di {wilayah_nama}")
        return []

    # Gerbang 3: Filter URL sudah ada di DB
    list_url = [item["url"] for item in hasil_search]
    # PERBAIKAN 3: Alirkan parameter paksa_proses_ulang ke database
    url_baru, warnings = filter_url_baru(list_url, paksa_proses_ulang)

    if warnings:
        print(f"\n  ⚠️ {len(warnings)} artikel sudah pernah diekstrak (akan dilewati):")
        for w in warnings:
            print(f"     • {w['judul'][:60]} → {w['pesan']}")

    if not url_baru:
        print("  ⚠️ Semua URL sudah ada di database atau tidak lolos sebelumnya")
        return []

    print(f"\n  🔗 URL baru/diproses ulang: {len(url_baru)} dari {len(list_url)}")

    # Gerbang 4: Parallel Scraping
    artikel_scraped = fetch_parallel(url_baru, max_workers=5)
    if not artikel_scraped:
        return []

    # Gerbang 5: AI Screening
    lolos, tidak_lolos = screening_batch(
        api_keys=API_KEYS_DICT,          # <--- INI YANG DIUBAH
        list_artikel=artikel_scraped,
        nama_kategori=nama_kategori,
        wilayah=wilayah_nama,
        min_skor=min_skor
    )

    # Simpan semua ke database (baik yang lolos maupun tidak)
    url_to_meta = {item["url"]: item for item in hasil_search}

    for artikel in lolos + tidak_lolos:
        url    = artikel.get("url", "")
        judul  = artikel.get("judul", "")
        meta   = url_to_meta.get(url, {})
        simpan_artikel(
            url=url,
            judul=judul,
            kategori=nama_kategori,
            triwulan=triwulan,
            skor=artikel.get("skor_relevansi", 0),
            alasan=artikel.get("alasan_singkat", ""),
            ada_data_angka=artikel.get("ada_data_angka", False),
            ada_perbandingan=artikel.get("ada_perbandingan_waktu", False),
            relevan_kategori=artikel.get("relevan_dengan_kategori", False),
            layak_ekstrak=artikel.get("layak_ekstrak", False),
        )

    return lolos


# ─── FUNGSI UTAMA: SCAN 1 KATEGORI ────────────────────────────────────────────

def scan_kategori(
    nama_kategori: str,
    tanggal_mulai: str,
    tanggal_selesai: str,
    min_skor: int = 6,
    aktifkan_fallback: bool = True,
    paksa_proses_ulang: bool = False,
) -> dict:
    """
    Fungsi utama RADAR untuk scan 1 kategori PDRB.
    """
    print(f"\n{'#'*55}")
    print(f"  🎯 SI-FENO RADAR — Scan Kategori")
    print(f"  📂 {nama_kategori}")
    print(f"  📅 {tanggal_mulai} s.d. {tanggal_selesai}")
    if paksa_proses_ulang:
        print(f"  🔄 MODE: Paksa Proses Ulang Aktif!")
    print(f"{'#'*55}")

    inisialisasi_database()
    triwulan = _hitung_triwulan(tanggal_mulai)

    # Gerbang 1: Query Expansion
    print(f"\n[1/6] 🔍 Menerjemahkan kategori ke keyword...")
    keywords = dapatkan_keywords(nama_kategori, GROQ_KEY)
    
    semua_artikel_valid = []
    level_sekarang = 0

    # Loop fallback wilayah
    for level_cfg in URUTAN_FALLBACK:
        level_sekarang = level_cfg["level"]
        print(f"\n[2-5/{len(URUTAN_FALLBACK)}] Pipeline Level {level_sekarang}: {level_cfg['nama']}")

        lolos = _jalankan_pipeline_satu_level(
            nama_kategori=nama_kategori,
            keywords_dict=keywords,
            level_cfg=level_cfg,
            tanggal_mulai=tanggal_mulai,
            tanggal_selesai=tanggal_selesai,
            triwulan=triwulan,
            min_skor=min_skor,
            paksa_proses_ulang=paksa_proses_ulang,
        )

        semua_artikel_valid.extend(lolos)

        if semua_artikel_valid:
            print(f"\n  ✅ {len(semua_artikel_valid)} artikel valid ditemukan di level {level_sekarang}!")
            if not aktifkan_fallback:
                break  # Tidak perlu lanjut ke level berikutnya
            if len(semua_artikel_valid) >= 3:
                break  # Sudah cukup, tidak perlu ekspansi lebih jauh

        if not aktifkan_fallback:
            break

    # Update status kategori di DB
    update_status_kategori(nama_kategori, triwulan, len(semua_artikel_valid))

    # Susun output
    if semua_artikel_valid:
        semua_artikel_valid.sort(key=lambda x: x.get("skor_relevansi", 0), reverse=True)
        return {
            "status":          "sukses",
            "kategori":        nama_kategori,
            "triwulan":        triwulan,
            "artikel_valid":   semua_artikel_valid,
            "jumlah_valid":    len(semua_artikel_valid),
            "level_ditemukan": level_sekarang,
        }
    else:
        pesan_buntu = buat_pesan_anti_buntu(nama_kategori, keywords)
        return {
            "status":        "buntu",
            "kategori":      nama_kategori,
            "triwulan":      triwulan,
            "artikel_valid": [],
            "jumlah_valid":  0,
            **pesan_buntu,
        }


# ─── FUNGSI BATCH SCAN ─────────────────────────────────────────────────────────

def batch_scan_semua_kategori(
    daftar_kategori: list[str],
    tanggal_mulai: str,
    tanggal_selesai: str,
    min_skor: int = 6,
    paksa_proses_ulang: bool = False,
    callback_progress=None  
) -> dict:
    """
    Scan semua kategori PDRB secara berurutan.
    """
    print(f"\n{'#'*55}")
    print(f"  🚀 BATCH SCAN — {len(daftar_kategori)} kategori")
    print(f"{'#'*55}")

    hasil_per_kategori = {}
    ada_berita = []
    tidak_ada  = []

    for i, kategori in enumerate(daftar_kategori, 1):
        print(f"\n[{i}/{len(daftar_kategori)}] ▶ {kategori}")
        hasil = scan_kategori(
            kategori, 
            tanggal_mulai, 
            tanggal_selesai, 
            min_skor, 
            aktifkan_fallback=True, 
            paksa_proses_ulang=paksa_proses_ulang
        )
        hasil_per_kategori[kategori] = hasil

        if hasil["status"] == "sukses":
            ada_berita.append({"kategori": kategori, "jumlah": hasil["jumlah_valid"]})
        else:
            tidak_ada.append({"kategori": kategori})

        if callback_progress:
            callback_progress(kategori, i, len(daftar_kategori))

    return {
        "total_kategori":     len(daftar_kategori),
        "ada_berita":         ada_berita,
        "tidak_ada_berita":   tidak_ada,
        "detail":             hasil_per_kategori,
        "ringkasan": {
            "sukses":  len(ada_berita),
            "buntu":   len(tidak_ada),
            "persen_sukses": round(len(ada_berita) / len(daftar_kategori) * 100, 1) if daftar_kategori else 0
        }
    }