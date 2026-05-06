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
# Diselaraskan dengan MODEL_STACK di ai_engine.py
SCREENER_STACK = [
    {
        "nama": "Groq — Llama 3.3 70B",
        "provider": "groq",
        "model_id": "llama-3.3-70b-versatile"
    },
    {
        "nama": "Cerebras — Llama 3.3 70B",
        "provider": "cerebras",
        "model_id": "llama-3.3-70b"            # ✅ DIFIX: bukan gpt-oss-120b
    },
    {
        "nama": "Google — Gemini 2.5 Flash",
        "provider": "gemini",
        "model_id": "gemini-2.5-flash"
    },
    {
        "nama": "Mistral — Mistral Small",
        "provider": "mistral",
        "model_id": "mistral-small-latest"      # ← BARU: ~1B token/bulan gratis
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

            elif provider == "mistral":
                client = openai.OpenAI(
                    api_key=api_key,
                    base_url="https://api.mistral.ai/v1"
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
                    raise ValueError("Mistral mengembalikan respons kosong")
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
            elif "404" in err or "not found" in err or "does not exist" in err:
                print(f"         ⚠️ {cfg['nama']} Model 404! Pindah ke model berikutnya...")
                continue
            else:
                print(f"         ⚠️ {cfg['nama']} Error: {str(e)[:80]}")
                continue

    raise Exception("Semua model di Screener Stack error atau habis kuota.")


def screening_satu_artikel(api_keys: dict, artikel: dict, nama_kategori: str, wilayah: str) -> dict:
    """
    Screening artikel untuk BPS Kota Magelang.

    ATURAN GEOGRAFI YANG BENAR:
    ✅ LOLOS: Artikel menyebut Kota Magelang secara eksplisit
    ✅ LOLOS: Artikel tentang Kabupaten Magelang (1 wilayah, berdampak ke Kota)
    ✅ LOLOS: Artikel Jawa Tengah (provinsi Kota Magelang berada)
    ✅ LOLOS: Artikel NASIONAL dari Kementerian/Badan/Pemerintah Pusat
              yang dampaknya ke SELURUH Indonesia (otomatis termasuk Kota Magelang)
    ❌ TOLAK: Artikel dari provinsi LAIN (Jatim, Bali, Sumsel, Kalsel, dll)
              yang tidak menyebut Magelang/Jawa Tengah sama sekali
    ❌ TOLAK: Artikel opini/berita tanpa data angka apapun
    """
    teks_pendek = artikel.get("teks", "")[:4000]
    judul       = artikel.get("judul", "")
    url         = artikel.get("url_asli", artikel.get("url", ""))

    # Tentukan konteks level untuk AI
    wilayah_lower = wilayah.lower()
    if "kota magelang" in wilayah_lower:
        level_info = "Level 1 - KOTA MAGELANG (target utama)"
    elif "kabupaten magelang" in wilayah_lower:
        level_info = "Level 2 - KABUPATEN MAGELANG (fallback)"
    elif "kedu" in wilayah_lower:
        level_info = "Level 3 - EKS-KARESIDENAN KEDU (fallback)"
    elif "jawa tengah" in wilayah_lower or "jateng" in wilayah_lower:
        level_info = "Level 4 - PROVINSI JAWA TENGAH (fallback)"
    else:
        level_info = "Level 5 - NASIONAL/INDONESIA (fallback terakhir)"

    prompt = f"""
        Kamu adalah validator berita untuk BPS KOTA MAGELANG, Jawa Tengah, Indonesia.
        TUGAS: Nilai apakah artikel ini LAYAK DIEKSTRAK untuk keperluan data PDRB Kota Magelang.

        === KONTEKS PENCARIAN ===
        Kategori PDRB: "{nama_kategori}"
        Level Pencarian: {level_info}

        === DATA ARTIKEL ===
        JUDUL: {judul}
        URL: {url}
        ISI ARTIKEL:
        {teks_pendek}

        === ATURAN GEOGRAFI (WAJIB DIPATUHI) ===
        JENIS ARTIKEL YANG WAJIB DILOLOSKAN (jika memenuhi syarat data):
        1. ✅ Artikel yang secara EKSPLISIT menyebut "Kota Magelang" atau "Magelang"
        2. ✅ Artikel yang membahas "Kabupaten Magelang" (satu wilayah, berdampak ke Kota)
        3. ✅ Artikel yang membahas kondisi di "Jawa Tengah" atau "Jateng" (provinsi Kota Magelang)
        4. ✅ Artikel NASIONAL dari KEMENTERIAN/BADAN/PEMERINTAH PUSAT (contoh: Kementan, Bulog, BPS Pusat, Bapanas, dll) yang menetapkan kebijakan/data berlaku SELURUH Indonesia — otomatis berdampak ke Kota Magelang

        JENIS ARTIKEL YANG WAJIB DITOLAK:
        1. ❌ Artikel dari PROVINSI LAIN (Jawa Timur, Bali, Sumatera Selatan, Kalimantan, Papua, dll) yang TIDAK menyebut Magelang atau Jawa Tengah sama sekali
        2. ❌ Artikel yang hanya membahas kota/kabupaten lain di luar Jawa Tengah tanpa kaitan ke Magelang
        3. ❌ Artikel opini/lifestyle/hiburan tanpa data statistik apapun
        4. ❌ Artikel tentang topik yang SAMA SEKALI tidak berkaitan dengan kategori "{nama_kategori}"

        CONTOH KEPUTUSAN:
        - "Produksi Padi Jatim Tembus 8,7 Juta Ton" → ❌ TOLAK (Jatim bukan Jateng, tidak sebut Magelang)
        - "Harga Beras di Bali Stabil" → ❌ TOLAK (Bali bukan Jateng)
        - "Panen Padi Kabupaten Magelang Surplus" → ✅ LOLOS (menyebut Magelang)
        - "Kementan: Produksi Beras Nasional Naik 15%" → ✅ LOLOS (kebijakan nasional, berdampak ke semua daerah termasuk Kota Magelang)
        - "Harga Beras Jawa Tengah Naik Menjelang Lebaran" → ✅ LOLOS (Jawa Tengah = provinsi Kota Magelang)
        - "BPS: Inflasi Pangan Nasional Bulan Ini 0,5%" → ✅ LOLOS (data nasional BPS berlaku semua daerah)
        - "Bulog Pastikan Stok Beras Nasional Aman" → ✅ LOLOS (kebijakan nasional Bulog)

        === KRITERIA DATA FENOMENA STATISTIK ===
        Minimal SALAH SATU harus terpenuhi untuk skor ≥ 6:
        A. Ada DATA ANGKA SPESIFIK: harga (Rp), persentase (%), berat (ton/kuintal/kg), luas (ha), jumlah unit/orang
        B. Ada PERBANDINGAN WAKTU: "naik X% dari bulan lalu", "turun dibanding tahun lalu", "y-on-y", "q-to-q"
        C. Ada PERNYATAAN DATA RESMI dari pejabat/instansi pemerintah tentang kondisi sektor

        === FORMAT JAWABAN ===
        Balas HANYA dengan JSON ini (tanpa markdown, tanpa teks lain):
        {{
        "skor_relevansi": <angka 1-10>,
        "alasan_singkat": "<2-3 kalimat: sebutkan isi artikel, kenapa lolos/tidak, dan data apa yang ada>",
        "ada_data_angka": <true/false>,
        "ada_perbandingan_waktu": <true/false>,
        "relevan_dengan_kategori": <true/false>,
        "wilayah_valid": <true jika lolos aturan geografi di atas, false jika artikel provinsi lain>,
        "sumber_nasional_resmi": <true jika dari Kementerian/Badan/Pemerintah Pusat yang berdampak nasional>,
        "layak_ekstrak": <true HANYA jika: skor>=6 DAN relevan_dengan_kategori=true DAN wilayah_valid=true>
        }}

        === PANDUAN SKOR DETAIL ===
        10  : Ada data angka SPESIFIK + perbandingan waktu + menyebut Kota/Kab Magelang LANGSUNG
        9   : Ada data angka spesifik + perbandingan waktu + konteks Jawa Tengah
        8   : Ada data angka spesifik + relevan kategori + wilayah valid (Magelang/Jateng/Nasional resmi)
        7   : Ada data angka + relevan kategori + wilayah valid, tapi perbandingan waktu kurang eksplisit
        6   : Ada data angka atau pernyataan resmi + relevan kategori + wilayah valid, tapi data kurang spesifik
        5   : Relevan kategori + wilayah valid, tapi minim data konkret
        3-4 : Ada kaitan dengan kategori tapi data sangat kurang atau wilayah kurang relevan
        1-2 : Artikel tidak relevan kategori, atau berasal dari provinsi lain yang tidak berdampak ke Magelang
        """

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
            "skor_relevansi": 0, "alasan_singkat": f"Error AI: {str(e)[:60]}",
            "ada_data_angka": False, "ada_perbandingan_waktu": False,
            "relevan_dengan_kategori": False, "wilayah_valid": False,
            "sumber_nasional_resmi": False, "layak_ekstrak": False
        }


def screening_batch(
    api_keys: dict,
    list_artikel: list[dict],
    nama_kategori: str,
    wilayah: str,
    min_skor: int = 6,
    jeda_detik: float = 1.0,
    max_artikel: int = 15
) -> tuple[list[dict], list[dict]]:

    if not list_artikel:
        return [], []

    # Prioritaskan artikel yang ada "magelang" di judul/URL
    def skor_prioritas(art):
        teks_cek = (art.get("judul", "") + art.get("url", "")).lower()
        if "kota magelang" in teks_cek:
            return 0
        elif "magelang" in teks_cek:
            return 1
        elif "jawa tengah" in teks_cek or "jateng" in teks_cek:
            return 2
        else:
            return 3

    list_artikel_sorted = sorted(list_artikel, key=skor_prioritas)

    if len(list_artikel_sorted) > max_artikel:
        print(f"   ⚠️ {len(list_artikel_sorted)} artikel dipotong ke {max_artikel} (prioritas: Magelang > Jateng > Nasional)")
        list_artikel_sorted = list_artikel_sorted[:max_artikel]

    # Label tampilan wilayah
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

    print(f"\n   🤖 AI Screening {len(list_artikel_sorted)} artikel untuk '{nama_kategori}' di {tampilan}...")

    lolos = []
    gagal = []

    for i, artikel in enumerate(list_artikel_sorted, 1):
        print(f"      [{i}/{len(list_artikel_sorted)}] Menilai: {artikel.get('judul', '')[:55]}...")
        hasil = screening_satu_artikel(api_keys, artikel, nama_kategori, wilayah)
        skor  = hasil.get("skor_relevansi", 0)
        layak = hasil.get("layak_ekstrak", False)

        if skor >= min_skor and layak:
            badge = "🟢" if skor >= 8 else "🟡"
            wilayah_valid = hasil.get("wilayah_valid", False)
            print(f"         {badge} LOLOS — Skor {skor}/10 | Wilayah valid: {wilayah_valid} | by {hasil.get('_model_screener', 'AI')}")
            lolos.append(hasil)
        else:
            wilayah_valid = hasil.get("wilayah_valid", False)
            print(f"         🔴 TIDAK LOLOS — Skor {skor}/10 | Wilayah valid: {wilayah_valid} | by {hasil.get('_model_screener', 'AI')}")
            gagal.append(hasil)

        time.sleep(jeda_detik)

    print(f"\n   📊 Screening selesai: {len(lolos)} lolos, {len(gagal)} tidak lolos")
    return lolos, gagal