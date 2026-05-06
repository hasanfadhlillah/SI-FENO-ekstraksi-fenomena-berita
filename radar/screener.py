# File: radar/screener.py
"""
Modul E: AI Pre-Screening & Scoring
Membaca cepat isi artikel dan memberikan skor relevansi 1-10.
Dilengkapi dengan Auto-Fallback Model Stack untuk mencegah limit kuota.
"""

import json
import time
import openai
from groq import Groq
from google import genai as google_genai
from google.genai import types as google_types

# ─── KONFIGURASI MODEL STACK ──────────────────────────────────────────────────
SCREENER_STACK = [
    {
        "nama": "Groq — Llama 3.3 70B",
        "provider": "groq",
        "model_id": "llama-3.3-70b-versatile"
    },
    {
        "nama": "Google — Gemini 2.5 Flash",
        "provider": "gemini",
        "model_id": "gemini-2.5-flash"
    },
    {
        "nama": "Cerebras — GPT-OSS 120B",   # ← TAMBAH INI: 1M token/hari gratis
        "provider": "cerebras",
        "model_id": "gpt-oss-120b"
    },
    {
        "nama": "Groq — Llama 3.1 8B Instant",
        "provider": "groq",
        "model_id": "llama-3.1-8b-instant"
    }
]


def _call_ai_screening(api_keys: dict, prompt: str) -> tuple[str, str]:
    """
    Menjalankan request AI dengan fallback stack.
    DIPERBAIKI: Handle None response dari Gemini.
    """
    for cfg in SCREENER_STACK:
        provider = cfg["provider"]
        model_id = cfg["model_id"]
        api_key  = api_keys.get(provider, "").strip()

        if not api_key:
            continue

        try:
            if provider == "groq":
                client = Groq(api_key=api_key)
                resp = client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": "Validator berita BPS. Balas HANYA JSON murni tanpa markdown."},
                        {"role": "user",   "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=400,
                    response_format={"type": "json_object"}
                )
                teks = resp.choices[0].message.content
                # ─── PERBAIKAN: Validasi tidak None ───
                if teks is None or teks.strip() == "":
                    raise ValueError("Groq mengembalikan respons kosong")
                return teks, cfg["nama"]

            elif provider == "gemini":
                client = google_genai.Client(api_key=api_key)
                gabung = f"SYSTEM: Validator berita BPS. Balas HANYA JSON murni.\n\nUSER: {prompt}"
                resp = client.models.generate_content(
                    model=model_id,
                    contents=gabung,
                    config=google_types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=400,
                        response_mime_type="application/json",
                        thinking_config=google_types.ThinkingConfig(thinking_budget=0)
                    )
                )
                # ─── PERBAIKAN: Validasi tidak None sebelum .strip() ───
                teks = resp.text if resp.text is not None else ""
                if teks.strip() == "":
                    raise ValueError("Gemini mengembalikan respons kosong")
                return teks, cfg["nama"]
            
            elif provider == "cerebras":
                client = openai.OpenAI(
                    api_key=api_key,
                    base_url="https://api.cerebras.ai/v1"
                )
                resp = client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": "Validator berita BPS. Balas HANYA JSON murni tanpa markdown."},
                        {"role": "user",   "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=400,
                    response_format={"type": "json_object"}
                )
                teks = resp.choices[0].message.content
                if teks is None or teks.strip() == "":
                    raise ValueError("Cerebras mengembalikan respons kosong")
                return teks, cfg["nama"]

        except Exception as e:
            err = str(e).lower()
            is_limit = any(k in err for k in [
                "429", "rate limit", "quota", "exhausted",
                "too many requests", "resource_exhausted"
            ])
            if is_limit:
                print(f"         ⚠️ {cfg['nama']} Limit Kuota! Pindah ke model berikutnya...")
                time.sleep(2)
                continue
            elif "503" in err or "unavailable" in err:
                print(f"         ⚠️ {cfg['nama']} Server sibuk (503). Pindah ke model berikutnya...")
                continue
            else:
                print(f"         ⚠️ {cfg['nama']} Error: {str(e)[:80]}")
                continue

    raise Exception("Semua model di Screener Stack error atau habis kuota.")


