# File: ai_engine.py
import json
import time
import requests
import openai  # Pindahkan ke atas agar fail-fast jika belum terinstall
from groq import Groq
from google import genai as google_genai
from google.genai import types as google_types

# ─── KONFIGURASI MODEL STACK ────────────────────────────────────────────────────
MODEL_STACK = [
    {
        "nama"      : "Groq — Llama 3.3 70B",
        "provider"  : "groq",
        "model_id"  : "llama-3.3-70b-versatile",
        "max_chars" : 8000,
    },
    {
        "nama"      : "Google — Gemini 2.5 Flash",
        "provider"  : "gemini",
        "model_id"  : "gemini-2.5-flash",          # stable alias, selalu terbaru
        "max_chars" : 10000,
    },
    {
        "nama"      : "Cerebras — GPT-OSS 120B",
        "provider"  : "cerebras",
        "model_id"  : "gpt-oss-120b",              # open-weight reasoning model by OpenAI
        "max_chars" : 4000,
    },
    {
        "nama"      : "Google — Gemini 2.5 Flash-Lite",
        "provider"  : "gemini",
        "model_id"  : "gemini-2.5-flash-lite",     # stable alias
        "max_chars" : 10000,
    },
    {
        "nama"      : "Groq — Llama 3.1 8B Instant",
        "provider"  : "groq",
        "model_id"  : "llama-3.1-8b-instant",
        "max_chars" : 8000,
    },
    {
        "nama"      : "Groq — Gemma 2 9B",
        "provider"  : "groq",
        "model_id"  : "gemma2-9b-it",
        "max_chars" : 4000,
    },
]

# ─── Buat Prompt ────────────────────────────────────────────────────────────────
def _buat_prompt(data_artikel: dict, max_chars: int) -> str:
    teks = data_artikel['teks'][:max_chars]
    return f"""
        Anda adalah Analis Data Ahli yang Handal dan Professional di Badan Pusat Statistik (BPS) Kota Magelang.
        Tugas Anda adalah menganalisis teks artikel berita dan mengekstrak fenomena yang relevan untuk data statistik DENGAN SUPER LENGKAP, SUPER DETAIL, DAN SUPER TEPAT DAN BENAR TANPA ADA YANG TERTINGGAL.
        
        Data Artikel Sumber:
        URL: {data_artikel['url']}
        Judul Web: {data_artikel['judul']}
        Tanggal Web: {data_artikel['tanggal']}
        
        Teks Artikel:
        {teks}
        
        EKSTRAK KE DALAM JSON DENGAN 12 KEY WAJIB BERIKUT:
        1. "tema_topik": Kategori utama (misal Inflasi, Pertanian, Bencana Alam, Pariwisata, Kemiskinan, Ketenagakerjaan, dsb).
        2. "judul_dan_tanggal": Kombinasi judul asli berita dan tanggal publish.
        3. "sumber_dan_link": Nama media massa dan URL berita lengkap.
        4. "ringkasan_fenomena": rangkuman/ringkasan/penjelasan 4-5 Kalimat tentang penyebab kejadian, perubahan data angka, persentase, angka-angka penting (misal jumlah lokasi/daerah yang terdampak, jumlah yang dioptimalkan, dan sejenisnya), dan lain-lainya + beserta alasannya (pastikan dalam ringkasan sudah termasuk ada pernyataan narasumber yang diubah ke kalimat tidak langsung).
        5. "data_angka": Ekstraksi nilai kuantitatif spesifik (misal harga, persentase %, ton, jumlah korban/hektar, dan lain-lainnya) yang disebutkan.
        6. "kutipan_tokoh": Sebutkan semua pernyataan/statement/kata-kata resmi pejabat/tokoh/narasumber di dalam berita beserta nama dan jabatannya (biasanya ditandai dengan tanda kutip, ... ujarnya, ... ungkapnya, ... katanya, ... ungkap beliau, ungkap [nama narasumber/tokoh/pejabat], atau yang lain-lainnya).
        7. "lokasi_spesifik": Fokus area kejadian, misal nama kecamatan, pasar, atau desa, atau yang lainnya di Magelang.
        8. "intervensi_pemerintah": Sebutkan semua tindakan/aksi/kebijakan yang diambil oleh pemerintah yang disebutkan untuk merespons fenomena tersebut (misal operasi pasar, bantuan, dan lain-lainnya).
        9. "periode_kejadian": Kapan peristiwa tersebut terjadi, Rentang waktu riil peristiwa terjadi, terlepas dari tanggal berita rilis (misal tahun/bulan/minggu ke berapa).
        10. "kata_kunci": 3-5 hashtags untuk mempermudah pencarian (contoh: #Beras #GagalPanen).
        11. "sentimen_dampak": Pilih salah satu: Positif / Negatif / Netral.
        12. "kategori_perbandingan": Analisis narasi dan kutipan narasumber di dalam teks untuk menentukan satu perbandingan fenomena secara eksklusif, lalu pilih "y-on-y" (jika dibandingkan dengan tahun sebelumnya), "q-to-q" (kuartal/bulan sebelumnya), "harga" (fluktuasi harian/mingguan), atau "Tidak ada informasi" (jika tidak ada perbandingan waktu sama sekali).
        
        ATURAN:
        a. Jika data benar-benar tidak ada di teks, isi dengan "Tidak ada informasi".
        b. Jangan pernah membuat-buat data (No Hallucination).
        c. Balas HANYA dengan JSON murni tanpa penjelasan, tanpa markdown, tanpa backtick.
        """

