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
    Return: (teks_json, nama_model_yang_berhasil)
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
                    max_tokens=300,
                    response_format={"type": "json_object"}
                )
                return resp.choices[0].message.content, cfg["nama"]

            elif provider == "gemini":
                client = google_genai.Client(api_key=api_key)
                teks_gabungan = f"SYSTEM: Validator berita BPS. Balas HANYA JSON murni tanpa markdown.\n\nUSER: {prompt}"
                resp = client.models.generate_content(
                    model=model_id,
                    contents=teks_gabungan,
                    config=google_types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=300,
                        response_mime_type="application/json"
                    )
                )
                return resp.text, cfg["nama"]

        except Exception as e:
            err = str(e).lower()
            is_limit = any(k in err for k in ["429", "rate limit", "quota", "exhausted", "too many requests"])
            
            if is_limit:
                print(f"         ⚠️ {cfg['nama']} Limit Kuota! Pindah ke model berikutnya...")
                time.sleep(1)
                continue
            else:
                print(f"         ⚠️ {cfg['nama']} Error: {e}")
                continue

    raise Exception("Semua model di Screener Stack kehabisan kuota atau error.")


def screening_satu_artikel(api_keys: dict, artikel: dict, nama_kategori: str, wilayah: str) -> dict:
    """
    Screening satu artikel menggunakan AI Stack.
    """
    teks_pendek = artikel.get("teks", "")[:3000]
    judul = artikel.get("judul", "")
    url   = artikel.get("url_asli", artikel.get("url", ""))

    tampilan_wilayah = "KOTA MAGELANG" if wilayah.lower() == "magelang" else wilayah.upper()

    prompt = f"""
        Kamu adalah validator berita statistik BPS Indonesia.
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
        "layak_ekstrak": <true jika skor>=6 DAN keempat boolean di atas bernilai true>
        }}

        PANDUAN SKOR:
        9-10: Ada data angka + perbandingan waktu (y-on-y/q-to-q/bulan lalu) + sangat relevan dengan kategori DAN wilayah.
        7-8: Ada data angka + relevan, tapi perbandingan waktu kurang eksplisit.
        5-6: Ada angka tapi relevansi kategori/wilayah cukup lemah.
        1-4: Artikel opini, tidak ada data, atau MEMBAHAS WILAYAH YANG SALAH.

        ATURAN KHUSUS WILAYAH:
        Jika Target Wilayah adalah "KOTA MAGELANG", dan artikel tersebut secara eksplisit membahas "KABUPATEN MAGELANG" atau wilayah lain, maka "relevan_dengan_wilayah" WAJIB false dan skor maksimal adalah 4!
        """

    try:
        teks_json, model_terpakai = _call_ai_screening(api_keys, prompt)
        
        # Bersihkan sisa markdown
        teks_json = teks_json.strip()
        teks_json = teks_json.replace('```json', '').replace('```', '').strip()
        
        hasil = json.loads(teks_json)
        hasil["url"]   = url
        hasil["judul"] = judul
        hasil["teks"]  = artikel.get("teks", "")
        # Info tambahan: Model mana yang meloloskan/menolak artikel ini
        hasil["_model_screener"] = model_terpakai 
        return hasil

    except Exception as e:
        print(f"      ⚠️ Screening Gagal Total untuk {url[:50]}: {e}")
        return {
            "url": url, "judul": judul, "teks": artikel.get("teks", ""),
            "skor_relevansi": 0, "alasan_singkat": f"Error AI: {str(e)[:40]}",
            "ada_data_angka": False, "ada_perbandingan_waktu": False,
            "relevan_dengan_kategori": False, "relevan_dengan_wilayah": False,
            "layak_ekstrak": False
        }


def screening_batch(
    api_keys: dict,
    list_artikel: list[dict],
    nama_kategori: str,
    wilayah: str,
    min_skor: int = 6,
    jeda_detik: float = 1.5  # Diubah jadi 1.5 detik karena model 70B butuh jeda lebih lama
) -> tuple[list[dict], list[dict]]:
    """
    Screening semua artikel dalam batch.
    Return: (artikel_lolos, artikel_gagal)
    """
    if not list_artikel:
        return [], []

    tampilan_wilayah = "KOTA MAGELANG" if wilayah.lower() == "magelang" else wilayah.upper()
    print(f"\n   🤖 AI Screening {len(list_artikel)} artikel untuk '{nama_kategori}' di {tampilan_wilayah}...")

    lolos  = []
    gagal  = []

    for i, artikel in enumerate(list_artikel, 1):
        print(f"      [{i}/{len(list_artikel)}] Menilai: {artikel.get('judul', '')[:50]}...")
        
        hasil = screening_satu_artikel(api_keys, artikel, nama_kategori, wilayah)

        skor = hasil.get("skor_relevansi", 0)
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