# TODO --- Aplikasi Transkripsi Video ke Subtitle (SRT)

**Target platform:** Windows 11\
**Hardware sasaran:** AMD Ryzen 5 5500GT, Radeon RX 7600 8 GB VRAM, RAM
16 GB\
**Tujuan:** Aplikasi desktop lokal yang menerima video panjang,
mentranskripsikan audio multibahasa (termasuk Jepang, Inggris, dan
Korea), memanfaatkan GPU AMD melalui Vulkan, lalu menghasilkan subtitle
standar `.srt`. Penerjemahan ke Bahasa Indonesia disediakan sebagai
tahap opsional yang terpisah.

------------------------------------------------------------------------

## 1. Tujuan dan ruang lingkup

### Tujuan utama

-   [ ] Pengguna dapat memilih satu file video dan menghasilkan subtitle
    `.srt`.
-   [ ] Mendukung video berdurasi panjang dengan pemrosesan bertahap dan
    dapat dilanjutkan setelah gagal.
-   [ ] Mendukung deteksi bahasa otomatis dan pemilihan bahasa manual.
-   [ ] Memanfaatkan Radeon RX 7600 melalui backend Vulkan jika build
    dan drGUIiver mendukungnya.
-   [ ] Menjaga timestamp tetap sesuai posisi asli di video.
-   [ ] Menyediakan pilihan transkripsi bahasa asli atau transkripsi
    yang dilanjutkan dengan terjemahan ke Bahasa Indonesia.
-   [ ] Berjalan secara lokal tanpa mengirim video/audio ke layanan
    cloud.

### Bukan sasaran versi pertama

-   [ ] Dubbing atau sintesis suara.
-   [ ] Pengenalan pembicara tingkat lanjut/diarization.
-   [ ] Penerjemahan real-time.
-   [ ] Editor subtitle profesional dengan timeline multi-track.
-   [ ] Menjamin transkripsi 100% benar tanpa pemeriksaan manusia.

### Format dan bahasa

-   Input video: MP4, MKV, MOV, AVI, WebM (bergantung dukungan FFmpeg).
-   Audio: format apa pun yang dapat dibaca FFmpeg.
-   Output utama: SubRip `.srt` UTF-8.
-   Bahasa: gunakan daftar bahasa yang didukung model Whisper;
    prioritaskan pengujian Japanese (`ja`), English (`en`), Korean
    (`ko`), dan Indonesian (`id`).

------------------------------------------------------------------------

## 2. Keputusan teknologi

  -----------------------------------------------------------------------
  Bagian                  Pilihan awal            Alasan
  ----------------------- ----------------------- -----------------------
  Bahasa aplikasi         Python 3                Pengembangan GUI dan
                                                  pipeline relatif cepat

  GUI                     PySide6                 Aplikasi desktop
                                                  Windows

  Mesin transkripsi       `whisper.cpp`           Mendukung model
                                                  GGML/GGUF dan backend
                                                  Vulkan pada build yang
                                                  sesuai

  Akselerasi GPU          Vulkan                  Jalur praktis untuk GPU
                                                  AMD di Windows; bukan
                                                  CUDA

  Ekstraksi audio         FFmpeg / ffprobe        Membaca banyak format
                                                  video dan audio

  Pemrosesan audio        PCM WAV mono, 16 kHz    Format masukan umum
                                                  untuk Whisper

  Pengelolaan pekerjaan   Python worker/thread +  GUI tetap responsif
                          antrean                 

  Penyimpanan status      SQLite atau JSON per    Resume, status segmen,
                          pekerjaan               dan konfigurasi

  Output subtitle         SRT UTF-8               Kompatibilitas luas

  Pengujian               pytest                  Uji unit dan integrasi
  -----------------------------------------------------------------------

**Catatan kompatibilitas:** Vulkan harus diverifikasi pada mesin target.
Jangan mengasumsikan semua binary `whisper.cpp` memiliki Vulkan. Build
harus dikompilasi atau diunduh dari sumber tepercaya dengan backend
Vulkan aktif. Sediakan fallback CPU bila inisialisasi Vulkan gagal.
ROCm/HIP tidak dijadikan jalur utama Windows karena kompatibilitas dan
pemasangannya lebih rumit.

### Model awal

