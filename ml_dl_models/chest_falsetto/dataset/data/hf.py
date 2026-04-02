from modelscope.msdatasets import MsDataset


def create_arrows(
    script_name: str,
    subsets=["default", "eval"],
    cache_dir="./__pycache__",
):
    for subset in subsets:
        ds = MsDataset.load(script_name, subset_name=subset, cache_dir=cache_dir)
        ds.save_to_disk(f"{cache_dir}/data/{subset}")


if __name__ == "__main__":
    create_arrows("ccmusic-database/chest_falsetto")
