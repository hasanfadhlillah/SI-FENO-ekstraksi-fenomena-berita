# File: radar/database.py
"""
Modul C: SQLite State Tracker
Mengelola database untuk tracking artikel dan status kategori.
Mencegah duplikasi berita antar sesi dan antar kategori.
"""

import sqlite3
import os
from datetime import datetime

# Path database — selalu di root folder proyek
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sifeno_tracker.db")


def get_connection() -> sqlite3.Connection:
    """Membuat koneksi ke database SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Agar hasil bisa diakses seperti dict
    return conn


def inisialisasi_database():
    """
    Membuat semua tabel jika belum ada.
    Aman untuk dipanggil berkali-kali (idempotent).
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Tabel 1: Riwayat semua artikel yang pernah ditemukan radar
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS riwayat_artikel (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            url_berita       TEXT    UNIQUE NOT NULL,
            judul_berita     TEXT,
            kategori_pdrb    TEXT,
            triwulan         TEXT,
            skor_relevansi   INTEGER DEFAULT 0,
            alasan_ai        TEXT,
            ada_data_angka   INTEGER DEFAULT 0,
            ada_perbandingan INTEGER DEFAULT 0,
            relevan_kategori INTEGER DEFAULT 0,
            status           TEXT    DEFAULT 'ditemukan',
            tanggal_ditemukan DATETIME,
            tanggal_diekstrak DATETIME
        )
    """)

    # Tabel 2: Status ringkas per kategori PDRB per triwulan
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS status_kategori (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            kategori_pdrb         TEXT    NOT NULL,
            triwulan              TEXT    NOT NULL,
            status_berita         TEXT    DEFAULT 'belum_scan',
            jumlah_artikel_valid  INTEGER DEFAULT 0,
            terakhir_scan         DATETIME,
            UNIQUE(kategori_pdrb, triwulan)
        )
    """)

    conn.commit()
    conn.close()
    print("✅ [Database] Inisialisasi selesai.")


# ─── FUNGSI ARTIKEL ────────────────────────────────────────────────────────────

