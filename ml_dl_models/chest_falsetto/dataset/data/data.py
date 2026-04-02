import os
import time
import shutil
import librosa
import zipfile
import requests
import matplotlib
import numpy as np
from tqdm import tqdm
from multiprocessing import Pool
from matplotlib import pyplot as plt

SAMPLE_RATE = 22050


def failist(text_to_write, file_name="./data/failist.txt"):
    print(text_to_write)
    with open(file_name, "a", encoding="utf-8") as file:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        file.write(f"[{timestamp}]{text_to_write}\n")


# zip
def compress(folder_path, zip_file_path):
    if not os.path.exists(folder_path):
        failist(f"Error: Folder '{folder_path}' does not exist.")
        return
    # 打开 ZIP 文件，使用 'w' 模式表示写入
    with zipfile.ZipFile(
        zip_file_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9
    ) as zipf:
        # 遍历文件夹中的文件和子文件夹
        for root, _, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                # 计算相对路径，保留文件夹的根目录
                relative_path = os.path.relpath(file_path, folder_path)
                zipf.write(
                    file_path,
                    arcname=os.path.join(os.path.basename(folder_path), relative_path),
                )

    print(f"Compression complete. ZIP file created at: {zip_file_path}")


def extract_zip(zip_file_path, extract_folder):
    if not os.path.exists(zip_file_path):
        failist(f"Error: ZIP file '{zip_file_path}' does not exist.")
        return
    # 确保目标文件夹存在，如果不存在则创建
    if not os.path.exists(extract_folder):
        os.makedirs(extract_folder)
    # 打开 ZIP 文件
    with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
        # 解压缩到目标文件夹
        zip_ref.extractall(extract_folder)

    print(f"Extraction complete. Files extracted to: {extract_folder}")


def download_zip(url, save_path):
    response = requests.get(url, stream=True)  # 设置 stream=True 以便在下载时追踪进度
    # 获取文件大小
    file_size = int(response.headers.get("content-length", 0))
    # 使用 tqdm 创建进度条
    progress_bar = tqdm(total=file_size, unit="B", unit_scale=True)
    # 检查请求是否成功
    if response.status_code == 200:
        # 保存文件到本地
        with open(save_path, "wb") as file:
            for data in response.iter_content(chunk_size=1024):
                file.write(data)
                progress_bar.update(len(data))  # 更新进度条

        progress_bar.close()
        print(f"Download complete. File saved to: {save_path}")

    else:
        failist(
            f"Error: Unable to download file. HTTP status code: {response.status_code}"
        )


# data processor
def find_wav_files(directory):
    wav_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".wav"):
                wav_files.append(os.path.join(root, file))

    return wav_files


def wav2mel(y, sr: int, audio_path: str, width: float):
    audio_name = os.path.basename(audio_path)[:-4]
    mel_dir = os.path.dirname(audio_path).replace("/audio", "/eval/mel")
    mel_spec = librosa.feature.melspectrogram(y=y, sr=sr)
    log_mel_spec = librosa.power_to_db(mel_spec, ref=np.max)
    dur = librosa.get_duration(y=y, sr=sr)
    total_frames = log_mel_spec.shape[1]
    step = int(width * total_frames / dur)
    count = int(total_frames / step)
    begin = int(0.5 * (total_frames - count * step))
    end = begin + step * count
    for i in range(begin, end, step):
        librosa.display.specshow(log_mel_spec[:, i : i + step])
        plt.axis("off")
        plt.savefig(
            f"{mel_dir}/{audio_name}_{i}.jpg",
            bbox_inches="tight",
            pad_inches=0.0,
        )
        plt.close()


def wav2cqt(y, sr: int, audio_path: str, width: float):
    audio_name = os.path.basename(audio_path)[:-4]
    cqt_dir = os.path.dirname(audio_path).replace("/audio", "/eval/cqt")
    cqt_spec = librosa.cqt(y=y, sr=sr, fmin=librosa.note_to_hz("G1"))
    log_cqt_spec = librosa.power_to_db(np.abs(cqt_spec) ** 2, ref=np.max)
    dur = librosa.get_duration(y=y, sr=sr)
    total_frames = log_cqt_spec.shape[1]
    step = int(width * total_frames / dur)
    count = int(total_frames / step)
    begin = int(0.5 * (total_frames - count * step))
    end = begin + step * count
    for i in range(begin, end, step):
        librosa.display.specshow(log_cqt_spec[:, i : i + step])
        plt.axis("off")
        plt.savefig(
            f"{cqt_dir}/{audio_name}_{i}.jpg",
            bbox_inches="tight",
            pad_inches=0.0,
        )
        plt.close()