-   Model kualitas/kecepatan: Whisper `large-v3-turbo`.
-   Alternatif kualitas: `large-v3`.
-   Alternatif hemat memori/waktu: `medium` atau `small`.
-   Quantization: mulai uji dengan Q5 atau Q4 yang tersedia untuk model
    terkait. Bandingkan kualitas dan konsumsi VRAM sebelum menetapkan
    default.
-   Model disimpan lokal dan dapat dipilih dari pengaturan aplikasi.

**Penting:** Nama file model dan format kuantisasi harus sesuai dengan
format yang didukung versi `whisper.cpp` yang digunakan. Jangan
mengasumsikan setiap model Hugging Face dapat langsung dipakai tanpa
konversi.

------------------------------------------------------------------------

## 3. Arsitektur sistem

### 3.1 Diagram komponen

``` text
+-----------------------------------------------------------+
|                    DESKTOP GUI (PySide6)                  |
|  Pilih Video | Bahasa | Model | Mode | Progress | Preview |
+-----------------------------+-----------------------------+
                              |
                              v
+-----------------------------------------------------------+
|                    APPLICATION CONTROLLER                 |
| Validasi input | Buat job | Atur status | Cancel / Resume |
+-----------------------------+-----------------------------+
                              |
                              v
+-----------------------------------------------------------+
|                       JOB PIPELINE                        |
|                                                           |
|  1. Probe media (ffprobe)                                 |
|  2. Extract audio (FFmpeg -> PCM mono 16 kHz)              |
|  3. Segment audio + overlap                                |
|  4. Transcribe per segmen (whisper.cpp)                    |
|  5. Koreksi offset timestamp                               |
|  6. Merge + deduplicate overlap                            |
|  7. Format subtitle                                        |
|  8. Optional translation                                   |
|  9. Export SRT                                             |
+-----------+-------------------------------+---------------+
            |                               |
            v                               v
+-------------------------+     +---------------------------+
| MEDIA / AUDIO SERVICES  |     | AI INFERENCE SERVICE      |
| FFmpeg, ffprobe         |     | whisper.cpp CLI/API        |
| Audio validation        |     | Vulkan GPU / CPU fallback |
+-------------------------+     +---------------------------+
            |                               |
            +---------------+---------------+
                            v
+-----------------------------------------------------------+
|                 JOB STORAGE / CACHE                       |
| metadata | segment status | temporary WAV | logs | output |
+-----------------------------------------------------------+
```

### 3.2 Alur data

``` text
Video
  |
  v
ffprobe: durasi, codec, stream audio, sample rate
  |
  v
FFmpeg: ekstrak audio -> PCM WAV mono 16 kHz
  |
  v
Segmenter: potong audio ke bagian yang dapat diproses
  |
  v
Whisper.cpp: transkripsi tiap segmen
  |
  v
Timestamp normalizer: tambahkan offset awal segmen
  |
  v
Merger: gabungkan, hilangkan duplikasi overlap
  |
  +----> Mode A: subtitle bahasa asli
  |
  +----> Mode B: terjemahkan teks -> Bahasa Indonesia
  |
  v
Subtitle formatter / validator
  |
  v
File .srt UTF-8
```

### 3.3 Batas tanggung jawab komponen

-   **GUI:** hanya mengatur input, opsi, progress, preview, dan tindakan
    pengguna. GUI tidak menjalankan proses berat secara langsung.
-   **Controller:** membuat dan mengelola pekerjaan serta menghubungkan
    GUI dengan pipeline.
-   **Media service:** memanggil FFmpeg/ffprobe dan memvalidasi file.
-   **Segmenter:** menentukan rentang audio dan overlap.
-   **Transcription service:** menjalankan `whisper.cpp`, mengumpulkan
    teks dan timestamp.
-   **Post-processor:** mengoreksi offset, menggabungkan segmen,
    membersihkan hasil, dan membentuk cue subtitle.
-   **Translation service:** opsional; menerima teks transkripsi dan
    menghasilkan terjemahan tanpa mengubah timestamp.
-   **Exporter:** menulis SRT dan memvalidasi format.
-   **Job store:** menyimpan konfigurasi, status segmen, log, dan lokasi
    file sementara.

------------------------------------------------------------------------

## 4. Struktur proyek yang disarankan

