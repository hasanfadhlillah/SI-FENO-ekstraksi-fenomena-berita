# File: test_run.py
import os, json
from dotenv import load_dotenv
from scraper import scrape_berita
from ai_engine import ekstrak_fenomena_ai

load_dotenv()

# Kumpulkan semua API key dari .env
KEYS = {
    "groq"    : os.environ.get("GROQ_API_KEY", ""),
    "gemini"  : os.environ.get("GEMINI_API_KEY", ""),
    "cerebras": os.environ.get("CEREBRAS_API_KEY", ""),
}

# Cek apakah file .env sudah ada isinya (Opsional)
if not any(KEYS.values()):
    print("⚠️  Peringatan: Tidak ada API Key yang ditemukan di file .env!")

LINK_BERITA = "https://radarmagelang.jawapos.com/magelang/687213386/hingga-pertengahan-februari-2026-serapan-gabah-bulog-magelang-capai-4500-ton"

def main():
    print("=" * 60)
    print("    SI-FENO — SISTEM EKSTRAKSI FENOMENA BERITA")
    print("    Stack: 6 Model | 3 Provider | ~21.000 req/hari")
    print("=" * 60)

    print("\n[STEP 1] Scraping artikel...")
    hasil_scrape = scrape_berita(LINK_BERITA)
    if hasil_scrape["status"] == "error":
        print(f"❌ {hasil_scrape['pesan']}")
        return
    print(f"  ✅ Judul  : {hasil_scrape['judul']}")
    print(f"  📄 Teks   : {len(hasil_scrape['teks'])} karakter")
    print(f"  🔧 Metode : {hasil_scrape.get('metode', 'N/A')}")

    print("\n[STEP 2] Ekstraksi AI (auto-stacking 6 model)...")
    hasil_ai = ekstrak_fenomena_ai(KEYS, hasil_scrape)

    if hasil_ai["status"] == "error":
        print(f"\n❌ {hasil_ai['pesan']}")
        return

    print("\n" + "=" * 60)
    print("           HASIL EKSTRAKSI FENOMENA")
    print("=" * 60)
    print(json.dumps(hasil_ai["data"], indent=4, ensure_ascii=False))
    print("=" * 60)
    model = hasil_ai['data'].get('_model_digunakan', 'N/A')
    print(f"\n✅ Selesai! Diproses oleh: {model}")

if __name__ == "__main__":
    main()