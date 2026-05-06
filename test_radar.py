# File: test_radar.py (di root folder, bukan di dalam radar/)
import json
import os
from dotenv import load_dotenv
from radar.pipeline import scan_kategori, batch_scan_semua_kategori

load_dotenv()

# ── PENGATURAN TEST ─────────────────────────────────────────────────────────────
KATEGORI_TEST    = "Tanaman Pangan"      # Ganti untuk test kategori lain
TANGGAL_MULAI    = "2026-01-01"
TANGGAL_SELESAI  = "2026-03-31"
MIN_SKOR         = 6
PAKSA_PROSES_ULANG = True               # Ubah ke True jika ingin memaksa AI membaca ulang artikel yang pernah gagal

# Daftar kategori untuk batch test (subset kecil)
BATCH_TEST = [
    "Tanaman Pangan",
    "Peternakan",
    "Industri Makanan dan Minuman",
    "Angkutan Darat",
    "Penyediaan Akomodasi",
]

def test_single():
    """Test scan 1 kategori."""
    print("=" * 60)
    print("  MODE: SINGLE SCAN")
    print("=" * 60)

    hasil = scan_kategori(
        nama_kategori=KATEGORI_TEST,
        tanggal_mulai=TANGGAL_MULAI,
        tanggal_selesai=TANGGAL_SELESAI,
        min_skor=MIN_SKOR,
        aktifkan_fallback=True,
        paksa_proses_ulang=PAKSA_PROSES_ULANG
    )

    print("\n" + "=" * 60)
    print("  HASIL RADAR SCAN")
    print("=" * 60)

    if hasil["status"] == "sukses":
        print(f"✅ SUKSES — {hasil['jumlah_valid']} artikel valid ditemukan")
        print(f"   Level ditemukan: {hasil['level_ditemukan']}\n")
        for i, art in enumerate(hasil["artikel_valid"], 1):
            skor = art["skor_relevansi"]
            badge = "🟢" if skor >= 8 else "🟡"
            print(f"  {badge} [{i}] Skor {skor}/10")
            print(f"      Judul  : {art['judul'][:70]}")
            print(f"      URL    : {art['url'][:70]}")
            print(f"      Alasan : {art['alasan_singkat']}")
            print(f"      📊 Data angka: {art['ada_data_angka']} | Perbandingan: {art['ada_perbandingan_waktu']}")
            print()
    else:
        print(f"❌ BUNTU — {hasil['pesan_utama']}")
        print(f"\n💡 Saran keyword manual:")
        for kw in hasil.get("saran_keyword", []):
            print(f"   → {kw}")
        print(f"\n📰 Sumber yang disarankan:")
        for s in hasil.get("saran_sumber", []):
            print(f"   → {s}")


def test_batch():
    """Test batch scan beberapa kategori."""
    print("=" * 60)
    print("  MODE: BATCH SCAN")
    print("=" * 60)

    hasil = batch_scan_semua_kategori(
        daftar_kategori=BATCH_TEST,
        tanggal_mulai=TANGGAL_MULAI,
        tanggal_selesai=TANGGAL_SELESAI,
        min_skor=MIN_SKOR,
        paksa_proses_ulang=PAKSA_PROSES_ULANG
    )

    print("\n" + "=" * 60)
    print("  BATCH SCAN DASHBOARD")
    print("=" * 60)
    r = hasil["ringkasan"]
    print(f"Total kategori : {hasil['total_kategori']}")
    print(f"Ada berita     : {r['sukses']} ({r['persen_sukses']}%)")
    print(f"Tidak ada      : {r['buntu']}")

    print("\n✅ Kategori dengan berita:")
    for item in hasil["ada_berita"]:
        print(f"   • {item['kategori']:40} → {item['jumlah']} artikel")

    print("\n❌ Kategori tanpa berita:")
    for item in hasil["tidak_ada_berita"]:
        print(f"   • {item['kategori']}")


# ── PILIH MODE TEST ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "single"

    if mode == "batch":
        test_batch()
    else:
        test_single()