``` text
video-subtitle-tool/
├── README.md
├── TODO.md
├── requirements.txt
├── pyproject.toml
├── app.py
├── config/
│   ├── default.yaml
│   └── languages.json
├── src/
│   └── subtitle_app/
│       ├── __init__.py
│       ├── app_controller.py
│       ├── settings.py
│       ├── models/
│       │   ├── job.py
│       │   ├── segment.py
│       │   └── subtitle_cue.py
│       ├── gui/
│       │   ├── main_window.py
│       │   ├── settings_dialog.py
│       │   ├── job_panel.py
│       │   └── subtitle_preview.py
│       ├── pipeline/
│       │   ├── job_runner.py
│       │   ├── probe_media.py
│       │   ├── extract_audio.py
│       │   ├── segment_audio.py
│       │   ├── transcribe.py
│       │   ├── merge_segments.py
│       │   ├── format_subtitles.py
│       │   ├── translate.py
│       │   └── export_srt.py
│       ├── services/
│       │   ├── ffmpeg_service.py
│       │   ├── whisper_cpp_service.py
│       │   ├── gpu_detection.py
│       │   └── job_store.py
│       └── utils/
│           ├── timestamps.py
│           ├── logging_setup.py
│           └── file_validation.py
├── models/
│   └── .gitkeep
├── tools/
│   ├── ffmpeg/
│   └── whisper.cpp/
├── jobs/
│   └── .gitkeep
├── output/
│   └── .gitkeep
└── tests/
    ├── test_timestamps.py
    ├── test_srt_export.py
    ├── test_segment_merge.py
    ├── test_audio_pipeline.py
    └── test_job_resume.py
```

Model AI dan binary besar tidak perlu dimasukkan ke Git. Dokumentasikan
cara mendapatkannya dan simpan secara lokal.

------------------------------------------------------------------------

## 5. TODO implementasi terperinci

## Tahap 0 --- Validasi lingkungan dan benchmark

-   [ ] Catat versi Windows, driver AMD, dan versi Vulkan runtime.
-   [ ] Pastikan Radeon RX 7600 terdeteksi oleh sistem.
-   [ ] Siapkan Python 64-bit versi yang kompatibel dengan dependensi.
-   [ ] Instal FFmpeg dan ffprobe; pastikan keduanya dapat dipanggil
    dari terminal.
-   [ ] Build atau siapkan `whisper.cpp` dengan backend Vulkan aktif.
-   [ ] Jalankan perintah pemeriksaan backend dan pastikan perangkat
    Vulkan terlihat.
-   [ ] Uji satu file audio pendek menggunakan CPU.
-   [ ] Uji file yang sama menggunakan Vulkan.
-   [ ] Catat waktu proses, penggunaan VRAM, penggunaan RAM, dan
    kualitas hasil.
-   [ ] Siapkan fallback CPU jika GPU tidak tersedia atau gagal.
-   [ ] Bandingkan model Small, Medium, Large-v3 Turbo Q5, dan Large-v3
    sesuai kemampuan perangkat.
-   [ ] Tentukan model default berdasarkan hasil benchmark, bukan hanya
    perkiraan.

**Kriteria selesai:** transkripsi sampel berhasil; mode GPU benar-benar
terpakai saat dipilih; fallback CPU berfungsi; aplikasi tidak mengklaim
GPU aktif bila backend sebenarnya CPU.

## Tahap 1 --- Fondasi aplikasi

-   [ ] Buat struktur folder proyek.
-   [ ] Buat konfigurasi terpusat untuk path FFmpeg, binary whisper.cpp,
    model, folder sementara, dan output.
-   [ ] Buat kelas `Job` dengan ID, input, status, opsi, waktu mulai,
    dan lokasi output.
-   [ ] Buat status pekerjaan: `queued`, `probing`, `extracting`,
    `segmenting`, `transcribing`, `merging`, `translating`, `exporting`,
    `completed`, `failed`, `cancelled`.
-   [ ] Buat logging ke file per pekerjaan.
-   [ ] Buat validasi file input dan ruang penyimpanan.
-   [ ] Buat pengelolaan folder sementara per pekerjaan.
-   [ ] Pastikan path yang mengandung spasi atau karakter non-ASCII
    dapat diproses.

**Kriteria selesai:** sebuah job dapat dibuat, statusnya berubah, log
tercatat, dan error dapat ditampilkan secara jelas.

