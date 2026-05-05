# File: radar/screener.py
"""
Modul E: AI Pre-Screening & Scoring
Membaca cepat isi artikel dan memberikan skor relevansi 1-10.
Dilengkapi dengan Auto-Fallback Model Stack untuk mencegah limit kuota.
"""

import json
import time
from groq import Groq
from google import genai as google_genai
from google.genai import types as google_types

# ─── KONFIGURASI MODEL STACK KHUSUS SCREENER ──────────────────────────────────
# Urutan prioritas: Kepintaran (70B) -> Kuota Besar (Gemini) -> Darurat (8B)
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
    Screening satu artikel menggunakan AI Stack.
    DIPERBAIKI:
    - Logika tampilan_wilayah yang benar
    - Aturan relevansi wilayah adaptif per level fallback
    - layak_ekstrak lebih fleksibel di level fallback tinggi
    """
    teks_pendek = artikel.get("teks", "")[:3000]
    judul = artikel.get("judul", "")
    url   = artikel.get("url_asli", artikel.get("url", ""))

    # ─── PERBAIKAN BUG 1: Cek dengan 'in' bukan '==' ─────────────────────────
    wilayah_lower = wilayah.lower()
    if "kota magelang" in wilayah_lower:
        tampilan_wilayah = "KOTA MAGELANG"
        level_ketat = True   # Level 1 → paling ketat
    elif "kabupaten magelang" in wilayah_lower:
        tampilan_wilayah = "KABUPATEN MAGELANG"
        level_ketat = True
    elif "kedu" in wilayah_lower:
        tampilan_wilayah = "EKS-KARESIDENAN KEDU (Magelang, Temanggung, Wonosobo, Purworejo)"
        level_ketat = False  # Level 3+ → mulai longgarkan wilayah
    elif "jawa tengah" in wilayah_lower or "jateng" in wilayah_lower:
        tampilan_wilayah = "PROVINSI JAWA TENGAH"
        level_ketat = False
    else:
        tampilan_wilayah = "NASIONAL / INDONESIA"
        level_ketat = False  # Level 5 → paling longgar

    # ─── PERBAIKAN BUG 2 & 3: Aturan wilayah adaptif per level ──────────────
    if level_ketat:
        aturan_wilayah = f"""ATURAN KETAT WILAYAH:
Karena target adalah "{tampilan_wilayah}", artikel HARUS membahas wilayah tersebut secara eksplisit.
Jika artikel membahas wilayah lain (misal Kabupaten saat target Kota, atau provinsi lain), 
set "relevan_dengan_wilayah": false dan skor MAKSIMAL 4.
"layak_ekstrak": true HANYA jika skor>=6 DAN SEMUA 4 boolean bernilai true."""
    else:
        aturan_wilayah = f"""ATURAN LONGGAR WILAYAH:
Karena ini mode fallback wilayah "{tampilan_wilayah}", kriteria wilayah DIPERLONGGAR.
Artikel tetap relevan jika membahas wilayah tersebut ATAU wilayah yang lebih kecil di dalamnya.
Fokus utama adalah KUALITAS DATA dan RELEVANSI KATEGORI, bukan ketepatan wilayah.
"relevan_dengan_wilayah": true jika artikel membahas wilayah ini ATAU sub-wilayahnya.
"layak_ekstrak": true jika skor>=6 DAN minimal 3 dari 4 boolean bernilai true."""

    prompt = f"""Kamu adalah validator berita statistik BPS Indonesia.
Baca cepat artikel ini dan nilai relevansinya berdasarkan parameter berikut:

Target Kategori PDRB: "{nama_kategori}"
Target Wilayah: "{tampilan_wilayah}"

JUDUL: {judul}
URL: {url}
TEKS (penggalan):
{teks_pendek}

Balas HANYA dengan JSON ini:
{{
  "skor_relevansi": <angka 1-10>,
  "alasan_singkat": "<1 kalimat alasan skor>",
  "ada_data_angka": <true/false>,
  "ada_perbandingan_waktu": <true/false>,
  "relevan_dengan_kategori": <true/false>,
  "relevan_dengan_wilayah": <true/false>,
  "layak_ekstrak": <lihat aturan di bawah>
}}

PANDUAN SKOR:
9-10: Ada data angka + perbandingan waktu (y-on-y/q-to-q/bulan lalu) + sangat relevan kategori DAN wilayah.
7-8 : Ada data angka + relevan, perbandingan waktu kurang eksplisit.
5-6 : Ada angka tapi relevansi kategori/wilayah cukup lemah.
1-4 : Opini tanpa data, tidak relevan kategori, atau wilayah sama sekali salah.

{aturan_wilayah}"""

    try:
        teks_json, model_terpakai = _call_ai_screening(api_keys, prompt)

        teks_json = teks_json.strip().replace('```json', '').replace('```', '').strip()

        hasil = json.loads(teks_json)
        hasil["url"]             = url
        hasil["judul"]           = judul
        hasil["teks"]            = artikel.get("teks", "")
        hasil["_model_screener"] = model_terpakai
        hasil["_level_ketat"]    = level_ketat  # Info debug: apakah pakai aturan ketat?
        return hasil

    except Exception as e:
        print(f"      ⚠️ Screening Gagal Total untuk {url[:50]}: {e}")
        return {
            "url": url, "judul": judul, "teks": artikel.get("teks", ""),
            "skor_relevansi": 0, "alasan_singkat": f"Error AI: {str(e)[:40]}",
            "ada_data_angka": False, "ada_perbandingan_waktu": False,
            "relevan_dengan_kategori": False, "relevan_dengan_wilayah": False,
            "layak_ekstrak": False, "_level_ketat": False
        }


def screening_batch(
    api_keys: dict,
    list_artikel: list[dict],
    nama_kategori: str,
    wilayah: str,
    min_skor: int = 6,
    jeda_detik: float = 1.5
) -> tuple[list[dict], list[dict]]:

    if not list_artikel:
        return [], []

    # ─── PERBAIKAN: Konsisten dengan logika di screening_satu_artikel ─────────
    wilayah_lower = wilayah.lower()
    if "kota magelang" in wilayah_lower:
        tampilan_wilayah = "KOTA MAGELANG"
    elif "kabupaten magelang" in wilayah_lower:
        tampilan_wilayah = "KABUPATEN MAGELANG"
    elif "kedu" in wilayah_lower:
        tampilan_wilayah = "EKS-KARESIDENAN KEDU"
    elif "jawa tengah" in wilayah_lower or "jateng" in wilayah_lower:
        tampilan_wilayah = "PROVINSI JAWA TENGAH"
    else:
        tampilan_wilayah = "NASIONAL / INDONESIA"
    # ──────────────────────────────────────────────────────────────────────────

    print(f"\n   🤖 AI Screening {len(list_artikel)} artikel untuk '{nama_kategori}' di {tampilan_wilayah}...")

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