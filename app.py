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

# CSS Custom yang Diperbaiki (Support Dark Mode / Light Mode otomatis)
st.markdown("""
<style>
.kartu-artikel {
    border: 1px solid rgba(130, 130, 130, 0.2);
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 12px;
    background-color: rgba(130, 130, 130, 0.05);
}
.kartu-artikel a { color: #4a6cf7 !important; word-break: break-all; text-decoration: none; }
.kartu-artikel a:hover { text-decoration: underline; }
.badge-skor-hijau {
    background-color: rgba(40, 167, 69, 0.2); color: #28a745;
    padding: 4px 10px; border-radius: 20px; font-weight: bold; font-size: 13px;
}
.badge-skor-kuning {
    background-color: rgba(255, 193, 7, 0.2); color: #d39e00;
    padding: 4px 10px; border-radius: 20px; font-weight: bold; font-size: 13px;
}
.alasan-box {
    background-color: rgba(74, 108, 247, 0.1);
    border-left: 4px solid #4a6cf7;
    padding: 10px 14px; border-radius: 4px; font-size: 14px; margin-top: 8px;
}
</style>
""", unsafe_allow_html=True)

inisialisasi_database()
load_dotenv()

# ─── MENGAMBIL API KEYS (MENDUKUNG FORMAT JAMAK / POOLING) ───────────────────
# Prioritaskan mengambil yang ada huruf "S" nya (cth: GROQ_API_KEYS)
KEYS = {
    "groq"    : os.environ.get("GROQ_API_KEYS", os.environ.get("GROQ_API_KEY", "")),
    "gemini"  : os.environ.get("GEMINI_API_KEYS", os.environ.get("GEMINI_API_KEY", "")),
    "cerebras": os.environ.get("CEREBRAS_API_KEYS", os.environ.get("CEREBRAS_API_KEY", "")),
    "mistral" : os.environ.get("MISTRAL_API_KEYS", os.environ.get("MISTRAL_API_KEY", "")),
}

# Fungsi kecil untuk menghitung ada berapa kunci di dalam 1 string yang dipisah koma
def _hitung_kunci(raw_keys: str) -> int:
    return len([k for k in raw_keys.split(",") if k.strip()])

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
    if isinstance(nilai, (dict, list)):
        return json.dumps(nilai, ensure_ascii=False, indent=2)
    return str(nilai) if nilai else ""