## Tahap 2 --- Pemeriksaan video dan ekstraksi audio

-   [ ] Jalankan `ffprobe` untuk mendapatkan durasi, stream audio,
    codec, channel, sample rate, dan metadata.
-   [ ] Tangani video tanpa audio dengan pesan yang jelas.
-   [ ] Izinkan pengguna memilih track audio bila video memiliki
    beberapa track.
-   [ ] Ekstrak audio ke PCM WAV mono 16 kHz.
-   [ ] Gunakan nama file sementara yang aman.
-   [ ] Pastikan durasi audio hasil ekstraksi sesuai durasi track
    sumber.
-   [ ] Tampilkan durasi video, track audio, dan ukuran file pada GUI.
-   [ ] Tangani kegagalan FFmpeg, file rusak, dan ruang disk tidak
    cukup.

**Kriteria selesai:** audio dapat diekstrak dari format input yang
didukung dan metadata sumber tersimpan.

## Tahap 3 --- Segmentasi untuk video panjang

-   [ ] Buat segmenter berdasarkan durasi audio.
-   [ ] Default awal: segmen 15--20 menit; jadikan pengaturan yang dapat
    diubah.
-   [ ] Tambahkan overlap kecil pada batas segmen (misalnya 1--3 detik)
    untuk mengurangi risiko kata terpotong.
-   [ ] Simpan `segment_start`, `segment_end`, dan `overlap` untuk
    setiap segmen.
-   [ ] Jangan memotong segmen di tengah ucapan jika tersedia metode
    deteksi jeda yang stabil.
-   [ ] Pastikan semua segmen mencakup audio sumber tanpa celah.
-   [ ] Simpan daftar segmen dalam metadata job.
-   [ ] Buat retry per segmen jika proses gagal.
-   [ ] Dukung resume: segmen yang sudah berhasil tidak diproses ulang.
-   [ ] Jangan menjalankan banyak inferensi GPU bersamaan pada RX 7600 8
    GB; mulai dengan satu proses inferensi.
-   [ ] Batasi jumlah file audio sementara agar penggunaan disk
    terkendali.

**Catatan:** 15--20 menit adalah nilai awal, bukan angka wajib. Uji 5,
10, dan 20 menit. Segmen lebih pendek memudahkan retry tetapi menambah
overhead dan risiko batas kalimat; segmen lebih panjang mengurangi
overhead tetapi lebih berat dan lebih sulit diulang.

**Kriteria selesai:** video panjang dapat diproses per segmen, seluruh
segmen terpetakan ke posisi waktu asli, dan job dapat dilanjutkan.

## Tahap 4 --- Integrasi Whisper.cpp dan GPU AMD

-   [ ] Buat wrapper yang menjalankan binary `whisper.cpp`.
-   [ ] Kirim path model, file audio segmen, bahasa, dan parameter
    decoding.
-   [ ] Sediakan pilihan bahasa `Auto` dan bahasa manual.
-   [ ] Sediakan pilihan model dari model yang sudah terpasang.
-   [ ] Sediakan pengaturan beam size dan opsi VAD secara sederhana.
-   [ ] Mulai dengan satu worker inferensi agar VRAM tidak penuh.
-   [ ] Deteksi backend/perangkat dari output pemeriksaan runtime.
-   [ ] Tampilkan mode aktual: Vulkan GPU atau CPU.
-   [ ] Jika Vulkan gagal, tawarkan fallback CPU dan catat alasan
    kegagalan.
-   [ ] Tangkap stdout, stderr, exit code, dan durasi setiap segmen.
-   [ ] Parse output terstruktur yang disediakan versi whisper.cpp
    (misalnya JSON), bukan mengandalkan parsing teks terminal yang
    rapuh.
-   [ ] Normalisasi hasil ke format internal `Segment`.
-   [ ] Simpan hasil tiap segmen segera setelah selesai.
-   [ ] Uji transkripsi bahasa Jepang dengan audio percakapan nyata,
    bukan hanya sampel bersih.
-   [ ] Uji audio dengan musik latar, suara pelan, beberapa pembicara,
    dan jeda panjang.

**Kriteria selesai:** hasil teks dan timestamp dapat diambil secara
konsisten; mode Vulkan terverifikasi; kegagalan satu segmen tidak
menghapus hasil segmen lain.