def wav2chroma(y, sr: int, audio_path: str, width: float):
    audio_name = os.path.basename(audio_path)[:-4]
    chroma_dir = os.path.dirname(audio_path).replace("/audio", "/eval/chroma")
    chroma_spec = librosa.feature.chroma_stft(y=y, sr=sr)
    log_chroma_spec = librosa.power_to_db(np.abs(chroma_spec) ** 2, ref=np.max)
    dur = librosa.get_duration(y=y, sr=sr)
    total_frames = log_chroma_spec.shape[1]
    step = int(width * total_frames / dur)
    count = int(total_frames / step)
    begin = int(0.5 * (total_frames - count * step))
    end = begin + step * count
    for i in range(begin, end, step):
        librosa.display.specshow(log_chroma_spec[:, i : i + step])
        plt.axis("off")
        plt.savefig(
            f"{chroma_dir}/{audio_name}_{i}.jpg",
            bbox_inches="tight",
            pad_inches=0.0,
        )
        plt.close()


def audio2img(y: np.ndarray, sr: int, audio_path: str):
    outpath, _ = os.path.splitext(audio_path)
    outpath = outpath.replace("/audio", "/mel") + ".jpg"
    mel_spec = librosa.feature.melspectrogram(y=y, sr=sr)
    log_mel_spec = librosa.power_to_db(mel_spec, ref=np.max)
    plt.figure()
    plt.axis("off")
    plt.imsave(outpath, log_mel_spec)
    plt.close()


def batch_convert(wav_files: list, seg_len=0.496145124716553):
    # min_dur = 0.4961451247165533
    for wav_file in tqdm(wav_files, desc="Converting wav to jpg..."):
        try:
            y, sr = librosa.load(wav_file, sr=SAMPLE_RATE)
            wav2mel(y, sr, wav_file, width=seg_len)
            wav2cqt(y, sr, wav_file, width=seg_len)
            wav2chroma(y, sr, wav_file, width=seg_len)
            audio2img(y, sr, wav_file)

        except Exception as e:
            failist(f"Error converting {wav_file} : {e}")


def split_by_cpu(items):
    num_cpus = os.cpu_count() - 1
    if num_cpus is None or num_cpus < 1:
        num_cpus = 1

    index = 0
    if type(items) == dict:
        split_items = [{} for _ in range(num_cpus)]
        for key, value in items.items():
            split_items[index][key] = value
            index = (index + 1) % num_cpus

    else:
        split_items = [[] for _ in range(num_cpus)]
        for item in items:
            split_items[index].append(item)
            index = (index + 1) % num_cpus

    return split_items, num_cpus


def multi_batch_convert(zipath="./data/audio.zip", multi=True):
    if (
        not os.path.exists(zipath) and not os.path.exists("./data/audio")
    ) or os.path.getsize(zipath) < 10_000_000:
        repo_name = os.path.basename(os.path.dirname(os.path.dirname(__file__)))
        download_zip(
            f"https://www.modelscope.cn/api/v1/datasets/ccmusic-database/{repo_name}/repo?Revision=master&FilePath=data/audio.zip",
            zipath,
        )

    if not os.path.exists("./data/audio"):
        extract_zip("./data/audio.zip", "./data")

    os.makedirs("./data/mel", exist_ok=True)
    os.makedirs("./data/eval/mel", exist_ok=True)
    os.makedirs("./data/eval/cqt", exist_ok=True)
    os.makedirs("./data/eval/chroma", exist_ok=True)
    wav_files = find_wav_files("./data/audio")
    if multi:
        batches, num_cpu = split_by_cpu(wav_files)
        with Pool(processes=num_cpu) as pool:
            pool.map(batch_convert, batches)

    else:
        batch_convert(wav_files)


def clean_caches():
    print("Cleaning caches...")
    shutil.rmtree("./data/mel", ignore_errors=True)
    shutil.rmtree("./data/eval", ignore_errors=True)
    shutil.rmtree("./data/audio", ignore_errors=True)


if __name__ == "__main__":
    matplotlib.use("Agg")
    clean_caches()
    multi_batch_convert()
    compress("./data/eval", "./data/eval.zip")
    compress("./data/mel", "./data/mel.zip")
    clean_caches()
