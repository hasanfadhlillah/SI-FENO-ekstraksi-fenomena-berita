# File: radar/query_expander.py
"""
Modul A: Semantic Query Expander
Mengubah nomenklatur kaku PDRB menjadi keyword jurnalistik natural.
Menggunakan static dictionary (cepat) + AI fallback (untuk kategori tidak dikenal).
"""

import json
import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# ─── STATIC DICTIONARY ─────────────────────────────────────────────────────────
# Format: "nama_kategori": {"magelang": [...], "jateng": [...], "nasional": [...]}
# PERBAIKAN: Semua keyword level 1 dikunci ketat dengan "kota magelang"
KEYWORD_DICT = {
    # KATEGORI A: PERTANIAN
    "Tanaman Pangan": {
        "magelang": ["panen padi kota magelang", "harga beras kota magelang", "produksi jagung kota magelang", "pertanian kota magelang"],
        "jateng":   ["panen padi jawa tengah", "produksi beras jateng", "harga gabah jawa tengah"],
        "nasional": ["produksi padi nasional 2026", "stok beras bulog 2026", "panen jagung indonesia"],
    },
    "Tanaman Hortikultura Semusim": {
        "magelang": ["harga cabai kota magelang", "bawang merah kota magelang", "sayuran kota magelang"],
        "jateng":   ["cabai rawit jawa tengah", "bawang merah jateng", "hortikultura jawa tengah"],
        "nasional": ["harga cabai nasional 2026", "produksi bawang merah indonesia"],
    },
    "Perkebunan Semusim": {
        "magelang": ["tebu kota magelang", "tembakau kota magelang", "perkebunan kota magelang"],
        "jateng":   ["produksi tebu jawa tengah", "tembakau jateng"],
        "nasional": ["produksi gula nasional 2026", "tembakau indonesia"],
    },
    "Tanaman Hortikultura Tahunan": {
        "magelang": ["buah-buahan kota magelang", "durian kota magelang", "harga buah kota magelang"],
        "jateng":   ["buah-buahan jawa tengah", "hortikultura tahunan jateng"],
        "nasional": ["ekspor buah indonesia 2026"],
    },
    "Perkebunan Tahunan": {
        "magelang": ["kopi kota magelang", "kakao kota magelang", "perkebunan kota magelang"],
        "jateng":   ["kopi jawa tengah", "kakao jateng", "perkebunan tahunan jawa tengah"],
        "nasional": ["ekspor kopi indonesia 2026", "produksi kakao nasional"],
    },
    "Peternakan": {
        "magelang": ["harga daging sapi kota magelang", "harga telur kota magelang", "peternakan kota magelang"],
        "jateng":   ["peternakan jawa tengah", "sapi jateng", "produksi susu jawa tengah"],
        "nasional": ["harga daging sapi nasional 2026", "produksi telur indonesia"],
    },
    "Jasa Pertanian dan Perburuan": {
        "magelang": ["jasa pertanian kota magelang", "penyuluh pertanian kota magelang"],
        "jateng":   ["jasa pertanian jawa tengah", "alsintan jateng"],
        "nasional": ["jasa pertanian indonesia 2026"],
    },
    "Kehutanan dan Penebangan Kayu": {
        "magelang": ["kayu kota magelang", "penebangan pohon kota magelang"],
        "jateng":   ["kehutanan jawa tengah", "hutan produksi jateng"],
        "nasional": ["produksi kayu indonesia 2026", "deforestasi nasional"],
    },
    "Perikanan": {
        "magelang": ["harga ikan kota magelang", "budidaya ikan kota magelang", "pasar ikan kota magelang"],
        "jateng":   ["perikanan jawa tengah", "ikan laut jateng", "nelayan jawa tengah"],
        "nasional": ["produksi ikan indonesia 2026", "ekspor ikan nasional"],
    },
    # KATEGORI B: PERTAMBANGAN
    "Pertambangan Minyak dan Gas Bumi": {
        "magelang": ["BBM kota magelang", "pertamina kota magelang", "SPBU kota magelang"],
        "jateng":   ["migas jawa tengah", "blok migas jateng", "kuota pertalite jateng"],
        "nasional": ["produksi minyak bumi indonesia 2026", "lifting migas nasional"],
    },
    "Pertambangan Batubara dan Lignit": {
        "magelang": ["harga batubara kota magelang", "pasokan batu bara kota magelang"],
        "jateng":   ["batubara jawa tengah", "PLTU jateng"],
        "nasional": ["produksi batubara indonesia 2026", "ekspor batu bara nasional"],
    },
    "Pertambangan Bijih Logam": {
        "magelang": ["logam kota magelang", "tambang kota magelang"],
        "jateng":   ["pertambangan logam jawa tengah"],
        "nasional": ["nikel indonesia 2026", "tembaga nasional", "bijih logam indonesia"],
    },
    "Pertambangan dan Penggalian Lainnya": {
        "magelang": ["galian c kota magelang", "tambang pasir kota magelang", "material bangunan kota magelang"],
        "jateng":   ["galian c jawa tengah", "pasir uruk jateng", "tambang ilegal jateng"],
        "nasional": ["pertambangan galian c indonesia 2026"],
    },
    # KATEGORI C: INDUSTRI PENGOLAHAN
    "Industri Makanan dan Minuman": {
        "magelang": ["pabrik makanan kota magelang", "UMKM kuliner kota magelang", "industri minuman kota magelang", "pabrik tahu kota magelang"],
        "jateng":   ["industri makanan jawa tengah", "pabrik minuman jateng"],
        "nasional": ["industri makanan minuman indonesia 2026"],
    },
    "Pengolahan Tembakau": {
        "magelang": ["pabrik rokok kota magelang", "industri tembakau kota magelang", "cukai rokok kota magelang"],
        "jateng":   ["industri tembakau jawa tengah", "pabrik rokok jateng", "buruh rokok jateng"],
        "nasional": ["industri rokok indonesia 2026", "cukai tembakau nasional"],
    },
    "Industri Tekstil dan Pakaian Jadi": {
        "magelang": ["pabrik tekstil kota magelang", "konveksi kota magelang", "garmen kota magelang"],
        "jateng":   ["industri tekstil jawa tengah", "garmen jateng", "pabrik pakaian jateng"],
        "nasional": ["ekspor tekstil indonesia 2026", "PHK pabrik garmen"],
    },
    "Industri Kulit, Barang dari Kulit dan Alas Kaki": {
        "magelang": ["industri sepatu kota magelang", "pabrik sandal kota magelang", "kerajinan kulit kota magelang"],
        "jateng":   ["industri alas kaki jawa tengah", "pabrik sepatu jateng"],
        "nasional": ["ekspor alas kaki indonesia 2026"],
    },
    "Industri Kayu, Barang dari Kayu dan Gabus": {
        "magelang": ["mebel kota magelang", "furnitur kayu kota magelang", "pengrajin kayu kota magelang"],
        "jateng":   ["industri kayu jawa tengah", "ekspor mebel jateng"],
        "nasional": ["ekspor furnitur kayu indonesia 2026"],
    },
    "Industri Kertas dan Percetakan": {
        "magelang": ["percetakan kota magelang", "industri kertas kota magelang"],
        "jateng":   ["industri kertas jawa tengah", "percetakan jateng"],
        "nasional": ["industri kertas indonesia 2026"],
    },
    "Industri Kimia, Farmasi dan Obat Tradisional": {
        "magelang": ["pabrik obat kota magelang", "apotek kota magelang", "jamu kota magelang"],
        "jateng":   ["industri farmasi jawa tengah", "pabrik obat jateng", "jamu tradisional jateng"],
        "nasional": ["industri farmasi indonesia 2026", "ekspor jamu nasional"],
    },
    "Industri Karet, Barang dari Karet dan Plastik": {
        "magelang": ["pabrik plastik kota magelang", "industri plastik kota magelang"],
        "jateng":   ["industri karet jawa tengah", "pabrik plastik jateng"],
        "nasional": ["industri karet indonesia 2026"],
    },
    "Industri Barang Galian bukan Logam": {
        "magelang": ["pabrik genteng kota magelang", "keramik kota magelang", "toko bangunan kota magelang"],
        "jateng":   ["industri genteng jawa tengah", "keramik jateng"],
        "nasional": ["industri semen indonesia 2026"],
    },
    "Industri Logam Dasar": {
        "magelang": ["logam kota magelang", "bengkel las kota magelang"],
        "jateng":   ["industri logam jawa tengah", "baja jateng"],
        "nasional": ["industri baja indonesia 2026"],
    },
    "Industri Barang dari Logam, Komputer, Elektronik": {
        "magelang": ["toko elektronik kota magelang", "penjualan komputer kota magelang"],
        "jateng":   ["industri elektronik jawa tengah"],
        "nasional": ["industri elektronik indonesia 2026", "ekspor elektronik nasional"],
    },
    "Industri Alat Angkutan": {
        "magelang": ["karoseri kota magelang", "bengkel mobil kota magelang", "dealer kendaraan kota magelang"],
        "jateng":   ["industri otomotif jawa tengah", "karoseri jateng"],
        "nasional": ["produksi kendaraan indonesia 2026", "ekspor otomotif nasional"],
    },
    "Industri Furnitur": {
        "magelang": ["toko mebel kota magelang", "pabrik furnitur kota magelang"],
        "jateng":   ["industri furnitur jawa tengah", "mebel jateng"],
        "nasional": ["ekspor furnitur indonesia 2026"],
    },
    # KATEGORI D, E, F
    "Ketenagalistrikan": {
        "magelang": ["PLN kota magelang", "konsumsi listrik kota magelang", "tarif listrik kota magelang"],
        "jateng":   ["listrik jawa tengah", "PLN jateng", "ketenagalistrikan jateng"],
        "nasional": ["produksi listrik indonesia 2026", "bauran energi nasional"],
    },
    "Pengadaan Gas dan Produksi Es": {
        "magelang": ["harga LPG kota magelang", "pangkalan gas kota magelang", "pabrik es kota magelang"],
        "jateng":   ["jaringan gas jawa tengah", "LPG jateng"],
        "nasional": ["harga LPG nasional 2026", "subsidi gas elpiji"],
    },
    "Pengadaan Air": {
        "magelang": ["PDAM kota magelang", "tarif air kota magelang", "pasokan air bersih kota magelang"],
        "jateng":   ["PDAM jawa tengah", "air bersih jateng"],
        "nasional": ["akses air bersih indonesia 2026"],
    },
    "Konstruksi": {
        "magelang": ["proyek pemkot magelang", "infrastruktur kota magelang", "pembangunan jalan kota magelang"],
        "jateng":   ["konstruksi jawa tengah", "proyek infrastruktur jateng"],
        "nasional": ["realisasi APBN infrastruktur 2026", "konstruksi nasional"],
    },
    # KATEGORI G, H, I
    "Perdagangan Mobil, Sepeda Motor dan Reparasinya": {
        "magelang": ["penjualan motor kota magelang", "dealer mobil kota magelang", "bengkel resmi kota magelang"],
        "jateng":   ["penjualan kendaraan jawa tengah", "otomotif jateng"],
        "nasional": ["penjualan mobil motor indonesia 2026", "gaikindo 2026"],
    },
    "Perdagangan Besar dan Eceran": {
        "magelang": ["pasar rejowinangun kota magelang", "pasar tradisional kota magelang", "toko ritel kota magelang", "omzet pedagang kota magelang"],
        "jateng":   ["perdagangan jawa tengah", "pasar tradisional jateng", "harga sembako jateng"],
        "nasional": ["perdagangan ritel indonesia 2026", "omzet pasar nasional"],
    },
    "Angkutan Rel": {
        "magelang": ["stasiun kota magelang", "kereta api kota magelang", "reaktivasi jalur kereta kota magelang"],
        "jateng":   ["penumpang kereta daop 6", "volume barang KAI jawa tengah"],
        "nasional": ["penumpang KAI 2026", "volume angkutan kereta nasional"],
    },
    "Angkutan Darat": {
        "magelang": ["terminal tidar kota magelang", "angkutan umum kota magelang", "bus kota magelang"],
        "jateng":   ["angkutan darat jawa tengah", "bus AKDP jateng"],
        "nasional": ["angkutan darat indonesia 2026"],
    },
    "Angkutan Laut": {
        "magelang": ["logistik laut kota magelang", "pengiriman barang laut kota magelang"],
        "jateng":   ["pelabuhan semarang", "angkutan laut jawa tengah"],
        "nasional": ["angkutan laut indonesia 2026", "pelabuhan tanjung priok"],
    },
    "Angkutan Udara": {
        "magelang": ["agen tiket pesawat kota magelang", "travel udara kota magelang"],
        "jateng":   ["bandara ahmad yani semarang", "penerbangan jawa tengah", "bandara adi soemarmo"],
        "nasional": ["penumpang pesawat indonesia 2026", "maskapai domestik"],
    },
    "Pergudangan dan Jasa Penunjang Angkutan": {
        "magelang": ["gudang kota magelang", "jasa kurir kota magelang", "ekspedisi kota magelang"],
        "jateng":   ["logistik jawa tengah", "pergudangan jateng"],
        "nasional": ["logistik nasional 2026", "biaya logistik indonesia"],
    },
    "Penyediaan Akomodasi": {
        "magelang": ["tingkat hunian hotel kota magelang", "penginapan kota magelang", "hotel berbintang kota magelang"],
        "jateng":   ["hotel jawa tengah", "pariwisata akomodasi jateng"],
        "nasional": ["tingkat hunian hotel nasional 2026"],
    },
    "Penyediaan Makan Minum": {
        "magelang": ["restoran kota magelang", "pajak restoran kota magelang", "kafe kota magelang", "kuliner kota magelang"],
        "jateng":   ["restoran jawa tengah", "UMKM kuliner jateng"],
        "nasional": ["industri kuliner indonesia 2026"],
    },
    # KATEGORI J, K, L, dst
    "Informasi dan Komunikasi": {
        "magelang": ["pengguna internet kota magelang", "provider telekomunikasi kota magelang", "warnet kota magelang"],
        "jateng":   ["internet jawa tengah", "telekomunikasi jateng"],
        "nasional": ["industri digital indonesia 2026", "pengguna internet nasional"],
    },
    "Jasa Perantara Keuangan": {
        "magelang": ["kredit bank kota magelang", "penyaluran KUR kota magelang", "bank daerah kota magelang"],
        "jateng":   ["perbankan jawa tengah", "NPL bank jateng", "kredit UMKM jateng"],
        "nasional": ["kredit perbankan nasional 2026", "suku bunga bank indonesia"],
    },
    "Asuransi dan Dana Pensiun": {
        "magelang": ["klaim asuransi kota magelang", "BPJS ketenagakerjaan kota magelang", "BPJS kesehatan kota magelang"],
        "jateng":   ["asuransi jawa tengah", "BPJS jateng"],
        "nasional": ["industri asuransi indonesia 2026"],
    },
    "Jasa Keuangan Lainnya": {
        "magelang": ["koperasi kota magelang", "pegadaian kota magelang", "pinjol kota magelang"],
        "jateng":   ["koperasi jawa tengah", "fintech jateng"],
        "nasional": ["fintech indonesia 2026", "pinjaman online nasional"],
    },
    "Real Estate": {
        "magelang": ["harga perumahan kota magelang", "jual beli rumah kota magelang", "properti kota magelang"],
        "jateng":   ["properti jawa tengah", "harga tanah jateng"],
        "nasional": ["properti indonesia 2026", "harga rumah nasional"],
    },
    "Jasa Perusahaan": {
        "magelang": ["konsultan kota magelang", "jasa advertising kota magelang", "jasa keamanan kota magelang"],
        "jateng":   ["jasa perusahaan jawa tengah", "agen outsourcing jateng"],
        "nasional": ["jasa bisnis indonesia 2026"],
    },
    "Administrasi Pemerintahan dan Jaminan Sosial": {
        "magelang": ["APBD kota magelang", "belanja daerah pemkot magelang", "pajak daerah kota magelang"],
        "jateng":   ["pemerintah jawa tengah", "APBD jateng"],
        "nasional": ["realisasi APBN 2026", "belanja pemerintah nasional"],
    },
    "Jasa Pendidikan": {
        "magelang": ["sekolah negeri kota magelang", "biaya pendidikan kota magelang", "universitas di kota magelang"],
        "jateng":   ["pendidikan jawa tengah", "APK sekolah jateng"],
        "nasional": ["anggaran pendidikan indonesia 2026"],
    },
    "Jasa Kesehatan dan Kegiatan Sosial": {
        "magelang": ["RSUD kota magelang", "pasien rumah sakit kota magelang", "kesehatan warga kota magelang"],
        "jateng":   ["kesehatan jawa tengah", "stunting jateng", "fasilitas kesehatan jateng"],
        "nasional": ["kesehatan nasional 2026", "JKN BPJS nasional"],
    },
    "Jasa Lainnya": {
        "magelang": ["wisata taman kyai langgeng kota magelang", "kunjungan wisatawan kota magelang", "salon kota magelang"],
        "jateng":   ["pariwisata jawa tengah", "wisatawan jateng"],
        "nasional": ["pariwisata indonesia 2026"],
    },
    "PRODUK DOMESTIK BRUTO": {
        "magelang": ["pertumbuhan ekonomi kota magelang", "PDRB kota magelang", "inflasi kota magelang"],
        "jateng":   ["PDRB jawa tengah", "pertumbuhan ekonomi jateng", "inflasi jateng"],
        "nasional": ["PDB indonesia 2026", "pertumbuhan ekonomi nasional triwulan", "inflasi nasional"],
    },
}