def screening_satu_artikel(api_keys: dict, artikel: dict, nama_kategori: str, wilayah: str) -> dict:
    """
    Screening satu artikel.
    KONSEP BARU: Berita dari wilayah MANAPUN bisa lolos, asal fenomenanya
    relevan/berdampak pada kondisi ekonomi Kota Magelang.
    """
    teks_pendek = artikel.get("teks", "")[:3000]
    judul       = artikel.get("judul", "")
    url         = artikel.get("url_asli", artikel.get("url", ""))

    # Tentukan konteks wilayah untuk prompt
    wilayah_lower = wilayah.lower()
    if "kota magelang" in wilayah_lower:
        konteks = "Sedang mencari berita untuk level KOTA MAGELANG (pencarian pertama/utama)."
    elif "kabupaten magelang" in wilayah_lower:
        konteks = "Sedang mencari berita untuk level KABUPATEN MAGELANG (fallback level 2)."
    elif "kedu" in wilayah_lower:
        konteks = "Sedang mencari berita untuk level EKS-KARESIDENAN KEDU (fallback level 3)."
    elif "jawa tengah" in wilayah_lower or "jateng" in wilayah_lower:
        konteks = "Sedang mencari berita untuk level PROVINSI JAWA TENGAH (fallback level 4)."
    else:
        konteks = "Sedang mencari berita untuk level NASIONAL/INDONESIA (fallback level 5, kriteria paling longgar)."

    prompt = f"""Kamu adalah validator berita untuk BPS KOTA MAGELANG, Jawa Tengah, Indonesia.

TUGAS UTAMA: Nilai apakah artikel berita ini mengandung FENOMENA STATISTIK yang RELEVAN untuk data PDRB Kota Magelang.

Kategori PDRB yang dicari: "{nama_kategori}"
{konteks}

JUDUL: {judul}
URL: {url}
TEKS ARTIKEL:
{teks_pendek}

FILOSOFI PENILAIAN (SANGAT PENTING):
Berita TIDAK HARUS secara eksplisit menyebut "Kota Magelang".
Berita dari wilayah manapun (Kabupaten Magelang, Jawa Tengah, Nasional) TETAP RELEVAN jika:
- Fenomenanya (harga, produksi, stok) BERDAMPAK atau MENCERMINKAN kondisi di Kota Magelang
- Contoh LOLOS: "Harga beras Jateng naik 15%" → berdampak ke Kota Magelang
- Contoh LOLOS: "Panen padi Kabupaten Magelang surplus" → mencerminkan kondisi wilayah
- Contoh LOLOS: "Sidak Bulog Magelang, stok aman" → langsung menyebut Magelang
- Contoh TIDAK LOLOS: "Banjir di Papua rusak sawah" → tidak ada kaitan dengan Magelang
- Contoh TIDAK LOLOS: "Artikel opini tanpa data angka apapun"

KRITERIA FENOMENA STATISTIK VALID (minimal salah satu):
1. Ada DATA ANGKA spesifik (harga Rp, %, ton, kuintal, hektare, jumlah, dll)
2. Ada PERBANDINGAN WAKTU (naik/turun dari bulan lalu, tahun lalu, triwulan sebelumnya)
3. Ada PERNYATAAN RESMI dari pejabat/instansi tentang kondisi sektor tersebut

Balas HANYA dengan JSON ini (tanpa markdown):
{{
  "skor_relevansi": <1-10>,
  "alasan_singkat": "<1-2 kalimat mengapa skor ini>",
  "ada_data_angka": <true/false>,
  "ada_perbandingan_waktu": <true/false>,
  "relevan_dengan_kategori": <true/false>,
  "berdampak_ke_magelang": <true jika fenomena berdampak/mencerminkan kondisi Magelang>,
  "layak_ekstrak": <true jika skor>=6 DAN relevan_dengan_kategori=true DAN berdampak_ke_magelang=true>
}}

PANDUAN SKOR:
9-10: Data angka + perbandingan waktu + langsung menyebut Magelang/sekitarnya
7-8 : Data angka + relevan kategori + berdampak ke Magelang (meski tidak sebut langsung)
5-6 : Ada angka tapi relevansi kategori lemah, ATAU relevan tapi minim data
1-4 : Tidak ada data, tidak relevan kategori, atau sama sekali tidak ada kaitan Magelang"""

    try:
        teks_json, model_terpakai = _call_ai_screening(api_keys, prompt)
        teks_json = teks_json.strip().replace('```json', '').replace('```', '').strip()
        hasil = json.loads(teks_json)
        hasil["url"]             = url
        hasil["judul"]           = judul
        hasil["teks"]            = artikel.get("teks", "")
        hasil["_model_screener"] = model_terpakai
        return hasil

    except Exception as e:
        print(f"      ⚠️ Screening Gagal Total untuk {url[:50]}: {e}")
        return {
            "url": url, "judul": judul, "teks": artikel.get("teks", ""),
            "skor_relevansi": 0, "alasan_singkat": f"Error AI: {str(e)[:40]}",
            "ada_data_angka": False, "ada_perbandingan_waktu": False,
            "relevan_dengan_kategori": False, "berdampak_ke_magelang": False,
            "layak_ekstrak": False
        }


