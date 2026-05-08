# File: app.py
import streamlit as st
import pandas as pd
import os
import time
import json
import io
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from radar.database import (
    inisialisasi_database,
    ambil_semua_status_kategori,
    ambil_artikel_valid,
    tandai_artikel_diekstrak,
    tandai_artikel_ditolak
)
from radar.pipeline import scan_kategori, batch_scan_semua_kategori, _hitung_triwulan
from scraper import scrape_berita
from ai_engine import ekstrak_fenomena_ai

# ─── KONFIGURASI HALAMAN ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="SI-FENO | BPS Kota Magelang",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS Custom untuk tampilan lebih rapi
st.markdown("""
<style>
.kartu-artikel {
    border: 1px solid #dee2e6;
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 12px;
    background-color: #ffffff;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.badge-skor-hijau {
    background-color: #d4edda; color: #155724;
    padding: 4px 10px; border-radius: 20px;
    font-weight: bold; font-size: 13px; display: inline-block;
}
.badge-skor-kuning {
    background-color: #fff3cd; color: #856404;
    padding: 4px 10px; border-radius: 20px;
    font-weight: bold; font-size: 13px; display: inline-block;
}
.alasan-box {
    background-color: #f0f4ff;
    border-left: 4px solid #4a6cf7;
    padding: 10px 14px;
    border-radius: 4px;
    font-size: 14px;
    margin-top: 8px;
}
.metric-card {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white; padding: 20px; border-radius: 10px; text-align: center;
}
</style>
""", unsafe_allow_html=True)

inisialisasi_database()
load_dotenv()

KEYS = {
    "groq"    : os.environ.get("GROQ_API_KEY", ""),
    "gemini"  : os.environ.get("GEMINI_API_KEY", ""),
    "cerebras": os.environ.get("CEREBRAS_API_KEY", ""),
    "mistral" : os.environ.get("MISTRAL_API_KEY", ""),
}

DAFTAR_KATEGORI = [
    "Tanaman Pangan", "Tanaman Hortikultura Semusim", "Perkebunan Semusim",
    "Tanaman Hortikultura Tahunan", "Perkebunan Tahunan", "Peternakan",
    "Jasa Pertanian dan Perburuan", "Kehutanan dan Penebangan Kayu", "Perikanan",
    "Pertambangan Minyak dan Gas Bumi", "Pertambangan Batubara dan Lignit",
    "Pertambangan Bijih Logam", "Pertambangan dan Penggalian Lainnya",
    "Industri Makanan dan Minuman", "Pengolahan Tembakau",
    "Industri Tekstil dan Pakaian Jadi", "Industri Kulit, Barang dari Kulit dan Alas Kaki",
    "Industri Kayu, Barang dari Kayu dan Gabus", "Industri Kertas dan Percetakan",
    "Industri Kimia, Farmasi dan Obat Tradisional", "Industri Karet, Barang dari Karet dan Plastik",
    "Industri Barang Galian bukan Logam", "Industri Logam Dasar",
    "Industri Barang dari Logam, Komputer, Elektronik", "Industri Alat Angkutan", "Industri Furnitur",
    "Ketenagalistrikan", "Pengadaan Gas dan Produksi Es", "Pengadaan Air", "Konstruksi",
    "Perdagangan Mobil, Sepeda Motor dan Reparasinya", "Perdagangan Besar dan Eceran",
    "Angkutan Rel", "Angkutan Darat", "Angkutan Laut", "Angkutan Udara",
    "Pergudangan dan Jasa Penunjang Angkutan", "Penyediaan Akomodasi", "Penyediaan Makan Minum",
    "Informasi dan Komunikasi", "Jasa Perantara Keuangan", "Asuransi dan Dana Pensiun",
    "Jasa Keuangan Lainnya", "Real Estate", "Jasa Perusahaan",
    "Administrasi Pemerintahan dan Jaminan Sosial", "Jasa Pendidikan",
    "Jasa Kesehatan dan Kegiatan Sosial", "Jasa Lainnya", "PRODUK DOMESTIK BRUTO"
]

