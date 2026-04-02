import os
import random
import datasets
import requests

_NAMES = {
    "all": ["m_chest", "f_chest", "m_falsetto", "f_falsetto"],
    "gender": ["female", "male"],
    "singing_method": ["falsetto", "chest"],
}

_HOME = f"https://www.modelscope.cn/datasets/ccmusic-database/{os.path.basename(__file__)[:-3]}"

_URL = f"{_HOME}/resolve/master/data"

_URLS = {
    "audio": f"{_URL}/audio.zip",
    "mel": f"{_URL}/mel.zip",
    "eval": f"{_URL}/eval.zip",
}


class chest_falsetto(datasets.GeneratorBasedBuilder):
    def _info(self):
        return datasets.DatasetInfo(
            features=(
                datasets.Features(
                    {
                        "audio": datasets.Audio(sampling_rate=22050),
                        "mel": datasets.Image(),
                        "label": datasets.features.ClassLabel(names=_NAMES["all"]),
                        "gender": datasets.features.ClassLabel(names=_NAMES["gender"]),
                        "singing_method": datasets.features.ClassLabel(
                            names=_NAMES["singing_method"]
                        ),
                    }
                )
                if self.config.name == "default"
                else datasets.Features(
                    {
                        "mel": datasets.Image(),
                        "cqt": datasets.Image(),
                        "chroma": datasets.Image(),
                        "label": datasets.features.ClassLabel(names=_NAMES["all"]),
                        "gender": datasets.features.ClassLabel(names=_NAMES["gender"]),
                        "singing_method": datasets.features.ClassLabel(
                            names=_NAMES["singing_method"]
                        ),
                    }
                )
            ),
            supervised_keys=("mel", "label"),
            license="CC-BY-NC-ND",
            version="1.2.0",
            homepage=_HOME,
        )

    def _download_and_extract(self, dl_manager: datasets.DownloadManager, lnk: str):
        try:
            return dl_manager.download_and_extract(lnk)
        except Exception as e:
            print(f"{e}, retrying...")
            return dl_manager.download_and_extract(
                requests.head(lnk, allow_redirects=True).url
            )

    def _split_generators(self, dl_manager):
        dataset = []
        if self.config.name == "default":
            files = {}
            audio_files = self._download_and_extract(dl_manager, _URLS["audio"])
            for fpath in dl_manager.iter_files([audio_files]):
                fname: str = os.path.basename(fpath)
                if fname.endswith(".wav"):
                    i = fname.split(".")[0]
                    files[i] = {"audio": fpath}

            img_files = self._download_and_extract(dl_manager, _URLS["mel"])
            for fpath in dl_manager.iter_files([img_files]):
                fname: str = os.path.basename(fpath)
                if fname.endswith(".jpg"):
                    i = fname.split(".")[0]
                    if files[i]:
                        files[i]["mel"] = fpath

            dataset = list(files.values())

        else:
            data_files = self._download_and_extract(dl_manager, _URLS["eval"])
            for fpath in dl_manager.iter_files([data_files]):
                if "mel" in fpath and os.path.basename(fpath).endswith(".jpg"):
                    dataset.append(fpath)

        categories = {}
        for i in _NAMES["all"]:
            categories[i] = []

        for data in dataset:
            fpath = data["audio"] if self.config.name == "default" else data
            fname: str = os.path.basename(fpath)[:-4]
            i = "_".join(fname.split("_")[1:3])
            categories[i].append(data)

        testset, validset, trainset = [], [], []
        for i in categories:
            random.shuffle(categories[i])
            count = len(categories[i])
            p60 = int(count * 0.6)
            p80 = int(count * 0.8)
            trainset += categories[i][:p60]
            validset += categories[i][p60:p80]
            testset += categories[i][p80:]

        random.shuffle(trainset)
        random.shuffle(validset)
        random.shuffle(testset)

        return [
            datasets.SplitGenerator(
                name=datasets.Split.TRAIN, gen_kwargs={"files": trainset}
            ),
            datasets.SplitGenerator(
                name=datasets.Split.VALIDATION, gen_kwargs={"files": validset}
            ),
            datasets.SplitGenerator(
                name=datasets.Split.TEST, gen_kwargs={"files": testset}
            ),
        ]

    def _generate_examples(self, files):
        if self.config.name == "default":
            for i, data in enumerate(files):
                fname = os.path.basename(data["audio"])
                sex = fname.split("_")[1]
                method = fname.split("_")[2].split(".")[0]
                yield i, {
                    "audio": data["audio"],
                    "mel": data["mel"],
                    "label": f"{sex}_{method}",
                    "gender": "male" if sex == "m" else "female",
                    "singing_method": method,
                }

        else:
            for i, fpath in enumerate(files):
                fname: str = os.path.basename(fpath)
                sex = fname.split("_")[1]
                method = fname.split("_")[2]
                mel_path: str = fpath
                yield i, {
                    "mel": mel_path,
                    "cqt": mel_path.replace("mel", "cqt"),
                    "chroma": mel_path.replace("mel", "chroma"),
                    "label": f"{sex}_{method}",
                    "gender": "male" if sex == "m" else "female",
                    "singing_method": method,
                }