def screening_batch(
    api_keys: dict,
    list_artikel: list[dict],
    nama_kategori: str,
    wilayah: str,
    min_skor: int = 6,
    jeda_detik: float = 1.0,
    max_artikel: int = 15        # ← BATASI max 15 artikel per level agar hemat kuota
) -> tuple[list[dict], list[dict]]:

    if not list_artikel:
        return [], []

    # Batasi jumlah artikel yang masuk ke AI
    if len(list_artikel) > max_artikel:
        print(f"   ⚠️ Terlalu banyak artikel ({len(list_artikel)}), dipotong ke {max_artikel} terbaik...")
        list_artikel = list_artikel[:max_artikel]

    wilayah_lower = wilayah.lower()
    if "kota magelang" in wilayah_lower:
        tampilan = "KOTA MAGELANG"
    elif "kabupaten magelang" in wilayah_lower:
        tampilan = "KABUPATEN MAGELANG"
    elif "kedu" in wilayah_lower:
        tampilan = "EKS-KARESIDENAN KEDU"
    elif "jawa tengah" in wilayah_lower or "jateng" in wilayah_lower:
        tampilan = "PROVINSI JAWA TENGAH"
    else:
        tampilan = "NASIONAL / INDONESIA"

    print(f"\n   🤖 AI Screening {len(list_artikel)} artikel untuk '{nama_kategori}' di {tampilan}...")

    lolos = []
    gagal = []

    for i, artikel in enumerate(list_artikel, 1):
        print(f"      [{i}/{len(list_artikel)}] Menilai: {artikel.get('judul', '')[:50]}...")
        hasil = screening_satu_artikel(api_keys, artikel, nama_kategori, wilayah)
        skor  = hasil.get("skor_relevansi", 0)
        layak = hasil.get("layak_ekstrak", False)

        if skor >= min_skor and layak:
            badge = "🟢" if skor >= 8 else "🟡"
            print(f"         {badge} LOLOS — Skor {skor}/10 | by {hasil.get('_model_screener', 'AI')}")
            lolos.append(hasil)
        else:
            print(f"         🔴 TIDAK LOLOS — Skor {skor}/10 | by {hasil.get('_model_screener', 'AI')}")
            gagal.append(hasil)

        time.sleep(jeda_detik)

    print(f"\n   📊 Screening selesai: {len(lolos)} lolos, {len(gagal)} tidak lolos")
    return lolos, gagal