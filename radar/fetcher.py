# File: radar/fetcher.py
"""
Modul D: Parallel Scraping
Mengambil isi artikel dari banyak URL sekaligus menggunakan ThreadPoolExecutor.
Memanfaatkan scrape_berita() dari SI-FENO yang sudah ada.
"""

import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import scraper dari folder induk
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scraper import scrape_berita


def fetch_parallel(list_url: list[str], max_workers: int = 5) -> list[dict]:
    """
    Scraping semua URL secara paralel.
    Return: list dict hasil scraping (hanya yang sukses).
    """
    if not list_url:
        return []

    print(f"\n   📥 Scraping {len(list_url)} URL secara paralel (max {max_workers} thread)...")
    hasil_semua = []
    gagal = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Mapping future → url
        future_to_url = {
            executor.submit(scrape_berita, url): url
            for url in list_url
        }

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                hasil = future.result(timeout=60)
                if hasil["status"] == "sukses" and len(hasil.get("teks", "")) > 200:
                    hasil["url_asli"] = url
                    hasil_semua.append(hasil)
                    print(f"      ✅ OK: {hasil['judul'][:60]}...")
                else:
                    print(f"      ❌ Gagal/Kosong: {url[:60]}...")
                    gagal += 1
            except Exception as e:
                print(f"      ❌ Exception: {url[:60]}... → {e}")
                gagal += 1

    print(f"   📊 Scraping selesai: {len(hasil_semua)} sukses, {gagal} gagal")
    return hasil_semua