## Tahap 5 --- Penanganan bahasa dan kualitas transkripsi

-   [ ] Gunakan deteksi bahasa otomatis hanya jika pengguna memilih
    `Auto`.
-   [ ] Jika pengguna memilih Japanese, teruskan kode bahasa `ja` ke
    Whisper.
-   [ ] Sediakan bahasa manual untuk menghindari salah deteksi pada
    audio pendek atau campuran.
-   [ ] Jangan menerjemahkan otomatis pada tahap transkripsi.
-   [ ] Pertahankan teks asli dan bahasa hasil deteksi di data job.
-   [ ] Sediakan kamus istilah/nama khusus sebagai fitur lanjutan jika
    metode prompting model mendukungnya.
-   [ ] Jangan menganggap koreksi ejaan otomatis selalu benar, terutama
    nama karakter, istilah fiksi, dan nama orang.
-   [ ] Sediakan opsi untuk menonaktifkan VAD atau mengubah
    sensitivitasnya.
-   [ ] Bandingkan hasil dengan dan tanpa VAD pada bahasa Jepang.
-   [ ] Simpan opsi decoding yang digunakan agar hasil dapat
    direproduksi.

**Catatan akurasi:** Whisper dapat salah mengenali nama, istilah,
percakapan pelan, dialog yang tertutup musik, atau beberapa pembicara
yang tumpang tindih. Subtitle harus dapat diedit atau diperiksa
pengguna.

## Tahap 6 --- Penggabungan segmen dan timestamp

-   [ ] Konversi timestamp lokal segmen ke timestamp global video dengan
    menambahkan offset awal segmen.
-   [ ] Pastikan satuan waktu internal konsisten (milidetik atau detik).
-   [ ] Tangani overlap di awal/akhir segmen.
-   [ ] Hilangkan teks duplikat akibat overlap tanpa menghapus
    pengulangan dialog yang memang diucapkan.
-   [ ] Urutkan semua cue berdasarkan waktu mulai.
-   [ ] Pastikan waktu selesai lebih besar daripada waktu mulai.
-   [ ] Cegah cue bertumpuk secara tidak wajar.
-   [ ] Pertahankan jeda asli sebisa mungkin.
-   [ ] Validasi bahwa timestamp tidak melampaui durasi media secara
    signifikan.
-   [ ] Buat tes untuk batas segmen, overlap, dan video berdurasi
    panjang.

**Kriteria selesai:** gabungan hasil memiliki urutan waktu benar, tidak
ada offset yang hilang, dan duplikasi batas segmen terkendali.

## Tahap 7 --- Pemformatan subtitle SRT

-   [ ] Buat nomor cue berurutan mulai dari 1.
-   [ ] Format timestamp standar `HH:MM:SS,mmm --> HH:MM:SS,mmm`.
-   [ ] Tulis file UTF-8 agar karakter Jepang, Korea, dan Indonesia
    tetap benar.
-   [ ] Pisahkan cue berdasarkan batas kalimat dan jeda, bukan hanya
    setiap hasil segmen.
-   [ ] Batasi panjang baris dan jumlah baris sebagai preferensi, bukan
    aturan kaku.
-   [ ] Sediakan pengaturan durasi minimum/maksimum cue.
-   [ ] Hindari cue terlalu singkat atau terlalu panjang.
-   [ ] Jangan mengubah kata hanya demi memenuhi batas karakter.
-   [ ] Pastikan baris kosong memisahkan setiap cue.
-   [ ] Validasi file hasil dengan parser SRT atau tes internal.
-   [ ] Sediakan nama output otomatis berdasarkan nama video.
-   [ ] Jangan menimpa file yang sudah ada tanpa konfirmasi.

**Contoh format:**

``` srt
1
00:00:01,200 --> 00:00:03,500
こんにちは。皆さん、ようこそ。

2
00:00:03,600 --> 00:00:06,200
今日はこのテーマについて説明します。
```

## Tahap 8 --- Terjemahan opsional ke Bahasa Indonesia

Transkripsi dan terjemahan harus menjadi dua tahap terpisah.

-   [x] Buat antarmuka `TranslationService` yang terpisah dari Whisper.
-   [x] Input penerjemah adalah daftar teks cue; timestamp tidak dikirim
    sebagai teks yang boleh diubah.
