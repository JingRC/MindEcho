---
license: CC-BY-NC-ND
audio:
  audio-classification:
    size_scale:
      - 100-10k
tags:
  - art
  - music
  - classification
  - singing
---

# 简介 Dataset Card for Chest voice and Falsetto Dataset
原始数据集来源于 [真假声数据集](https://ccmusic-database.github.io/database/ccm.html#shou3)，包含 1,280 个单音演唱音频文件，格式为 .wav，由中国音乐学院声乐专业的学生演唱、录制并注释。真声被标记为“chest”，假声被标记为“falsetto”。数据集还包括Mel频谱图、Mel 频率倒谱系数 (MFCC) 和每个音频段的频谱特征，共产生 5,120 个 CSV 文件。

原始数据集未区分男女声，这对于准确识别真声和假声技巧至关重要。为解决这一问题，我们进行了仔细的手动审核，并为数据集添加了性别注释。处理后，构建了当前集成版数据集的 [默认子集](#快速使用-usage)，其数据结构可在 [数据预览](https://www.modelscope.cn/datasets/ccmusic-database/chest_falsetto/dataPeview) 中查看。默认子集未经校验，为验证集成版数据集的有效性，我们基于默认子集构建了 [校验子集](#快速使用-usage) 并完成了校验，校验结果可在 [歌唱真假声分类模型](https://www.modelscope.cn/models/ccmusic-database/chest_falsetto) 中查看。以下是集成版数据集各个子数据集的数据结构简介。

The original dataset, sourced from the [Chest Voice and Falsetto Dataset](https://ccmusic-database.github.io/en/database/ccm.html#shou3), includes 1,280 monophonic singing audio files in .wav format, performed, recorded, and annotated by students majoring in Vocal Music at the China Conservatory of Music. The chest voice is tagged as "chest" and the falsetto voice as "falsetto." Additionally, the dataset encompasses the Mel spectrogram, Mel frequency cepstral coefficient (MFCC), and spectral features of each audio segment, totaling 5,120 CSV files.

The original dataset did not distinguish between male and female voices, a critical detail for accurately identifying chest and falsetto vocal techniques. To correct this, we undertook a careful manual review and added gender annotations to the dataset. Following this process, we constructed the [default subset](#快速使用-usage) of the current integrated version of the dataset, viewable in [viewer](https://www.modelscope.cn/datasets/ccmusic-database/chest_falsetto/dataPeview). As the default subset had not undergone evaluation, we created the [eval subset](#快速使用-usage) from it to verify the integrated dataset's effectiveness and completed the evaluation, viewable at [chest_falsetto](https://www.modelscope.cn/models/ccmusic-database/chest_falsetto). Below is a brief overview of the data structure for each subset within the integrated dataset.

## 数据结构 Dataset Structure
### 默认子集 Default Subset Structure
<table>
    <tr>
        <th>audio</th>
        <th>mel (spectrogram)</th>
        <th>label (4-class)</th>
        <th>gender (2-class)</th>
        <th>singing_method (2-class)</th>
    </tr>
    <tr>
        <td>.wav, 22050Hz</td>
        <td>.jpg, 22050Hz</td>
        <td>m_chest=0, m_falsetto=2, f_chest=1, f_falsetto=3</td>
        <td>male=1, female=0</td>
        <td>chest=1, falsetto=0</td>
    </tr>
</table>

### 校验子集 Eval Subset Structure
<table>
    <tr>
        <th>mel (spectrogram)</th>
        <th>cqt (spectrogram)</th>
        <th>chroma (spectrogram)</th>
        <th>label (4-class)</th>
        <th>gender (2-class)</th>
        <th>singing_method (2-class)</th>
    </tr>
    <tr>
        <td>.jpg, 0.496s, 22050Hz</td>
        <td>.jpg, 0.496s, 22050Hz</td>
        <td>.jpg, 0.496s, 22050Hz</td>
        <td>m_chest=0, m_falsetto=2, f_chest=1, f_falsetto=3</td>
        <td>male=1, female=0</td>
        <td>chest=1, falsetto=0</td>
    </tr>
</table>

### 文件格式 Data Instances
.zip(.wav, .jpg)

### 标签 Data Fields
m_chest=0, f_chest=1, m_falsetto=2, f_falsetto=3

### 数据分割 Data Splits
| Split(6:2:2) / Subset |    default & eval    |
| :-------------------: | :------------------: |
|         train         |         767          |
|      validation       |         256          |
|         test          |         257          |
|         total         |        1,280         |
|   total duration(s)   | `640.0513605442178`  |
|    min duration(s)    | `0.4961451247165533` |
|    max duration(s)    | `0.5099773242630385` |

## 快速使用 Usage
:modelscope-code[]{type="sdk"}

## 维护 Maintenance
```bash
GIT_LFS_SKIP_SMUDGE=1 
```

:modelscope-code[]{type="git"}

### 环境(仅用于数据处理脚本) Requirements(Only for data processor)
```bash
cd data
echo y | conda create -n data python=3.x
conda activate data
pip install -r requirements.txt
```

### 数据处理脚本 Data processor
1. Open project with `VSCode`
2. Select file `./data/data.py`
3. Press `F5`

## 数据集描述 Dataset Description
### 数据集总结 Dataset Summary
For the pre-processed version, the audio clip was into 0.25 seconds and then transformed to Mel, CQT and Chroma spectrogram in .jpg format, resulting in 8,974 files. The chest/falsetto label for each file is given as one of the four classes: m chest, m falsetto, f chest, and f falsetto. The spectrogram, the chest/falsetto label and the gender label are combined into one data entry, with the first three columns representing the Mel, CQT and Chroma. The fourth and fifth columns are the chest/falsetto label and gender label, respectively. Additionally, the integrated dataset provides the function to shuffle and split the dataset into training, validation, and test sets in an 8:1:1 ratio. This dataset can be used for singing-related tasks such as singing gender classification or chest and falsetto voice classification.

### 支持任务 Supported Tasks and Leaderboards
Audio classification, singing method classification, voice classification

### 语言 Languages
Chinese, English

## 数据集创建 Dataset Creation
### 动机 Curation Rationale
Lack of a dataset for Chest voice and Falsetto

### 数据源 Source Data
#### 源数据搜集与正规化 Initial Data Collection and Normalization
Zhaorui Liu, Monan Zhou

#### 语言支持 Who are the source language producers?
Students from CCMUSIC

### 标注 Annotations
#### 标注步骤 Annotation process
1280 monophonic singing audio (.wav format) of chest and falsetto voices, with chest voice tagged as _chest_ and falsetto voice tagged as _falsetto_.

#### 标注者 Who are the annotators?
Students from CCMUSIC

## 数据使用考量 Considerations for Using the Data
### 社会影响 Social Impact of Dataset
Promoting the development of AI in the music industry

### 偏好 Discussion of Biases
Only for chest and falsetto voices

### 其它限制 Other Known Limitations
Recordings are cut into slices that are too short;
The CQT spectrum column has the problem of spectrum leakage, but because the original audio slice is too short, only 0.5s, it cannot effectively avoid this problem.

## 附加信息 Additional Information
### 策划人 Dataset Curators
Zijin Li

### 镜像 Mirror
<https://huggingface.co/datasets/ccmusic-database/chest_falsetto>

### 校验 Evaluation
<https://www.modelscope.cn/models/ccmusic-database/chest_falsetto>

### 引用 Cite
```bibtex
@dataset{zhaorui_liu_2021_5676893,
  author    = {Zhaorui Liu and Zijin Li},
  title     = {Music Data Sharing Platform for Computational Musicology Research (CCMUSIC DATASET)},
  month     = {nov},
  year      = {2021},
  publisher = {Zenodo},
  version   = {1.1},
  doi       = {10.5281/zenodo.5676893},
  url       = {https://doi.org/10.5281/zenodo.5676893}
}
```

### 贡献 Contributions
Provide a dataset for distinguishing chest and falsetto voices

<div style="display:none">