def _buat_excel_ekstraksi(json_final: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Ekstraksi Fenomena"
    header_fill   = PatternFill("solid", fgColor="003366")   
    header_font   = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
    subheader_fill = PatternFill("solid", fgColor="DDEEFF")   
    subheader_font = Font(name="Calibri", bold=True, color="003366", size=10)
    isi_font      = Font(name="Calibri", size=10)
    border_tipis  = Border(left=Side(style="thin"), right=Side(style="thin"), top=Side(style="thin"), bottom=Side(style="thin"))
    wrap_align    = Alignment(wrap_text=True, vertical="top")
    center_align  = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.merge_cells("A1:C1")
    ws["A1"] = "FORMULIR EKSTRAKSI FENOMENA EKONOMI — BPS KOTA MAGELANG"
    ws["A1"].font = Font(name="Calibri", bold=True, color="FFFFFF", size=13)
    ws["A1"].fill = header_fill
    ws["A1"].alignment = center_align
    ws.row_dimensions[1].height = 30

    ws.merge_cells("A2:C2")
    ws["A2"] = f"Diekstrak pada: {json_final.get('_waktu_ekstraksi', '')}  |  URL: {json_final.get('_url_sumber', '')}"
    ws["A2"].font = Font(name="Calibri", italic=True, size=9, color="555555")
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[2].height = 20
    ws.row_dimensions[3].height = 8

    headers = ["No.", "Variabel BPS", "Hasil Ekstraksi (Bisa Diedit)"]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.font = subheader_font; cell.fill = subheader_fill; cell.border = border_tipis; cell.alignment = center_align
    ws.row_dimensions[4].height = 22

    LABEL_MAP = [
        ("tema_topik", "1. Tema / Topik"), ("judul_dan_tanggal", "2. Judul & Tanggal Terbit"),
        ("sumber_dan_link", "3. Sumber & Link Media"), ("ringkasan_fenomena", "4. Ringkasan Fenomena"),
        ("data_angka", "5. Data Angka Kuantitatif"), ("kutipan_tokoh", "6. Kutipan Tokoh / Narasumber"),
        ("lokasi_spesifik", "7. Lokasi Spesifik"), ("intervensi_pemerintah", "8. Intervensi Pemerintah"),
        ("periode_kejadian", "9. Periode Kejadian"), ("kata_kunci", "10. Kata Kunci / Hashtag"),
        ("sentimen_dampak", "11. Sentimen Dampak"), ("kategori_perbandingan", "12. Kategori Perbandingan"),
    ]
    warna_ganjil = PatternFill("solid", fgColor="F7FAFF"); warna_genap = PatternFill("solid", fgColor="FFFFFF")

    for i, (key, label) in enumerate(LABEL_MAP):
        row = i + 5
        nilai = json_final.get(key, "")
        if isinstance(nilai, (dict, list)): nilai = json.dumps(nilai, ensure_ascii=False, indent=2)
        fill_baris = warna_ganjil if i % 2 == 0 else warna_genap

        c_no = ws.cell(row=row, column=1, value=i+1); c_no.font = Font(name="Calibri", size=10, bold=True); c_no.alignment = center_align; c_no.border = border_tipis; c_no.fill = fill_baris
        c_var = ws.cell(row=row, column=2, value=label); c_var.font = Font(name="Calibri", size=10, bold=True, color="003366"); c_var.alignment = Alignment(vertical="top", wrap_text=True); c_var.border = border_tipis; c_var.fill = fill_baris
        c_val = ws.cell(row=row, column=3, value=str(nilai)); c_val.font = isi_font; c_val.alignment = wrap_align; c_val.border = border_tipis; c_val.fill = fill_baris

        if key in ["ringkasan_fenomena", "kutipan_tokoh", "data_angka", "intervensi_pemerintah"]: ws.row_dimensions[row].height = 80
        else: ws.row_dimensions[row].height = 25

    ws.column_dimensions["A"].width = 6; ws.column_dimensions["B"].width = 32; ws.column_dimensions["C"].width = 75
    ws.freeze_panes = "A5"
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return buf.getvalue()

# ─── SESSION STATE ────────────────────────────────────────────────────────────
for key, default in [
    ("target_url", ""),
    ("hasil_ekstraksi", None),
    ("ekstraksi_url_aktif", ""),
    ("json_final_siap", None),
    ("kategori_terpilih_antrean", "— Pilih Kategori —") 
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    if os.path.exists("logo_bps_magelang.png"):
        st.image("logo_bps_magelang.png", use_container_width=True)
    
    st.markdown("## 📡 SI-FENO")
    st.markdown("**Sistem Informasi Fenomena Ekonomi**")
    st.markdown("BPS Kota Magelang")
    st.markdown("---")

    st.markdown("### 📅 Rentang Waktu Pencarian")
    default_end   = datetime.now()
    default_start = default_end - timedelta(days=90)
    tanggal_mulai   = st.date_input("Dari Tanggal", default_start, help="Batas awal berita diterbitkan.")
    tanggal_selesai = st.date_input("Sampai Tanggal", default_end, help="Batas akhir berita diterbitkan.")

    if tanggal_mulai > tanggal_selesai:
        st.error("Tanggal mulai tidak boleh setelah tanggal selesai!")

    triwulan_berjalan = _hitung_triwulan(tanggal_mulai.strftime("%Y-%m-%d"))
    st.success(f"📌 Periode: **{triwulan_berjalan}**")

    st.markdown("### 🎛️ Pengaturan AI Radar")
    min_skor    = st.slider("Skor Minimum Lolos", 1, 10, 6,
                            help="Filter seberapa ketat AI menyeleksi berita. Angka 6 disarankan untuk membuang berita opini tanpa angka.")
    paksa_ulang = st.toggle("🔄 Proses Ulang Artikel Lama", value=False,
                            help="PENTING: Jika diaktifkan, Radar akan men-scan ulang berita yang di masa lalu pernah ditolak atau gagal. Matikan untuk menghemat kuota AI.")
    scan_semua  = st.toggle("🌐 Scan Semua Level Wilayah", value=True,
                            help="Jika dinonaktifkan, AI akan berhenti mencari jika di level Kota/Kabupaten sudah menemukan minimal 3 berita.")

    st.markdown("---")
    st.markdown("### 🚦 Status Pasukan AI (Pool)")
    st.caption("Aplikasi ini menggunakan sistem Load Balancing. AI akan otomatis berganti kunci jika terjadi limit.")
    for nama, key_val in [("Groq", KEYS["groq"]), ("Cerebras", KEYS["cerebras"]), 
                           ("Gemini", KEYS["gemini"]), ("Mistral", KEYS["mistral"])]:
        jumlah = _hitung_kunci(key_val)
        status = f"🟢 {jumlah} Amunisi Siap" if jumlah > 0 else "🔴 Kosong"
        st.caption(f"**{nama}:** {status}")

# ─── MAIN TABS ────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "📡 RADAR BERITA",
    "📝 EKSTRAKTOR FENOMENA",
    "📊 HISTORY & EKSPOR"
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: RADAR PDRB
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:
    with st.expander("📖 Panduan Penggunaan Tab Radar", expanded=False):
        st.markdown("""
        **Fungsi Tab Ini:** Tempat Anda memantau dan memburu berita fenomena ekonomi secara otomatis dari internet.
        1. **Jalankan Radar:** Pilih salah satu kategori, lalu klik tombol **▶ SCAN**. Mesin akan mencari berita, lalu AI akan menyaring berita yang tidak relevan.
        2. **Status Kategori PDRB:** Menampilkan ringkasan kategori mana yang sudah punya berita (Aman) dan mana yang kosong (Buntu).
        3. **Antrean Artikel:** Setelah scan selesai, berita yang lolos akan muncul di sini. Klik **🚀 Kirim ke Ekstraktor** untuk membedah artikel tersebut di Tab 2.
        """)

    st.markdown("## 📡 Radar Pencari Berita Fenomena")

    with st.container(border=True):
        st.markdown("#### 🚀 Jalankan Radar")
        col_kat, col_btn = st.columns([4, 1])
        with col_kat:
            pilihan_kategori = st.selectbox(
                "Target Kategori:",
                ["✨ SEMUA KATEGORI (BATCH SCAN)"] + DAFTAR_KATEGORI,
                label_visibility="collapsed",
                help="Pilih 1 kategori untuk discan cepat, atau pilih BATCH SCAN untuk memproses 47 kategori sekaligus secara otomatis."
            )
        with col_btn:
            btn_scan = st.button("▶ SCAN", type="primary", use_container_width=True, help="Mulai pencarian dan filter AI.")

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

                    with st.spinner("Memulai Batch Scan — mohon tunggu, Anda bisa minum kopi dulu ☕..."):
                        hasil_batch = batch_scan_semua_kategori(
                            DAFTAR_KATEGORI, mulai_str, selesai_str,
                            min_skor=min_skor, paksa_proses_ulang=paksa_ulang,
                            callback_progress=cb_progress
                        )
                    prog.empty(); status.empty()
                    r = hasil_batch["ringkasan"]
                    st.success(f"✅ Batch Scan Selesai! Berita ditemukan di **{r['sukses']} kategori** ({r['persen_sukses']}%). Silakan cek tabel antrean di bawah.")
                    time.sleep(2); st.rerun()

                else:
                    with st.spinner(f"📡 Radar memindai: **{pilihan_kategori}**... Membutuhkan waktu sekitar 1-2 menit..."):
                        hasil = scan_kategori(
                            pilihan_kategori, mulai_str, selesai_str,
                            min_skor=min_skor,
                            paksa_proses_ulang=paksa_ulang,
                            scan_semua_level=scan_semua,
                            aktifkan_fallback=True,
                        )
                    if hasil["status"] == "sukses":
                        st.success(f"✅ Ditemukan **{hasil['jumlah_valid']} artikel** valid! Mengarahkan ke antrean...")
                        st.session_state.kategori_terpilih_antrean = pilihan_kategori 
                    else:
                        st.error(hasil.get("pesan_utama", "Tidak ada berita ditemukan."))
                        with st.expander("💡 Saran Keyword Manual dari AI"):
                            for kw in hasil.get("saran_keyword", []): st.markdown(f"- `{kw}`")
                            st.markdown("**Coba cari manual di sumber berikut:**")
                            for s in hasil.get("saran_sumber", []): st.markdown(f"- [{s}](https://{s})")
                    time.sleep(1.5); st.rerun()

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
        c1.metric("📋 Total Dipindai",  len(df), help="Jumlah total kategori PDRB yang sudah pernah di-scan oleh Radar pada triwulan ini.")
        c2.metric("🟢 Ada Berita",       len(ada), help="Kategori yang sudah memiliki minimal 1 artikel berita di database.")
        c3.metric("🔴 Kosong/Buntu",     len(kosong), help="Kategori yang belum ditemukan beritanya sama sekali (AI menyerah).")
        c4.metric("📈 Coverage",         f"{round(len(ada)/len(df)*100)}%" if len(df) else "0%", help="Persentase kelengkapan fenomena BPS Anda untuk triwulan ini.")

        col_ada, col_buntu = st.columns(2)
        with col_ada:
            st.markdown("**✅ Kategori dengan Berita**")
            if not ada.empty:
                st.dataframe(
                    ada[["kategori_pdrb", "jumlah_artikel_valid", "terakhir_scan"]]
                    .rename(columns={"kategori_pdrb": "Kategori", "jumlah_artikel_valid": "Artikel", "terakhir_scan": "Terakhir Scan"}),
                    use_container_width=True, hide_index=True
                )
        with col_buntu:
            st.markdown("**⚠️ Kategori Butuh Perhatian**")
            if not kosong.empty:
                st.dataframe(
                    kosong[["kategori_pdrb", "terakhir_scan"]]
                    .rename(columns={"kategori_pdrb": "Kategori", "terakhir_scan": "Terakhir Scan"}),
                    use_container_width=True, hide_index=True
                )

    st.markdown("---")

    # ── BAGIAN C: ANTREAN ARTIKEL ─────────────────────────────────────────────
    st.markdown("#### 📥 Antrean Artikel Siap Ekstrak", help="Daftar berita hasil Radar yang lolos seleksi dan siap dibedah oleh AI Ekstraktor.")

    col_filter, col_input_manual = st.columns([2, 2])
    with col_filter:
        opsi_antrean = ["— Pilih Kategori —"] + DAFTAR_KATEGORI
        index_terpilih = 0
        if st.session_state.kategori_terpilih_antrean in opsi_antrean:
            index_terpilih = opsi_antrean.index(st.session_state.kategori_terpilih_antrean)

        kat_antrean = st.selectbox(
            "Tampilkan antrean dari kategori:",
            opsi_antrean,
            index=index_terpilih,
            help="Pilih kategori untuk melihat berita-berita hasil radar yang tertangkap."
        )
        st.session_state.kategori_terpilih_antrean = kat_antrean

    with col_input_manual:
        st.markdown("**📎 Atau input URL manual (dari Google/Teman):**")
        url_manual = st.text_input("URL Berita Manual:", placeholder="https://...", label_visibility="collapsed")
        if st.button("📤 Kirim ke Ekstraktor Tab 2", use_container_width=True, help="Melewati antrean radar dan langsung mengirim link pilihan Anda ke meja Ekstraktor.") and url_manual:
            st.session_state.target_url = url_manual
            st.toast("URL berhasil dikirim! Silakan buka Tab 2 (Ekstraktor Fenomena).", icon="✅")

    if kat_antrean != "— Pilih Kategori —":
        artikel_db = ambil_artikel_valid(kat_antrean, triwulan_berjalan)

        if not artikel_db:
            st.info("🎉 Kosong! Semua artikel di kategori ini sudah diekstrak oleh staf BPS atau belum ada scan baru.")
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
                        <a href="{art['url_berita']}" target="_blank"><small>🔗 {art['url_berita']}</small></a><br><br>
                        <span class="{badge}">{label} Skor AI: {skor}/10</span>
                        &nbsp; {'✅ Ada Angka' if art['ada_data_angka'] else '❌ Tanpa Angka'}
                        &nbsp; {'✅ Ada Perbandingan' if art['ada_perbandingan'] else '❌ Tanpa Perbandingan'}
                        <div class="alasan-box">💬 {art['alasan_ai']}</div>
                    </div>
                    """, unsafe_allow_html=True)

                    ca, cb, cc = st.columns([2, 2, 8])
                    with ca:
                        if st.button("🚀 Ekstrak Berita Ini", key=f"eks_{art['id']}", type="primary", help="Membawa artikel ini ke Tab 2 untuk dibedah nilai statistiknya oleh AI."):
                            st.session_state.target_url = art["url_berita"]
                            st.toast("Berita dikirim! Silakan buka Tab Ekstraktor.", icon="🚀")
                    with cb:
                        if st.button("❌ Tolak (Hapus)", key=f"tolak_{art['id']}", help="Buang artikel ini dari antrean karena judulnya clickbait atau tidak relevan."):
                            tandai_artikel_ditolak(art["url_berita"])
                            st.toast("Artikel dibuang ke tempat sampah.", icon="🗑️")
                            time.sleep(0.5); st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: EKSTRAKTOR FENOMENA
# ═══════════════════════════════════════════════════════════════════════════════
with tab2:
    with st.expander("📖 Panduan Penggunaan Tab Ekstraktor", expanded=False):
        st.markdown("""
        **Fungsi Tab Ini:** Meja operasi AI untuk membedah artikel.
        1. **Mulai Ekstrak:** Tekan tombol untuk memerintahkan AI membaca artikel dan memecahnya menjadi 12 poin penting (Ringkasan, Data Angka, Kutipan, dll).
        2. **Human-in-the-Loop:** AI tidak selalu 100% sempurna. Anda **WAJIB** mengecek dan mengedit isi kotak jawaban jika ada kata yang salah sebelum difinalisasi.
        3. **Finalisasi:** Menekan tombol 'Finalisasi' akan menghapus artikel tersebut dari antrean Radar (Tab 1), sehingga rekan kerja Anda tidak akan mengerjakan berita yang sama dobel-dobel.
        """)

    st.markdown("## 📝 Meja Ekstraksi Fenomena BPS")

    with st.container(border=True):
        st.markdown("#### 1️⃣ Masukkan URL Berita")
        url_input = st.text_input(
            "URL Berita:",
            value=st.session_state.target_url,
            placeholder="Tempel link berita di sini...",
            label_visibility="collapsed"
        )
        btn_ekstrak = st.button("🤖 MULAI EKSTRAK", type="primary", use_container_width=True, help="AI akan mulai membaca artikel secara penuh.")

    if btn_ekstrak:
        if not url_input.strip():
            st.error("URL tidak boleh kosong!")
        elif not any(KEYS.values()):
            st.error("Tidak ada API Key yang terisi! Tambahkan di file `.env` atau Hugging Face Secrets.")
        else:
            st.session_state.ekstraksi_url_aktif = url_input.strip()
            st.session_state.hasil_ekstraksi     = None  
            st.session_state.json_final_siap     = None

            with st.status("⚙️ Menjalankan Mesin Ekstraksi Lapis 7...", expanded=True) as status_box:
                st.write("🕵️‍♂️ 1/2. Membaca situs web via Bypass Scraper...")
                hasil_scrape = scrape_berita(url_input.strip())

                if hasil_scrape["status"] == "error":
                    status_box.update(label="Scraping Gagal!", state="error")
                    st.error(f"Pesan: {hasil_scrape['pesan']}")
                    st.stop()
                else:
                    st.write(f"✅ Web terbaca via **{hasil_scrape['metode']}** ({len(hasil_scrape['teks'])} karakter).")
                    
                    st.write("🧠 2/2. AI Menganalisis 12 Variabel BPS... (Tunggu 10-20 Detik)")
                    hasil_ai = ekstrak_fenomena_ai(KEYS, hasil_scrape)

                    if hasil_ai["status"] == "error":
                        status_box.update(label="AI Tumbang / Limit Kuota!", state="error")
                        st.error(f"Pesan: {hasil_ai['pesan']}")
                        st.stop()
                    else:
                        model_pakai = hasil_ai["data"].get("_model_digunakan", "AI")
                        st.write(f"✅ Otak AI sukses memecah data menggunakan **{model_pakai}**.")
                        st.session_state.hasil_ekstraksi = hasil_ai["data"]
                        status_box.update(label="🎉 Ekstraksi Sukses!", state="complete")

    st.markdown("---")
    if st.session_state.hasil_ekstraksi is not None:
        data = st.session_state.hasil_ekstraksi

        st.markdown(f"#### 2️⃣ Validasi & Edit Hasil AI")
        st.info(f"🧠 AI yang bertugas: **{data.get('_model_digunakan', 'AI')}** — Ingat, AI bisa salah baca (Halusinasi). Silakan periksa dan ketik ulang jika ada yang kurang tepat.")

        with st.form("form_finalisasi"):
            col1, col2 = st.columns(2)

            with col1:
                tema      = st.text_input("1. Tema Topik", value=_ke_str(data.get("tema_topik", "")))
                judul_tgl = st.text_input("2. Judul & Tanggal Terbit", value=_ke_str(data.get("judul_dan_tanggal", "")))
                sumber    = st.text_input("3. Sumber & Link Media", value=_ke_str(data.get("sumber_dan_link", "")))
                lokasi    = st.text_input("7. Lokasi Spesifik", value=_ke_str(data.get("lokasi_spesifik", "")))
                periode   = st.text_input("9. Periode Kejadian", value=_ke_str(data.get("periode_kejadian", "")))
                kata_kunci = st.text_input("10. Kata Kunci / Hashtag", value=_ke_str(data.get("kata_kunci", "")))

            with col2:
                angka       = st.text_area("5. Data Angka Kuantitatif", value=_ke_str(data.get("data_angka", "")), height=120)
                intervensi  = st.text_area("8. Intervensi Pemerintah", value=_ke_str(data.get("intervensi_pemerintah", "")), height=120)
                sentimen    = st.selectbox(
                    "11. Sentimen Dampak", ["Positif", "Negatif", "Netral"],
                    index=["Positif", "Negatif", "Netral"].index(data.get("sentimen_dampak", "Netral")) if data.get("sentimen_dampak") in ["Positif", "Negatif", "Netral"] else 2
                )
                perbandingan = st.selectbox(
                    "12. Jenis Perbandingan", ["y-on-y", "q-to-q", "harga", "Tidak ada informasi"],
                    index=["y-on-y", "q-to-q", "harga", "Tidak ada informasi"].index(data.get("kategori_perbandingan", "Tidak ada informasi")) if data.get("kategori_perbandingan") in ["y-on-y", "q-to-q", "harga", "Tidak ada informasi"] else 3
                )

            ringkasan = st.text_area("4. Ringkasan Fenomena (4-5 Kalimat)", value=_ke_str(data.get("ringkasan_fenomena", "")), height=160)
            kutipan   = st.text_area("6. Kutipan Tokoh & Narasumber", value=_ke_str(data.get("kutipan_tokoh", "")), height=130)

            st.markdown("---")
            submit = st.form_submit_button("✅ FINALISASI & TANDAI SELESAI", type="primary", use_container_width=True, help="Menyimpan hasil ke database agar laporan bisa didownload.")

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
                st.success("🎉 Berhasil difinalisasi! Cek ke bawah form ini untuk mendownload Excel/JSON.")

    # ── DOWNLOAD BUTTONS — DI LUAR FORM ──
    if st.session_state.json_final_siap:
        jf = st.session_state.json_final_siap
        st.markdown("#### 📤 Unduh Hasil Ekstraksi (Pilih Salah Satu)")

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
            st.caption("📊 Excel — Paling direkomendasikan untuk laporan BPS")

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
                data=csv_buf.getvalue(), file_name=f"sifeno_{ts}.csv", mime="text/csv",
                use_container_width=True, key="dl_csv"
            )
            st.caption("📄 CSV — Mudah digabungkan di database tabular")

        with col_dl3:
            st.download_button(
                "⬇️ Download JSON",
                data=json.dumps(jf, indent=4, ensure_ascii=False).encode("utf-8"),
                file_name=f"sifeno_{ts}.json", mime="application/json",
                use_container_width=True, key="dl_json"
            )
            st.caption("🗂️ JSON — Untuk integrasi antar aplikasi/developer")

        with st.expander("👁️ Preview Hasil Akhir Cetak", expanded=False):
            df_preview = pd.DataFrame([
                {"No": i+1, "Variabel BPS": lbl, "Hasil Ekstraksi": jf.get(k,"")}
                for i, (k, lbl) in enumerate(LABEL_MAP_DL)
            ])
            st.dataframe(df_preview, use_container_width=True, hide_index=True,
                         column_config={"Hasil Ekstraksi": st.column_config.TextColumn(width="large")})

        if st.button("🔄 Mulai Kerjakan Artikel Baru"):
            st.session_state.json_final_siap = None
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: HISTORY & EKSPOR
# ═══════════════════════════════════════════════════════════════════════════════
with tab3:
    with st.expander("📖 Panduan Penggunaan Tab Riwayat", expanded=False):
        st.markdown("""
        **Fungsi Tab Ini:** Tempat Anda mengekspor seluruh rekapan aktivitas Radar dan AI dalam 1 database besar.
        1. **Analisis Visual:** Anda bisa melihat kategori PDRB apa yang paling sering muncul di media (tren ekonomi).
        2. **Export Excel Massal:** Jika atasan meminta rekap mingguan, filter tabel di bawah, lalu klik 'Download Excel'.
        """)

    st.markdown("## 📊 Riwayat & Visualisasi Data SI-FENO")

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
        st.info("Belum ada riwayat artikel di database SQLite. Jalankan radar terlebih dahulu.")
    else:
        st.markdown("### 📈 Tren Berita per Kategori")
        distribusi = df_riwayat['Kategori PDRB'].value_counts()
        st.bar_chart(distribusi, use_container_width=True, color="#4a6cf7")

        st.markdown("---")
        st.markdown("### 🗄️ Tabel Data Lengkap")
        
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            filter_status = st.multiselect(
                "Filter Status (Ditemukan = Di antrean):",
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
                "Filter Kategori (Opsional):",
                df_riwayat["Kategori PDRB"].unique().tolist() if not df_riwayat.empty else []
            )

        df_tampil = df_riwayat.copy()
        if filter_status: df_tampil = df_tampil[df_tampil["Status"].isin(filter_status)]
        if filter_tw: df_tampil = df_tampil[df_tampil["Triwulan"].isin(filter_tw)]
        if filter_kat: df_tampil = df_tampil[df_tampil["Kategori PDRB"].isin(filter_kat)]

        st.markdown(f"**Menampilkan {len(df_tampil)} dari {len(df_riwayat)} total entri di Database**")
        st.dataframe(df_tampil.drop(columns=["URL"]), use_container_width=True, hide_index=True)

        st.markdown("**📤 Export Tabel di Atas:**")
        col_e1, col_e2, col_e3 = st.columns(3)
        
        with col_e1:
            excel_buf_riwayat = io.BytesIO()
            with pd.ExcelWriter(excel_buf_riwayat, engine='openpyxl') as writer:
                df_tampil.to_excel(writer, index=False, sheet_name='Riwayat SIFENO')
            st.download_button(
                "⬇️ Download EXCEL (.xlsx)",
                data=excel_buf_riwayat.getvalue(),
                file_name=f"Rekap_Radar_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True, type="primary"
            )
            
        with col_e2:
            csv_exp = df_tampil.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Download CSV", data=csv_exp,
                               file_name=f"Rekap_Radar_{datetime.now().strftime('%Y%m%d')}.csv",
                               mime="text/csv", use_container_width=True)
                               
        with col_e3:
            json_exp = df_tampil.to_json(orient="records", force_ascii=False, indent=2)
            st.download_button("⬇️ Download JSON", data=json_exp.encode("utf-8"),
                               file_name=f"Rekap_Radar_{datetime.now().strftime('%Y%m%d')}.json",
                               mime="application/json", use_container_width=True)