def cek_url_sudah_ada(url: str) -> dict | None:
    """
    Cek apakah URL sudah pernah masuk database.
    Return: dict info artikel jika ada, None jika belum.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM riwayat_artikel WHERE url_berita = ?", (url,))
    baris = cursor.fetchone()
    conn.close()
    return dict(baris) if baris else None


def simpan_artikel(
    url: str,
    judul: str,
    kategori: str,
    triwulan: str,
    skor: int,
    alasan: str,
    ada_data_angka: bool,
    ada_perbandingan: bool,
    relevan_kategori: bool,
    layak_ekstrak: bool
):
    """
    Menyimpan artikel baru ke database.
    Jika URL sudah ada (diproses ulang), datanya akan di-OVERWRITE dengan hasil AI terbaru.
    """
    conn = get_connection()
    cursor = conn.cursor()
    status = "ditemukan" if layak_ekstrak else "tidak_lolos"
    try:
        # PERBAIKAN: Gunakan UPSERT agar percobaan ulang bisa memperbarui status
        cursor.execute("""
            INSERT INTO riwayat_artikel
            (url_berita, judul_berita, kategori_pdrb, triwulan,
             skor_relevansi, alasan_ai, ada_data_angka, ada_perbandingan,
             relevan_kategori, status, tanggal_ditemukan)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url_berita) DO UPDATE SET
                judul_berita = excluded.judul_berita,
                kategori_pdrb = excluded.kategori_pdrb,
                triwulan = excluded.triwulan,
                skor_relevansi = excluded.skor_relevansi,
                alasan_ai = excluded.alasan_ai,
                ada_data_angka = excluded.ada_data_angka,
                ada_perbandingan = excluded.ada_perbandingan,
                relevan_kategori = excluded.relevan_kategori,
                status = excluded.status,
                tanggal_ditemukan = excluded.tanggal_ditemukan
        """, (
            url, judul, kategori, triwulan,
            skor, alasan,
            int(ada_data_angka), int(ada_perbandingan), int(relevan_kategori),
            status, datetime.now().isoformat()
        ))
        conn.commit()
    finally:
        conn.close()


def tandai_artikel_diekstrak(url: str):
    """Mengubah status artikel menjadi 'diekstrak' saat staf mengekstraknya."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE riwayat_artikel
        SET status = 'diekstrak', tanggal_diekstrak = ?
        WHERE url_berita = ?
    """, (datetime.now().isoformat(), url))
    conn.commit()
    conn.close()


def tandai_artikel_ditolak(url: str):
    """Mengubah status artikel menjadi 'ditolak_user' agar tidak muncul lagi."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE riwayat_artikel
        SET status = 'ditolak_user'
        WHERE url_berita = ?
    """, (url,))
    conn.commit()
    conn.close()


def ambil_artikel_valid(kategori: str, triwulan: str) -> list[dict]:
    """
    Ambil semua artikel yang lolos seleksi untuk kategori & triwulan tertentu.
    Hanya yang status = 'ditemukan' (belum diekstrak, belum ditolak).
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM riwayat_artikel
        WHERE kategori_pdrb = ?
          AND triwulan      = ?
          AND status        = 'ditemukan'
          AND skor_relevansi >= 6
        ORDER BY skor_relevansi DESC
    """, (kategori, triwulan))
    hasil = [dict(b) for b in cursor.fetchall()]
    conn.close()
    return hasil


def filter_url_baru(list_url: list[str], paksa_proses_ulang: bool = False) -> tuple[list[str], list[dict]]:
    """
    Memisahkan URL menjadi dua kelompok:
    - url_baru: lolos untuk di-scrape (baru, atau dipaksa ulang)
    - daftar_warning: peringatan artikel sudah diekstrak
    """
    url_baru = []
    daftar_warning = []

    for url in list_url:
        info = cek_url_sudah_ada(url)

        if info is None:
            # 100% URL Baru
            url_baru.append(url)
            
        elif info["status"] == "diekstrak":
            # JANGAN DIBIARKAN LOLOS. Ini sudah dipakai oleh staf, cegah kerja dobel!
            tanggal = info.get('tanggal_diekstrak', 'Tanggal tidak diketahui')
            tanggal_rapi = tanggal[:10] if tanggal else ""
            
            daftar_warning.append({
                "url": url,
                "judul": info["judul_berita"],
                "kategori_lama": info["kategori_pdrb"],
                "tanggal_ekstrak": tanggal_rapi,
                "pesan": f"⚠️ Sudah diekstrak untuk '{info['kategori_pdrb']}' pada {tanggal_rapi}"
            })
            
        elif info["status"] == "ditemukan":
            # Berita ini valid dan sedang nongkrong di layar antrean.
            # Tidak perlu dibaca ulang oleh AI, biarkan saja.
            pass
            
        elif info["status"] in ["ditolak_user", "tidak_lolos"]:
            # JIKA USER MENCENTANG FITUR "PROSES ULANG" DI STREAMLIT
            if paksa_proses_ulang:
                print(f"   🔄 Memproses ulang URL yang pernah gagal/ditolak: {url}")
                url_baru.append(url)
            else:
                # Default: Hemat kuota, abaikan berita sampah masa lalu
                pass

    return url_baru, daftar_warning


# ─── FUNGSI STATUS KATEGORI ────────────────────────────────────────────────────

def update_status_kategori(kategori: str, triwulan: str, jumlah_valid: int):
    """Update atau insert status kategori setelah scan selesai."""
    conn = get_connection()
    cursor = conn.cursor()
    status = "ada_berita" if jumlah_valid > 0 else "tidak_ada_berita"
    cursor.execute("""
        INSERT INTO status_kategori
            (kategori_pdrb, triwulan, status_berita, jumlah_artikel_valid, terakhir_scan)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(kategori_pdrb, triwulan)
        DO UPDATE SET
            status_berita        = excluded.status_berita,
            jumlah_artikel_valid = excluded.jumlah_artikel_valid,
            terakhir_scan        = excluded.terakhir_scan
    """, (kategori, triwulan, status, jumlah_valid, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def ambil_semua_status_kategori(triwulan: str) -> list[dict]:
    """Ambil ringkasan status semua kategori untuk satu triwulan (untuk Batch Dashboard)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM status_kategori
        WHERE triwulan = ?
        ORDER BY kategori_pdrb
    """, (triwulan,))
    hasil = [dict(b) for b in cursor.fetchall()]
    conn.close()
    return hasil