-   [x] Pertahankan ID cue dan timestamp sumber.
-   [x] Sediakan mode transkripsi video dan terjemahan SRT ke Indonesia.
-   [ ] Sediakan pilihan untuk menyimpan dua file: `video.ja.srt` dan
    `video.id.srt`.
-   [ ] Uji agar nama karakter dan istilah khusus tidak berubah
    sembarangan.
-   [ ] Tangani batas konteks model penerjemah dengan mengirim batch
    teks yang wajar.
-   [x] Simpan hasil terjemahan terpisah agar dapat dibuat ulang tanpa
    transkripsi ulang.
-   [ ] Jangan menganggap hasil terjemahan otomatis setara dengan
    terjemahan profesional.

**Pemilihan model penerjemah:** versi ini memakai Argos Translate lokal.
Paket bahasa yang diperlukan diunduh saat terjemahan pertama dan dipakai
secara offline setelah terpasang. Untuk bahasa Jepang/Korea, rute saat ini
melewati bahasa Inggris sebelum ke Bahasa Indonesia.

## Tahap 9 --- GUI desktop

### Layout utama

``` text
+------------------------------------------------------------------+
| VIDEO SUBTITLE TOOL                              [Settings]      |
+------------------------------------------------------------------+
| Input Video                                                       |
| [ D:\Videos\sample.mkv                         ] [Browse...]     |
| Durasi: 02:35:18   Audio: Japanese   Size: 4.2 GB                |
+------------------------------------------------------------------+
| Transcription                                                     |
| Language: [Auto v]    Model: [Large-v3 Turbo Q5 v]               |
| Device:   [Vulkan GPU v]  [ ] CPU fallback                       |
| Segment:  [20 minutes v]  Overlap: [2 seconds]                   |
+------------------------------------------------------------------+
| Output                                                            |
| (o) Original language   ( ) Translate to Indonesian              |
| Folder: [D:\Videos\Subtitles                    ] [Browse...]     |
+------------------------------------------------------------------+
| [Start] [Pause] [Cancel] [Resume]                                 |
| Stage: Transcribing segment 4 / 8                                 |
| [########################................] 61%                    |
| Current segment: 01:00:00 - 01:20:00                              |
| Backend: Vulkan GPU                                                |
+------------------------------------------------------------------+
| Log / Messages                                                    |
| 10:21:03 Segment 1 completed                                      |
| 10:25:42 Segment 2 completed                                      |
+------------------------------------------------------------------+
| [Open Output Folder] [Preview SRT]                                |
+------------------------------------------------------------------+
```

### TODO GUI

-   [ ] Buat jendela utama dengan panel input, pengaturan, progress,
    log, dan output.
-   [ ] Tambahkan drag-and-drop video.
-   [ ] Tambahkan validasi ekstensi dan file.
-   [ ] Tampilkan metadata video dan bahasa audio (jika dapat
    dideteksi).
-   [ ] Buat dropdown bahasa dan model.
-   [ ] Tampilkan backend yang benar-benar digunakan.
-   [ ] Tampilkan progress tahap dan progress keseluruhan.
-   [ ] Tampilkan segmen yang sedang diproses.
-   [ ] Tambahkan tombol Start, Cancel, Resume, dan Open Output Folder.
-   [ ] Gunakan worker/thread agar GUI tidak freeze.
-   [ ] Minta konfirmasi sebelum membatalkan pekerjaan.
-   [ ] Tampilkan pesan error yang dapat dipahami, dengan opsi membuka
    log.
-   [ ] Buat preview teks SRT setelah proses selesai.
-   [ ] Sediakan pengaturan lanjutan pada dialog terpisah.

## Tahap 10 --- Ketahanan, resume, dan manajemen file

-   [ ] Simpan manifest job ke JSON atau SQLite.
-   [ ] Simpan status setiap segmen (`pending`, `running`, `completed`,
    `failed`).
-   [ ] Simpan hasil transkripsi segmen yang selesai secara atomik.
-   [ ] Ketika aplikasi dibuka kembali, tampilkan job yang belum
    selesai.
-   [ ] Resume hanya segmen yang belum selesai atau gagal.
-   [ ] Pastikan cancel menghentikan proses anak FFmpeg/Whisper dengan
    benar.
