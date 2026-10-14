import os
import subprocess
import win32com.client
import wave

# Slide narration scripts in English
NARRATIONS = [
    # Slide 1
    "Welcome to the official presentation of HGTTD: Hitchhiker's Guide through the Database. "
    "HGTTD is an interactive, standalone desktop suite for spectroscopy, molecular structure elucidation, and chemical artificial intelligence.",

    # Slide 2
    "Spectroscopy and structure elucidation face persistent challenges: fragmented data silos, incompatible file formats, "
    "and tedious manual peak assignments. HGTTD unifies over 5.2 million experimental and quantum spectra in an intuitive, fully offline platform.",

    # Slide 3
    "HGTTD is built on massive scientific foundations: 3.37 million NMR spectra from NMRexp across 6 nuclei, "
    "1.75 million mass spectra from MoNa, 133,000 infrared spectra from SQuIRL and NIST, and 54,000 3D molecular structures from nmrshiftdb2.",

    # Slide 4
    "The application integrates the modern EPAM Ketcher 2D chemical editor directly into the desktop workspace. "
    "Draw complex molecules with ease, enjoy full bilingual support in English and German, and leverage responsive keyboard shortcuts.",

    # Slide 5
    "Search chemical spaces with unparalleled speed. Perform exact structure queries in under 5 milliseconds, "
    "substructure searches with atom-accurate cyan highlighting, or Tanimoto similarity searches powered by 2048-bit Morgan circular fingerprints.",

    # Slide 6
    "Experience a 60-frames-per-second real-time NMR spectrum synthesizer. Features include continuous Lorentzian convolution, "
    "Pascal splitting trees, full multi-nucleus support, cumulative step integrals, and an inverted mirror plot for side-by-side isomer comparison.",

    # Slide 7
    "Accelerate your workflow with AI-driven peak auto-assignment. Powered by Wavefunction's DLNMR1 deep learning model, "
    "HGTTD predicts quantum chemical shifts in under 20 milliseconds on standard desktop CPUs, coupled with a pure NumPy bipartite matching solver.",

    # Slide 8
    "Dive into 1.75 million mass spectra from MoNa. Explore high-resolution LC-MS/MS and GC-MS data with our color-coded stick viewer, "
    "noise cutoff filtering, and an interactive neutral-loss calculator for instantaneous delta mass diagnosis.",

    # Slide 9
    "Analyze infrared spectra from the SQuIRL quantum dataset and the NIST WebBook. "
    "Toggle smoothly between transmittance and absorbance, adjust Lorentzian linewidths, and leverage automatic diagnostic band overlays for functional groups.",

    # Slide 10
    "Inspect 3D molecular conformations with hardware-accelerated WebGL powered by 3Dmol.js. "
    "Enjoy live cross-highlighting between NMR peaks and 3D atoms, and watch animated MMFF94 force field energy minimizations fold molecules in real time.",

    # Slide 11
    "Organize your research seamlessly with the persistent SQLite research logbook. "
    "Bookmark favorites, review your history, add tags, and generate publication-ready A4 Certificates of Analysis in HTML and PDF with a single click.",

    # Slide 12
    "Under the hood, HGTTD combines PySide6 Qt6, Apache Parquet with Snappy compression, RDKit, PyTorch CPU, "
    "and pure NumPy solvers, ensuring maximum reliability, zero cloud dependency, and complete privacy for intellectual property.",

    # Slide 13
    "HGTTD empowers synthetic chemists verifying reaction outcomes, analytical scientists deconvoluting complex metabolomics samples, "
    "and university educators bringing spectroscopic theory to life in the classroom.",

    # Slide 14
    "In summary, HGTTD brings 5.2 million spectra, on-device AI inference, and rich interactive visualization together into one free, open-source tool. "
    "Don't panic — explore your chemistry with HGTTD today!"
]

def generate_voiceover_wav(text, output_wav_path):
    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    # Select English voice (David or Zira)
    voices = speaker.GetVoices()
    for i in range(voices.Count):
        v = voices.Item(i)
        desc = v.GetDescription()
        if "David" in desc or "Zira" in desc or "English" in desc:
            speaker.Voice = v
            break
    
    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    # 39 = SAFT44kHz16BitStereo or standard WAV
    stream.Format.Type = 39 
    stream.Open(output_wav_path, 3, False) # 3 = SSFMCreateForWrite
    speaker.AudioOutputStream = stream
    speaker.Speak(text)
    stream.Close()

def get_wav_duration(wav_path):
    with wave.open(wav_path, 'r') as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / float(rate)

def build_video():
    slide_dir = os.path.abspath("video_temp_slides/slide")
    out_dir = os.path.abspath("video_build")
    os.makedirs(out_dir, exist_ok=True)

    slide_files = [f"Folie{i}.JPG" for i in range(1, 15)]
    segment_videos = []

    print("Generating voiceovers and rendering slide video segments...")
    for idx, (slide_file, narration) in enumerate(zip(slide_files, NARRATIONS), start=1):
        slide_img = os.path.join(slide_dir, slide_file)
        wav_file = os.path.join(out_dir, f"audio_{idx:02d}.wav")
        segment_mp4 = os.path.join(out_dir, f"segment_{idx:02d}.mp4")

        print(f"[{idx}/14] Voiceover for Slide {idx}...")
        generate_voiceover_wav(narration, wav_file)
        duration = get_wav_duration(wav_file) + 1.2 # extra 1.2s padding for smooth pacing

        # Render slide image + audio into mp4 segment using ffmpeg
        # Scale to 1920x1080 Full HD
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", slide_img,
            "-i", wav_file,
            "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0f172a",
            "-t", f"{duration:.3f}",
            segment_mp4
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        segment_videos.append(segment_mp4)

    # Concat all segments
    concat_list_path = os.path.join(out_dir, "concat_list.txt")
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for seg in segment_videos:
            clean_p = seg.replace("\\", "/")
            f.write(f"file '{clean_p}'\n")

    final_output = os.path.abspath("HGTTD_Introduction_Video.mp4")
    print(f"Concatenating all segments into {final_output}...")
    concat_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        final_output
    ]
    subprocess.run(concat_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Video generation completed successfully!")

if __name__ == "__main__":
    build_video()