# ─── Helper: konversi nilai AI ke string aman ─────────────────────────────────
def _ke_str(nilai) -> str:
    """Konversi hasil AI (bisa dict/list/str) ke string yang aman untuk text_area."""
    if isinstance(nilai, (dict, list)):
        return json.dumps(nilai, ensure_ascii=False, indent=2)
    return str(nilai) if nilai else ""

def _buat_excel_ekstraksi(json_final: dict) -> bytes:
    """
    Membuat file Excel terformat rapi dari hasil 12 variabel ekstraksi fenomena BPS.
    Return: bytes untuk di-download.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Ekstraksi Fenomena"

    # ─── Style ────────────────────────────────────────────────────────────────
    header_fill   = PatternFill("solid", fgColor="003366")   # Biru tua BPS
    header_font   = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
    subheader_fill = PatternFill("solid", fgColor="DDEEFF")   # Biru muda
    subheader_font = Font(name="Calibri", bold=True, color="003366", size=10)
    isi_font      = Font(name="Calibri", size=10)
    border_tipis  = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin")
    )
    wrap_align    = Alignment(wrap_text=True, vertical="top")
    center_align  = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # ─── Baris 1: Header Judul ─────────────────────────────────────────────────
    ws.merge_cells("A1:C1")
    ws["A1"] = "FORMULIR EKSTRAKSI FENOMENA EKONOMI — BPS KOTA MAGELANG"
    ws["A1"].font = Font(name="Calibri", bold=True, color="FFFFFF", size=13)
    ws["A1"].fill = header_fill
    ws["A1"].alignment = center_align
    ws.row_dimensions[1].height = 30

    # ─── Baris 2: Info Waktu ───────────────────────────────────────────────────
    ws.merge_cells("A2:C2")
    ws["A2"] = f"Diekstrak pada: {json_final.get('_waktu_ekstraksi', '')}  |  URL: {json_final.get('_url_sumber', '')}"
    ws["A2"].font = Font(name="Calibri", italic=True, size=9, color="555555")
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[2].height = 20

    # ─── Baris 3: Kosong ──────────────────────────────────────────────────────
    ws.row_dimensions[3].height = 8

    # ─── Header Kolom Tabel ───────────────────────────────────────────────────
    headers = ["No.", "Variabel BPS", "Hasil Ekstraksi (Bisa Diedit)"]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.font   = subheader_font
        cell.fill   = subheader_fill
        cell.border = border_tipis
        cell.alignment = center_align
    ws.row_dimensions[4].height = 22

    # ─── Isi 12 Variabel ──────────────────────────────────────────────────────
    LABEL_MAP = [
        ("tema_topik",            "1. Tema / Topik"),
        ("judul_dan_tanggal",     "2. Judul & Tanggal Terbit"),
        ("sumber_dan_link",       "3. Sumber & Link Media"),
        ("ringkasan_fenomena",    "4. Ringkasan Fenomena"),
        ("data_angka",            "5. Data Angka Kuantitatif"),
        ("kutipan_tokoh",         "6. Kutipan Tokoh / Narasumber"),
        ("lokasi_spesifik",       "7. Lokasi Spesifik"),
        ("intervensi_pemerintah", "8. Intervensi Pemerintah"),
        ("periode_kejadian",      "9. Periode Kejadian"),
        ("kata_kunci",            "10. Kata Kunci / Hashtag"),
        ("sentimen_dampak",       "11. Sentimen Dampak"),
        ("kategori_perbandingan", "12. Kategori Perbandingan"),
    ]

    # Warna selang-seling untuk kemudahan baca
    warna_ganjil = PatternFill("solid", fgColor="F7FAFF")
    warna_genap  = PatternFill("solid", fgColor="FFFFFF")

    for i, (key, label) in enumerate(LABEL_MAP):
        row = i + 5
        nilai = json_final.get(key, "")
        if isinstance(nilai, (dict, list)):
            nilai = json.dumps(nilai, ensure_ascii=False, indent=2)

        fill_baris = warna_ganjil if i % 2 == 0 else warna_genap

        # Kolom A: Nomor
        c_no = ws.cell(row=row, column=1, value=i+1)
        c_no.font      = Font(name="Calibri", size=10, bold=True)
        c_no.alignment = center_align
        c_no.border    = border_tipis
        c_no.fill      = fill_baris

        # Kolom B: Nama variabel
        c_var = ws.cell(row=row, column=2, value=label)
        c_var.font      = Font(name="Calibri", size=10, bold=True, color="003366")
        c_var.alignment = Alignment(vertical="top", wrap_text=True)
        c_var.border    = border_tipis
        c_var.fill      = fill_baris

        # Kolom C: Nilai (bisa diedit user di Excel)
        c_val = ws.cell(row=row, column=3, value=str(nilai))
        c_val.font      = isi_font
        c_val.alignment = wrap_align
        c_val.border    = border_tipis
        c_val.fill      = fill_baris

        # Atur tinggi baris — field panjang dapat lebih tinggi
        if key in ["ringkasan_fenomena", "kutipan_tokoh", "data_angka", "intervensi_pemerintah"]:
            ws.row_dimensions[row].height = 80
        else:
            ws.row_dimensions[row].height = 25

    # ─── Lebar Kolom ──────────────────────────────────────────────────────────
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 32
    ws.column_dimensions["C"].width = 75

    # ─── Freeze pane agar header selalu kelihatan saat scroll ─────────────────
    ws.freeze_panes = "A5"

    # ─── Simpan ke bytes ──────────────────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()

# ─── SESSION STATE ─────────────────────────────────────────────────────────────
for key, default in [
    ("target_url", ""),
    ("hasil_ekstraksi", None),
    ("ekstraksi_url_aktif", ""),
    ("tab_aktif", 0),
    ("json_final_siap", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    # Logo (aman jika file tidak ada)
    if os.path.exists("logo_bps_magelang.png"):
        st.image("logo_bps_magelang.png", use_container_width=True)
    
    st.markdown("## 📡 SI-FENO")
    st.markdown("**Sistem Informasi Fenomena Ekonomi**")
    st.markdown("BPS Kota Magelang")
    st.markdown("---")

    st.markdown("### 📅 Rentang Waktu Pencarian")
    default_end   = datetime.now()
    default_start = default_end - timedelta(days=90)
    tanggal_mulai   = st.date_input("Dari Tanggal", default_start)
    tanggal_selesai = st.date_input("Sampai Tanggal", default_end)

    if tanggal_mulai > tanggal_selesai:
        st.error("Tanggal mulai tidak boleh setelah tanggal selesai!")

    triwulan_berjalan = _hitung_triwulan(tanggal_mulai.strftime("%Y-%m-%d"))
    st.success(f"📌 Periode: **{triwulan_berjalan}**")

    st.markdown("### 🎛️ Pengaturan AI Radar")
    min_skor    = st.slider("Skor Minimum Lolos", 1, 10, 6,
                            help="Angka 6 = Cukup selektif. Turunkan jika berita sedikit.")
    paksa_ulang = st.toggle("🔄 Proses Ulang Artikel Lama", value=False,
                            help="Aktifkan untuk memaksa AI membaca ulang artikel yang sebelumnya ditolak.")
    scan_semua  = st.toggle("🌐 Scan Semua Level Wilayah", value=True,
                            help="Jika aktif, radar memindai hingga level Nasional meski sudah ada berita lokal.")

    st.markdown("---")
    st.markdown("### 🔑 Status API")
    for nama, key_val in [("Groq", KEYS["groq"]), ("Gemini", KEYS["gemini"]),
                           ("Cerebras", KEYS["cerebras"]), ("Mistral", KEYS["mistral"])]:
        status = "🟢 Terhubung" if key_val else "🔴 Belum diisi"
        st.caption(f"{nama}: {status}")

    st.markdown("---")
    st.caption("v2.0 | Dibuat untuk BPS Kota Magelang")

# ─── MAIN TABS ────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "📡 RADAR PDRB",
    "📝 EKSTRAKTOR FENOMENA",
    "📊 RIWAYAT & EKSPOR"
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: RADAR PDRB
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("## 📡 Radar Pencari Berita Fenomena PDRB")
    st.markdown("Temukan berita fenomena ekonomi secara otomatis dari seluruh internet, lalu kirim ke Ekstraktor.")

    # ── BAGIAN A: KONTROL SCAN ────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("#### 🚀 Jalankan Radar")
        col_kat, col_btn = st.columns([4, 1])
        with col_kat:
            pilihan_kategori = st.selectbox(
                "Target Kategori:",
                ["✨ SEMUA KATEGORI (BATCH SCAN)"] + DAFTAR_KATEGORI,
                label_visibility="collapsed"
            )
        with col_btn:
            btn_scan = st.button("▶ SCAN", type="primary", use_container_width=True)

        if btn_scan:
            if tanggal_mulai > tanggal_selesai:
                st.error("Perbaiki rentang tanggal di sidebar terlebih dahulu.")
            else:
                mulai_str   = tanggal_mulai.strftime("%Y-%m-%d")
                selesai_str = tanggal_selesai.strftime("%Y-%m-%d")

                if pilihan_kategori == "✨ SEMUA KATEGORI (BATCH SCAN)":
                    prog   = st.progress(0)
                    status = st.empty()

                    def cb_progress(kat, idx, total):
                        prog.progress(idx / total)
                        status.info(f"🔄 [{idx}/{total}] Memindai: **{kat}**...")

                    with st.spinner("Memulai Batch Scan — mohon tunggu..."):
                        hasil_batch = batch_scan_semua_kategori(
                            DAFTAR_KATEGORI, mulai_str, selesai_str,
                            min_skor=min_skor, paksa_proses_ulang=paksa_ulang,
                            callback_progress=cb_progress
                        )
                    prog.empty(); status.empty()
                    r = hasil_batch["ringkasan"]
                    st.success(f"✅ Batch Scan Selesai! Berita ditemukan di **{r['sukses']} kategori** ({r['persen_sukses']}%).")
                    time.sleep(1); st.rerun()

                else:
                    with st.spinner(f"📡 Memindai: **{pilihan_kategori}**..."):
                        hasil = scan_kategori(
                            pilihan_kategori, mulai_str, selesai_str,
                            min_skor=min_skor,
                            paksa_proses_ulang=paksa_ulang,
                            scan_semua_level=scan_semua,
                            aktifkan_fallback=True,
                        )
                    if hasil["status"] == "sukses":
                        st.success(f"✅ Ditemukan **{hasil['jumlah_valid']} artikel** valid dari {hasil['jumlah_valid']} level!")
                    else:
                        st.error(hasil.get("pesan_utama", "Tidak ada berita ditemukan."))
                        with st.expander("💡 Saran Keyword Manual"):
                            for kw in hasil.get("saran_keyword", []):
                                st.markdown(f"- `{kw}`")
                            st.markdown("**Coba cari di sumber berikut:**")
                            for s in hasil.get("saran_sumber", []):
                                st.markdown(f"- [{s}](https://{s})")
                    time.sleep(1); st.rerun()

    st.markdown("---")

    # ── BAGIAN B: DASHBOARD STATUS ────────────────────────────────────────────
    st.markdown("#### 📊 Status Kategori PDRB")
    semua_status = ambil_semua_status_kategori(triwulan_berjalan)

    if not semua_status:
        st.info("ℹ️ Belum ada data untuk triwulan ini. Jalankan Radar terlebih dahulu.")
    else:
        df = pd.DataFrame(semua_status)
        ada    = df[df["jumlah_artikel_valid"] > 0]
        kosong = df[df["jumlah_artikel_valid"] == 0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📋 Total Dipindai",  len(df))
        c2.metric("🟢 Ada Berita",       len(ada))
        c3.metric("🔴 Kosong/Buntu",     len(kosong))
        c4.metric("📈 Coverage",         f"{round(len(ada)/len(df)*100)}%" if len(df) else "0%")

        col_ada, col_buntu = st.columns(2)
        with col_ada:
            st.markdown("**✅ Kategori dengan Berita**")
            if not ada.empty:
                st.dataframe(
                    ada[["kategori_pdrb", "jumlah_artikel_valid", "terakhir_scan"]]
                    .rename(columns={"kategori_pdrb": "Kategori",
                                     "jumlah_artikel_valid": "Artikel",
                                     "terakhir_scan": "Terakhir Scan"}),
                    use_container_width=True, hide_index=True
                )
        with col_buntu:
            st.markdown("**⚠️ Kategori Butuh Perhatian**")
            if not kosong.empty:
                st.dataframe(
                    kosong[["kategori_pdrb", "terakhir_scan"]]
                    .rename(columns={"kategori_pdrb": "Kategori",
                                     "terakhir_scan": "Terakhir Scan"}),
                    use_container_width=True, hide_index=True
                )

    st.markdown("---")

    # ── BAGIAN C: ANTREAN ARTIKEL ─────────────────────────────────────────────
    st.markdown("#### 📥 Antrean Artikel Siap Ekstrak")

    col_filter, col_input_manual = st.columns([2, 2])
    with col_filter:
        kat_antrean = st.selectbox(
            "Tampilkan antrean dari kategori:",
            ["— Pilih Kategori —"] + DAFTAR_KATEGORI
        )
    with col_input_manual:
        st.markdown("**📎 Atau input URL manual (dari ChatGPT/Gemini/Claude):**")
        url_manual = st.text_input("URL Berita Manual:", placeholder="https://...", label_visibility="collapsed")
        if st.button("📤 Kirim ke Ekstraktor", use_container_width=True) and url_manual:
            st.session_state.target_url = url_manual
            st.toast("URL dikirim ke Tab Ekstraktor!", icon="✅")

    if kat_antrean != "— Pilih Kategori —":
        artikel_db = ambil_artikel_valid(kat_antrean, triwulan_berjalan)

        if not artikel_db:
            st.info("🎉 Kosong! Semua artikel sudah diekstrak atau belum ada scan baru.")
        else:
            st.markdown(f"**{len(artikel_db)} artikel menunggu ekstraksi:**")
            for art in artikel_db:
                skor  = art["skor_relevansi"]
                badge = "badge-skor-hijau" if skor >= 8 else "badge-skor-kuning"
                label = "🟢" if skor >= 8 else "🟡"

                with st.container():
                    st.markdown(f"""
                    <div class="kartu-artikel">
                        <b>{art['judul_berita']}</b><br>
                        <small style="color:#666">🔗 {art['url_berita']}</small><br><br>
                        <span class="{badge}">{label} Skor AI: {skor}/10</span>
                        &nbsp; {'✅ Ada Angka' if art['ada_data_angka'] else '❌ Tanpa Angka'}
                        &nbsp; {'✅ Ada Perbandingan' if art['ada_perbandingan'] else '❌ Tanpa Perbandingan'}
                        <div class="alasan-box">💬 {art['alasan_ai']}</div>
                    </div>
                    """, unsafe_allow_html=True)

                    ca, cb, cc = st.columns([2, 2, 8])
                    with ca:
                        if st.button("🚀 Kirim ke Ekstraktor", key=f"eks_{art['id']}", type="primary"):
                            st.session_state.target_url = art["url_berita"]
                            st.toast("URL dikirim ke Tab Ekstraktor!", icon="🚀")
                    with cb:
                        if st.button("❌ Tolak", key=f"tolak_{art['id']}"):
                            tandai_artikel_ditolak(art["url_berita"])
                            st.toast("Artikel ditolak.", icon="🗑️")
                            time.sleep(0.5); st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: EKSTRAKTOR FENOMENA
# ═══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("## 📝 Meja Ekstraksi Fenomena BPS")
    st.markdown("AI akan membedah isi artikel dan menarik 12 variabel standar BPS. Anda bisa mengedit hasilnya.")

    # ── INPUT URL ────────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("#### 1️⃣ Masukkan URL Berita")
        url_input = st.text_input(
            "URL Berita:",
            value=st.session_state.target_url,
            placeholder="Tempel link berita di sini...",
            label_visibility="collapsed"
        )
        btn_ekstrak = st.button("🤖 MULAI EKSTRAK", type="primary", use_container_width=True)

    if btn_ekstrak:
        if not url_input.strip():
            st.error("URL tidak boleh kosong!")
        elif not any(KEYS.values()):
            st.error("Tidak ada API Key yang terisi! Tambahkan di file `.env` atau Hugging Face Secrets.")
        else:
            st.session_state.ekstraksi_url_aktif = url_input.strip()
            st.session_state.hasil_ekstraksi     = None  # Reset hasil lama

            col_step1, col_step2 = st.columns(2)

            # STEP 1: Scraping
            with col_step1:
                with st.spinner("🕷️ Sedang membaca halaman web..."):
                    hasil_scrape = scrape_berita(url_input.strip())

                if hasil_scrape["status"] == "error":
                    st.error(f"Scraping Gagal: {hasil_scrape['pesan']}")
                    st.stop()
                else:
                    st.success(f"✅ Terbaca via: **{hasil_scrape['metode']}**")
                    st.caption(f"Judul: {hasil_scrape['judul'][:80]}")
                    st.caption(f"Panjang teks: {len(hasil_scrape['teks'])} karakter")

            # STEP 2: AI Extraction
            with col_step2:
                with st.spinner("🧠 AI sedang menganalisis 12 variabel BPS..."):
                    hasil_ai = ekstrak_fenomena_ai(KEYS, hasil_scrape)

                if hasil_ai["status"] == "error":
                    st.error(f"Ekstraksi AI Gagal: {hasil_ai['pesan']}")
                    st.stop()
                else:
                    model_pakai = hasil_ai["data"].get("_model_digunakan", "AI")
                    st.success(f"✅ Diekstrak oleh: **{model_pakai}**")
                    st.session_state.hasil_ekstraksi = hasil_ai["data"]

    # ── EDITOR HASIL (HUMAN-IN-THE-LOOP) ─────────────────────────────────────
    st.markdown("---")
    if st.session_state.hasil_ekstraksi is not None:
        data = st.session_state.hasil_ekstraksi

        st.markdown(f"#### 2️⃣ Validasi & Edit Hasil AI")
        st.info(f"🧠 Diproses oleh: **{data.get('_model_digunakan', 'AI')}** — Periksa dan edit jika ada yang kurang tepat.")

        with st.form("form_finalisasi"):
            col1, col2 = st.columns(2)

            with col1:
                tema      = st.text_input("1. Tema Topik",
                                          value=_ke_str(data.get("tema_topik", "")))
                judul_tgl = st.text_input("2. Judul & Tanggal Terbit",
                                          value=_ke_str(data.get("judul_dan_tanggal", "")))
                sumber    = st.text_input("3. Sumber & Link Media",
                                          value=_ke_str(data.get("sumber_dan_link", "")))
                lokasi    = st.text_input("7. Lokasi Spesifik",
                                          value=_ke_str(data.get("lokasi_spesifik", "")))
                periode   = st.text_input("9. Periode Kejadian",
                                          value=_ke_str(data.get("periode_kejadian", "")))
                kata_kunci = st.text_input("10. Kata Kunci / Hashtag",
                                           value=_ke_str(data.get("kata_kunci", "")))

            with col2:
                angka       = st.text_area("5. Data Angka Kuantitatif",
                                           value=_ke_str(data.get("data_angka", "")), height=120)
                intervensi  = st.text_area("8. Intervensi Pemerintah",
                                           value=_ke_str(data.get("intervensi_pemerintah", "")), height=120)
                sentimen    = st.selectbox(
                    "11. Sentimen Dampak",
                    ["Positif", "Negatif", "Netral"],
                    index=["Positif", "Negatif", "Netral"].index(
                        data.get("sentimen_dampak", "Netral")
                    ) if data.get("sentimen_dampak") in ["Positif", "Negatif", "Netral"] else 2
                )
                perbandingan = st.selectbox(
                    "12. Jenis Perbandingan",
                    ["y-on-y", "q-to-q", "harga", "Tidak ada informasi"],
                    index=["y-on-y", "q-to-q", "harga", "Tidak ada informasi"].index(
                        data.get("kategori_perbandingan", "Tidak ada informasi")
                    ) if data.get("kategori_perbandingan") in ["y-on-y", "q-to-q", "harga", "Tidak ada informasi"] else 3
                )

            ringkasan = st.text_area("4. Ringkasan Fenomena (4-5 Kalimat)",
                                     value=_ke_str(data.get("ringkasan_fenomena", "")), height=160)
            kutipan   = st.text_area("6. Kutipan Tokoh & Narasumber",
                                     value=_ke_str(data.get("kutipan_tokoh", "")), height=130)

            st.markdown("---")
            submit = st.form_submit_button("✅ FINALISASI & TANDAI SELESAI",
                                           type="primary", use_container_width=True)

            if submit:
                tandai_artikel_diekstrak(st.session_state.ekstraksi_url_aktif)
                st.session_state.json_final_siap = {
                    "tema_topik"           : tema,
                    "judul_dan_tanggal"    : judul_tgl,
                    "sumber_dan_link"      : sumber,
                    "ringkasan_fenomena"   : ringkasan,
                    "data_angka"           : angka,
                    "kutipan_tokoh"        : kutipan,
                    "lokasi_spesifik"      : lokasi,
                    "intervensi_pemerintah": intervensi,
                    "periode_kejadian"     : periode,
                    "kata_kunci"           : kata_kunci,
                    "sentimen_dampak"      : sentimen,
                    "kategori_perbandingan": perbandingan,
                    "_url_sumber"          : st.session_state.ekstraksi_url_aktif,
                    "_waktu_ekstraksi"     : datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
                st.session_state.target_url      = ""
                st.session_state.hasil_ekstraksi = None
                st.success("🎉 Berhasil difinalisasi! Lihat tombol download di bawah.")

                # ── DOWNLOAD BUTTONS — DI LUAR FORM (WAJIB di sini, tidak boleh di dalam form) ──
    if st.session_state.json_final_siap:
        jf = st.session_state.json_final_siap
        st.markdown("#### 📤 Unduh Hasil Ekstraksi")

        col_dl1, col_dl2, col_dl3 = st.columns(3)
        ts = datetime.now().strftime('%Y%m%d_%H%M')

        with col_dl1:
            st.download_button(
                "⬇️ Download Excel (.xlsx)",
                data=_buat_excel_ekstraksi(jf),
                file_name=f"sifeno_{ts}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True, type="primary",
                key="dl_xlsx"
            )
            st.caption("📊 Excel — siap cetak & edit")

        with col_dl2:
            LABEL_MAP_DL = [
                ("tema_topik","Tema Topik"),("judul_dan_tanggal","Judul & Tanggal"),
                ("sumber_dan_link","Sumber & Link"),("ringkasan_fenomena","Ringkasan Fenomena"),
                ("data_angka","Data Angka"),("kutipan_tokoh","Kutipan Tokoh"),
                ("lokasi_spesifik","Lokasi Spesifik"),("intervensi_pemerintah","Intervensi Pemerintah"),
                ("periode_kejadian","Periode Kejadian"),("kata_kunci","Kata Kunci"),
                ("sentimen_dampak","Sentimen Dampak"),("kategori_perbandingan","Kategori Perbandingan"),
            ]
            df_csv = pd.DataFrame([{"Variabel": lbl, "Nilai": jf.get(k,"")} for k, lbl in LABEL_MAP_DL])
            csv_buf = io.StringIO()
            df_csv.to_csv(csv_buf, index=False)
            st.download_button(
                "⬇️ Download CSV",
                data=csv_buf.getvalue(),
                file_name=f"sifeno_{ts}.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_csv"
            )
            st.caption("📄 CSV — untuk import data")

        with col_dl3:
            st.download_button(
                "⬇️ Download JSON",
                data=json.dumps(jf, indent=4, ensure_ascii=False).encode("utf-8"),
                file_name=f"sifeno_{ts}.json",
                mime="application/json",
                use_container_width=True,
                key="dl_json"
            )
            st.caption("🗂️ JSON — arsip digital")

        # Preview hasil
        with st.expander("👁️ Preview Hasil Akhir", expanded=True):
            df_preview = pd.DataFrame([
                {"No": i+1, "Variabel BPS": lbl, "Hasil Ekstraksi": jf.get(k,"")}
                for i, (k, lbl) in enumerate(LABEL_MAP_DL)
            ])
            st.dataframe(df_preview, use_container_width=True, hide_index=True,
                         column_config={"Hasil Ekstraksi": st.column_config.TextColumn(width="large")})

        if st.button("🔄 Ekstrak Artikel Baru"):
            st.session_state.json_final_siap = None
            st.rerun()
    else:
        st.info("👆 Masukkan URL dan klik **Mulai Ekstrak** untuk memulai.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: RIWAYAT & EKSPOR
# ═══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("## 📊 Riwayat Ekstraksi & Ekspor Data")

    from radar.database import get_connection
    try:
        conn = get_connection()
        df_riwayat = pd.read_sql_query("""
            SELECT
                judul_berita     AS "Judul Berita",
                kategori_pdrb    AS "Kategori PDRB",
                triwulan         AS "Triwulan",
                skor_relevansi   AS "Skor AI",
                status           AS "Status",
                tanggal_ditemukan AS "Ditemukan",
                tanggal_diekstrak AS "Diekstrak",
                url_berita       AS "URL"
            FROM riwayat_artikel
            ORDER BY tanggal_ditemukan DESC
        """, conn)
        conn.close()
    except Exception:
        df_riwayat = pd.DataFrame()

    if df_riwayat.empty:
        st.info("Belum ada riwayat artikel di database.")
    else:
        # Filter
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            filter_status = st.multiselect(
                "Filter Status:",
                ["ditemukan", "diekstrak", "tidak_lolos", "ditolak_user"],
                default=["ditemukan", "diekstrak"]
            )
        with col_f2:
            filter_tw = st.multiselect(
                "Filter Triwulan:",
                df_riwayat["Triwulan"].unique().tolist() if not df_riwayat.empty else [],
                default=df_riwayat["Triwulan"].unique().tolist()[:1] if not df_riwayat.empty else []
            )
        with col_f3:
            filter_kat = st.multiselect(
                "Filter Kategori:",
                df_riwayat["Kategori PDRB"].unique().tolist() if not df_riwayat.empty else []
            )

        df_tampil = df_riwayat.copy()
        if filter_status:
            df_tampil = df_tampil[df_tampil["Status"].isin(filter_status)]
        if filter_tw:
            df_tampil = df_tampil[df_tampil["Triwulan"].isin(filter_tw)]
        if filter_kat:
            df_tampil = df_tampil[df_tampil["Kategori PDRB"].isin(filter_kat)]

        st.markdown(f"**Menampilkan {len(df_tampil)} dari {len(df_riwayat)} total entri**")
        st.dataframe(df_tampil.drop(columns=["URL"]), use_container_width=True, hide_index=True)

        # Ekspor
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            csv_exp = df_tampil.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Download CSV",
                               data=csv_exp,
                               file_name=f"sifeno_riwayat_{datetime.now().strftime('%Y%m%d')}.csv",
                               mime="text/csv", use_container_width=True)
        with col_e2:
            json_exp = df_tampil.to_json(orient="records", force_ascii=False, indent=2)
            st.download_button("⬇️ Download JSON",
                               data=json_exp.encode("utf-8"),
                               file_name=f"sifeno_riwayat_{datetime.now().strftime('%Y%m%d')}.json",
                               mime="application/json", use_container_width=True)