-   [ ] Bersihkan file sementara setelah sukses sesuai preferensi.
-   [ ] Pertahankan file sementara jika job gagal agar dapat dianalisis
    atau dilanjutkan.
-   [ ] Beri opsi hapus cache/job lama.
-   [ ] Jangan menghapus video sumber.
-   [ ] Tangani nama file duplikat dengan suffix aman.

## Tahap 11 --- Pengujian

### Unit test

-   [ ] Timestamp detik ke SRT.
-   [ ] Timestamp jam lebih dari 1.
-   [ ] Durasi cue nol/negatif.
-   [ ] Cue terurut.
-   [ ] Encoding Jepang dan Korea.
-   [ ] Penomoran cue.
-   [ ] Penambahan offset segmen.
-   [ ] Penghapusan duplikasi overlap.
-   [ ] Penamaan file output.

### Integration test

-   [ ] MP4 dengan satu track audio.
-   [ ] MKV dengan beberapa track audio.
-   [ ] Video tanpa audio.
-   [ ] Audio mono dan stereo.
-   [ ] Video singkat 1--2 menit.
-   [ ] Video 30 menit.
-   [ ] Video 2--3 jam.
-   [ ] Audio bahasa Jepang.
-   [ ] Audio bahasa Inggris.
-   [ ] Audio bahasa Korea.
-   [ ] Audio campuran bahasa.
-   [ ] GPU Vulkan tersedia.
-   [ ] GPU tidak tersedia dan CPU fallback aktif.
-   [ ] Aplikasi ditutup saat job berjalan lalu dibuka kembali.
-   [ ] Satu segmen gagal dan dapat diulang.

### Pengukuran kualitas dan performa

-   [ ] Catat durasi audio.
-   [ ] Catat waktu transkripsi.
-   [ ] Hitung RTF (waktu proses dibagi durasi audio).
-   [ ] Catat penggunaan VRAM puncak.
-   [ ] Catat penggunaan RAM puncak.
-   [ ] Catat penggunaan CPU/GPU.
-   [ ] Bandingkan hasil model dengan sampel transkrip referensi.
-   [ ] Gunakan WER/CER bila tersedia transkrip acuan.
-   [ ] Catat kesalahan khusus bahasa Jepang seperti nama, partikel, dan
    kata yang mirip bunyi.
-   [ ] Bandingkan model dan quantization sebelum memilih preset
    default.

## Tahap 12 --- Packaging dan distribusi

-   [ ] Buat konfigurasi path relatif untuk binary dan model.
-   [ ] Tentukan apakah FFmpeg dan whisper.cpp dibundel atau diminta
    dipasang terpisah.
-   [ ] Periksa lisensi aplikasi, model, FFmpeg, dan komponen pihak
    ketiga sebelum distribusi.
-   [ ] Buat build Windows menggunakan PyInstaller setelah aplikasi
    stabil.
-   [ ] Jangan bundel model besar ke executable utama; sediakan
    unduhan/pemilihan model lokal.
-   [ ] Tampilkan pemeriksaan dependensi saat aplikasi pertama kali
    dibuka.
-   [ ] Buat README instalasi dan troubleshooting.
-   [ ] Uji pada Windows 11 dengan akun pengguna biasa.
-   [ ] Pastikan aplikasi dapat berjalan dari folder dengan spasi pada
    path.

------------------------------------------------------------------------

## 6. Kebijakan pemrosesan video panjang

### Rekomendasi awal

1.  Probe file video.
2.  Ekstrak audio sekali ke WAV mono 16 kHz.
3.  Segmentasikan audio menjadi 15--20 menit dengan overlap 1--3 detik.
4.  Proses satu segmen pada satu waktu menggunakan GPU.
5.  Simpan hasil segmen langsung setelah selesai.
6.  Tambahkan offset awal segmen ke semua timestamp.
7.  Gabungkan dan deduplikasi teks pada overlap.
8.  Jalankan formatting subtitle.
9.  Jika diminta, terjemahkan teks sebagai tahap terpisah.
10. Ekspor SRT dan simpan manifest job.

### Mengapa tidak memproses seluruh video sekaligus?

-   Video panjang dapat memerlukan waktu dan sumber daya besar.
-   Kegagalan di akhir proses berisiko membuat seluruh pekerjaan harus
    diulang jika tidak ada checkpoint.