def expand_query_dari_dict(nama_kategori: str) -> dict | None:
    """
    Cari keyword dari static dictionary.
    Return dict {magelang, jateng, nasional} atau None jika tidak ditemukan.
    """
    # Coba exact match dulu
    if nama_kategori in KEYWORD_DICT:
        return KEYWORD_DICT[nama_kategori]

    # Coba partial match (case-insensitive)
    nama_lower = nama_kategori.lower()
    for key, val in KEYWORD_DICT.items():
        if nama_lower in key.lower() or key.lower() in nama_lower:
            return val

    return None


def expand_query_via_ai(nama_kategori: str, api_key: str) -> dict:
    """
    Fallback: generate keyword menggunakan AI jika tidak ada di dictionary.
    Dipakai untuk kategori yang sangat spesifik atau tidak dikenal.
    """
    client = Groq(api_key=api_key)
    prompt = f"""Kamu adalah asisten riset BPS (Badan Pusat Statistik) Indonesia.
Tugasmu: ubah kategori PDRB berikut menjadi keyword pencarian berita jurnalistik.

Kategori PDRB: "{nama_kategori}"
Lokasi fokus: KOTA Magelang, Jawa Tengah, Indonesia

Hasilkan HANYA JSON ini tanpa penjelasan:
{{
  "magelang": ["keyword 1 kota magelang", "keyword 2 kota magelang", "keyword 3 kota magelang"],
  "jateng": ["keyword 1 jawa tengah", "keyword 2 jateng", "keyword 3 jateng"],
  "nasional": ["keyword 1 indonesia", "keyword 2 nasional", "keyword 3 indonesia 2026"]
}}

ATURAN PENTING:
- Gunakan bahasa wartawan lokal, BUKAN bahasa akademis BPS.
- Untuk area magelang, HARUS gunakan frasa "kota magelang", JANGAN HANYA "magelang" agar tidak tertukar dengan Kabupaten Magelang.
- Setiap level wilayah: berikan 3-4 keyword berbeda yang sering muncul di judul berita online."""

    try:
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
            response_format={"type": "json_object"}
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"   ⚠️ AI Query Expansion gagal: {e}. Pakai keyword generik.")
        kata = nama_kategori.lower().replace(",", "").replace("dan", "").strip()
        return {
            "magelang": [f"{kata} kota magelang", f"kondisi {kata} kota magelang"],
            "jateng":   [f"{kata} jawa tengah", f"{kata} jateng"],
            "nasional": [f"{kata} indonesia 2026", f"{kata} nasional"],
        }


def dapatkan_keywords(nama_kategori: str, api_key: str) -> dict:
    """
    Fungsi utama Modul A.
    Coba dict dulu, fallback ke AI jika tidak ditemukan.
    Return: {"magelang": [...], "jateng": [...], "nasional": [...]}
    """
    hasil = expand_query_dari_dict(nama_kategori)
    if hasil:
        print(f"   ✅ Keyword dari dictionary ({len(hasil['magelang'])} keyword level Kota)")
        return hasil

    print(f"   ⚠️ Tidak ada di dictionary, generate via AI...")
    return expand_query_via_ai(nama_kategori, api_key)