# ─── Caller: Groq ───────────────────────────────────────────────────────────────
def _call_groq(api_key: str, model_id: str, prompt: str) -> str:
    client = Groq(api_key=api_key)
    resp = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": "Kamu analis data BPS. Balas HANYA JSON murni yang valid."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=2000,
        response_format={"type": "json_object"}
    )
    u = resp.usage
    print(f"   -> [Token] in:{u.prompt_tokens} out:{u.completion_tokens} total:{u.total_tokens}")
    return resp.choices[0].message.content

# ─── Caller: Gemini (pakai SDK resmi, bukan REST manual) ───────────────────────
def _call_gemini(api_key: str, model_id: str, prompt: str) -> str:
    client = google_genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=model_id,
        contents=prompt,
        config=google_types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=2000,
            response_mime_type="application/json",
            # Matikan thinking config untuk respon yang lebih stabil jika didukung
            thinking_config=google_types.ThinkingConfig(thinking_budget=0)
        )
    )
    return resp.text

# ─── Caller: Cerebras (OpenAI-compatible) ──────────────────────────────────────
def _call_cerebras(api_key: str, model_id: str, prompt: str) -> str:
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.cerebras.ai/v1"
    )
    resp = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": "Kamu analis data BPS. Balas HANYA JSON murni yang valid."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=2000,
        response_format={"type": "json_object"}
    )
    return resp.choices[0].message.content

# ─── Fungsi Utama ───────────────────────────────────────────────────────────────
def ekstrak_fenomena_ai(keys: dict, data_artikel: dict) -> dict:
    """
    Stacking 6 model dari 3 provider.
    Auto-fallback jika rate limit atau model error.
    keys = {"groq": "gsk_...", "gemini": "AIza...", "cerebras": "csk_..."}
    """
    for cfg in MODEL_STACK:
        provider = cfg["provider"]
        api_key  = keys.get(provider, "").strip()

        if not api_key or api_key.startswith("GANTI"):
            print(f"   -> [Skip] {cfg['nama']}: API key belum diisi.")
            continue

        print(f"\n   -> [Mencoba] {cfg['nama']}...")
        prompt = _buat_prompt(data_artikel, cfg["max_chars"])

        try:
            if provider == "groq":
                teks_json = _call_groq(api_key, cfg["model_id"], prompt)
            elif provider == "gemini":
                teks_json = _call_gemini(api_key, cfg["model_id"], prompt)
            elif provider == "cerebras":
                teks_json = _call_cerebras(api_key, cfg["model_id"], prompt)
            else:
                continue

            # PERBAIKAN: Bersihkan sisa markdown JSON yang jauh lebih aman dari lstrip
            teks_bersih = teks_json.strip()
            teks_bersih = teks_bersih.replace('```json', '').replace('```', '').strip()
            
            hasil = json.loads(teks_bersih)
            hasil["_model_digunakan"] = cfg["nama"]
            print(f"   -> [✅ Sukses] {cfg['nama']}")
            return {"status": "sukses", "data": hasil}

        except json.JSONDecodeError as e:
            print(f"   -> [Error JSON] {cfg['nama']}: {e}")
            continue

        except Exception as e:
            err = str(e)
            is_rate_limit = any(k in err for k in [
                "429", "rate_limit", "quota", "RESOURCE_EXHAUSTED",
                "Too Many Requests", "token", "RPM", "RPD"
            ])
            is_not_found = any(k in err for k in [
                "404", "not found", "does not exist", "model_not_found"
            ])

            if is_rate_limit:
                print(f"   -> [⚠️  Rate Limit] {cfg['nama']} → lanjut model berikutnya...")
                time.sleep(1)
            elif is_not_found:
                print(f"   -> [❌ Model 404] {cfg['nama']} → model tidak ditemukan, lewati.")
            else:
                print(f"   -> [Error] {cfg['nama']}: {err[:120]}")
            continue

    return {
        "status": "error",
        "pesan": "Semua model habis quota atau error. Coba lagi nanti!"
    }