-   Segmentasi mempermudah retry dan resume.
-   Timestamp global tetap dapat dipertahankan melalui offset segmen.

### Catatan audio dan jeda

-   Jangan menghapus semua keheningan secara permanen sebelum
    transkripsi karena hal itu dapat menggeser timestamp.
-   Jika menggunakan VAD, pastikan hasil timestamp dipetakan kembali ke
    posisi audio asli.
-   Simpan offset dan rentang setiap potongan audio.
-   Overlap perlu dideduplikasi dengan hati-hati agar pengulangan dialog
    yang nyata tidak hilang.

------------------------------------------------------------------------

## 7. Pengaturan default awal

  Pengaturan            Nilai awal
  --------------------- -----------------------------------------------
  Language              Auto
  Model                 Large-v3 Turbo, quantization yang telah diuji
  Backend               Vulkan jika terdeteksi
  Fallback              CPU
  Audio sample rate     16.000 Hz
  Audio channels        Mono
  Segment length        20 menit
  Overlap               2 detik
  Concurrent GPU jobs   1
  VAD                   Dapat diaktifkan/nonaktifkan
  Output encoding       UTF-8
  Output mode           Bahasa asli
  Translation           Nonaktif secara default
  Temporary files       Simpan sampai job sukses

Nilai di atas adalah preset awal untuk benchmark, bukan jaminan performa
atau akurasi. Turunkan model atau quantization jika VRAM/RAM tidak
cukup.

------------------------------------------------------------------------

## 8. Risiko teknis dan mitigasi

  -----------------------------------------------------------------------
  Risiko                  Dampak                  Mitigasi
  ----------------------- ----------------------- -----------------------
  Binary Whisper tidak    GPU tidak digunakan     Verifikasi build dan
  memiliki Vulkan                                 backend saat startup

  VRAM 8 GB tidak cukup   Gagal load atau lambat  Gunakan quantization
  untuk model/preset                              lebih kecil atau model
  tertentu                                        Medium

  RAM 16 GB penuh         Sistem melambat         Satu job GPU, batasi
                                                  cache, jangan memuat
                                                  model lain bersamaan

  Driver GPU bermasalah   Inferensi gagal         Log error, fallback
                                                  CPU, dokumentasikan
                                                  versi driver

  Audio terpotong di      Kata hilang             Overlap dan pemeriksaan
  batas segmen                                    hasil batas

  Timestamp bergeser      Subtitle tidak sinkron  Simpan offset dan
                                                  pemetaan waktu asli

  VAD membuang bagian     Kata hilang             Opsi nonaktif VAD dan
  ucapan                                          pengujian bahasa

  Deteksi bahasa salah    Teks tidak akurat       Pilihan bahasa manual

  Nama karakter salah     Subtitle keliru         Kamus istilah dan
                                                  pemeriksaan manual

  Penerjemah mengubah     Terjemahan buruk        Pisahkan tahap dan
  makna                                           pertahankan teks asli

  Aplikasi tertutup       Pekerjaan hilang        Manifest dan checkpoint
  mendadak                                        per segmen

  Path file mengandung    Perintah gagal          Gunakan subprocess
  karakter khusus                                 dengan argumen list,
                                                  bukan string shell
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 9. Kriteria MVP (versi pertama dianggap selesai)

MVP dinyatakan selesai jika: - \[ \] GUI dapat membuka file video. - \[
\] Metadata dan track audio dapat dibaca. - \[ \] Audio diekstrak dengan
FFmpeg. - \[ \] Model Whisper dapat dijalankan melalui Vulkan pada RX
7600, atau CPU fallback bila Vulkan tidak tersedia. - \[ \] Bahasa Auto
dan Japanese manual berfungsi. - \[ \] Video panjang diproses per
segmen. - \[ \] Timestamp global tetap sinkron dengan video. - \[ \]
File SRT UTF-8 valid dihasilkan. - \[ \] Progress dan log tampil di
GUI. - \[ \] Job dapat dilanjutkan setelah aplikasi ditutup atau satu
segmen gagal. - \[ \] File Jepang tampil dengan benar pada editor/player
subtitle.

**MVP tidak wajib memiliki penerjemahan.** Prioritaskan transkripsi yang
stabil, timestamp yang benar, penggunaan GPU yang terverifikasi, dan
pemrosesan video panjang yang dapat dilanjutkan.

