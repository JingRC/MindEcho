import librosa
import numpy as np
import matplotlib.pyplot as plt
from modelscope.msdatasets import MsDataset
from tqdm import tqdm

plt.rcParams["font.sans-serif"] = "Times New Roman"
CACHE_DIR = "F://"
LABEL_NAMES = [
    "Chest Voice\nMale",
    "Chest Voice\nFemale",
    "Falsetto\nMale",
    "Falsetto\nFemale",
]


def func(pct, allvals):
    absolute = round(pct / 100.0 * sum(allvals))
    return f"{pct:.1f}%\n({absolute})"


def draw_pie_chart(
    labels: list,
    sizes: list,
    filename: str = "./data/falsetto.pdf",
    label_fontsize: int = 16,  # 修改标签字号
    autopct_fontsize: int = 16,  # 修改百分比字号
):
    class_num = len(labels)
    cmap = plt.get_cmap("Set2")
    colors = [cmap(i / class_num) for i in range(class_num)]
    _, ax = plt.subplots()
    wedges, _, autotexts = ax.pie(
        sizes,
        labels=labels,
        autopct=lambda pct: func(pct, sizes),
        startangle=222,
        textprops={"fontsize": label_fontsize},
        colors=colors,
    )
    for wedge in wedges:
        wedge.set_edgecolor("black")

    for autotext in autotexts:
        autotext.set_fontsize(autopct_fontsize)  # 设置百分比字号

    ax.axis("equal")
    plt.savefig(filename, bbox_inches="tight")
    plt.close()


def plot():
    ds = MsDataset.load(
        "ccmusic-database/chest_falsetto",
        subset_name="eval",
        cache_dir=CACHE_DIR,
        trust_remote_code=True,
    )
    classes = ds["test"].features["label"].names
    statistics = {}
    data_count = 0
    for cls in classes:
        statistics[cls] = 0

    for item in tqdm(ds["train"], desc="Statistics are in progress..."):
        statistics[classes[item["label"]]] += 1
        data_count += 1

    for item in tqdm(ds["validation"], desc="Statistics are in progress..."):
        statistics[classes[item["label"]]] += 1
        data_count += 1

    for item in tqdm(ds["test"], desc="Statistics are in progress..."):
        statistics[classes[item["label"]]] += 1
        data_count += 1

    sizes = list(statistics.values())
    print(data_count, sizes)
    draw_pie_chart(LABEL_NAMES, sizes)


def draw_bar(
    labels: list,
    category_counts: list,
    filename="./data/bar.pdf",
    aspect_ratio: float = 1.618,
    label_fontsize: int = 32,
    tick_fontsize: int = 30,
    txt_fontsize: int = 28,
):
    x = np.arange(len(labels))
    # 绘制条形图
    plt.figure(figsize=(6 * aspect_ratio, 6))
    plt.bar(
        x,
        category_counts,
        align="center",
        color="cyan",
        edgecolor="black",
    )
    plt.xticks(x, labels, rotation=45, ha="right", fontsize=tick_fontsize)
    plt.yticks(fontsize=tick_fontsize)
    plt.ylabel("Duration(s)", fontsize=label_fontsize)
    # 显示数值
    for i, count in enumerate(category_counts):
        plt.text(
            x[i],
            count * 0.5,
            round(count, 2),
            ha="center",
            va="center",
            fontsize=txt_fontsize,
        )

    plt.tight_layout()
    plt.savefig(filename, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    ds = MsDataset.load(
        "ccmusic-database/chest_falsetto",
        subset_name="default",
        cache_dir=CACHE_DIR,
        # download_mode="force_redownload",
        trust_remote_code=True,
    )
    durs, counts = [0, 0, 0, 0], [0, 0, 0, 0]
    min_dur, max_dur = 1, 0
    for item in tqdm(ds["train"], desc="Loading trainset..."):
        counts[item["label"]] += 1
        dur = librosa.get_duration(filename=item["audio"]["path"])
        durs[item["label"]] += dur
        if dur < min_dur:
            min_dur = dur

        if dur > max_dur:
            max_dur = dur

    for item in tqdm(ds["validation"], desc="Loading validset..."):
        counts[item["label"]] += 1
        dur = librosa.get_duration(filename=item["audio"]["path"])
        durs[item["label"]] += dur
        if dur < min_dur:
            min_dur = dur

        if dur > max_dur:
            max_dur = dur

    for item in tqdm(ds["test"], desc="Loading testset..."):
        counts[item["label"]] += 1
        dur = librosa.get_duration(filename=item["audio"]["path"])
        durs[item["label"]] += dur
        if dur < min_dur:
            min_dur = dur

        if dur > max_dur:
            max_dur = dur

    draw_pie_chart(LABEL_NAMES, counts, "./data/falsetto_pie.pdf")
    draw_bar(LABEL_NAMES, durs, "./data/falsetto_bar.pdf")
    print(
        "| 总数据量 Total count | 总时长(秒) Total duration(s) | 最短时长(秒) Min duration(s) | 最长时长(秒) Max duration(s) |"
    )
    print("| :--: | :--: | :--: | :--: |")
    print(f"| `{sum(counts)}` | `{sum(durs)}` | `{min_dur}` | `{max_dur}` |")
