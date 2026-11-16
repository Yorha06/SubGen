# SubGen - Video to SRT Subtitle Transcription

Aplikasi desktop lokal untuk mentranskripsikan video panjang menjadi subtitle `.srt` menggunakan `whisper.cpp` dengan akselerasi GPU AMD melalui Vulkan.

## Fitur Utama

- Transkripsi multibahasa (Jepang, Inggris, Korea, Bahasa Indonesia, dan lainnya)
- Akselerasi GPU AMD via Vulkan (fallback ke CPU)
- Pemrosesan video panjang per segmen dengan checkpoint/resume
- Output SRT UTF-8 yang valid
- Nama output otomatis dibuat unik agar file sebelumnya tidak tertimpa
- Preview isi SRT dan buka folder output dari aplikasi
- File sementara dibersihkan setelah job berakhir
- Terjemahkan file SRT yang sudah ada tanpa menjalankan Whisper ulang
- Terjemahan lokal/offline melalui Argos Translate
- Berjalan sepenuhnya lokal, tidak mengirim data ke cloud

## Struktur Proyek

```
video-subtitle-tool/
├── README.md
├── TODO.md
├── requirements.txt
├── pyproject.toml
├── app.py
├── config/
│   ├── default.yaml
│   └── languages.json
├── src/subtitle_app/
│   ├── __init__.py
│   ├── app.py
│   ├── app_controller.py
│   ├── settings.py
│   ├── models/
│   │   ├── job.py
│   │   ├── segment.py
│   │   └── subtitle_cue.py
│   ├── gui/
│   │   ├── main_window.py
│   │   ├── settings_dialog.py
│   │   ├── job_panel.py
│   │   └── subtitle_preview.py
│   ├── pipeline/
│   │   ├── job_runner.py
│   │   ├── probe_media.py
│   │   ├── extract_audio.py
│   │   ├── segment_audio.py
│   │   ├── transcribe.py
│   │   ├── merge_segments.py
│   │   ├── format_subtitles.py
│   │   ├── translate.py
│   │   └── export_srt.py
│   ├── services/
│   │   ├── ffmpeg_service.py
│   │   ├── whisper_cpp_service.py
│   │   ├── gpu_detection.py
│   │   └── job_store.py
│   └── utils/
│       ├── timestamps.py
│       ├── logging_setup.py
│       └── file_validation.py
├── models/          (model AI disimpan di sini)
├── tools/           (ffmpeg, whisper.cpp binary)
├── jobs/            (manifest dan status pekerjaan)
├── output/          (file SRT hasil)
└── tests/
```

## Instalasi

1. Clone atau salin repositori ini.
2. Buat virtual environment:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   ```
3. Instal dependensi:
   ```
   pip install -r requirements.txt
   ```
4. Unduh dan pasang FFmpeg, simpan di `tools/ffmpeg/`.
5. Build atau unduh `whisper.cpp` dengan backend Vulkan, simpan di `tools/whisper.cpp/`.
6. Unduh model Whisper (misal: `ggml-large-v3-turbo-q5_0.bin`), simpan di `models/`.
   VAD nonaktif secara default; jika diaktifkan, atur `vad_model_path` di
   `config/default.yaml` ke file model VAD yang valid.
7. Terjemahan SRT memakai Argos Translate. Pada pemakaian pertama, SubGen
   mengunduh dan memasang model bahasa lokal yang diperlukan; teks subtitle
   tidak dikirim ke layanan terjemahan online. Pilih mode **Terjemahkan file
   SRT**, pilih bahasa sumber dan tujuan, sumber `.srt`, lalu tentukan file
   output `.srt`. Bahasa tujuan yang tersedia: Indonesia, Inggris, Jepang,
   dan Korea. Mode ini tidak mengulang ekstraksi audio atau transkripsi Whisper.
   Jika Argos mengembalikan terjemahan kosong, cue tersebut dipertahankan dalam
   bahasa sumber dan jumlahnya ditampilkan pada status pekerjaan.

Bahasa sumber otomatis mengenali tulisan Jepang dan Korea; teks Latin dianggap
bahasa Inggris. Jika sumbernya berbeda, pilih bahasanya secara manual.

## Menjalankan Aplikasi

```
python app.py
```

## Roadmap

Lihat `TODO.md` untuk rencana pengerjaan detail per tahap.