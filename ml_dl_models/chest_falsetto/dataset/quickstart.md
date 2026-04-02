## 数据集: ccmusic-database/chest_falsetto

```python
from modelscope.msdatasets import MsDataset

ds = MsDataset.load(
    "ccmusic-database/chest_falsetto",
    subset_name="default",  # default / eval
    split="train",  # train / validation / test
    cache_dir="./__pycache__",
    trust_remote_code=True,
)
for i in ds:
    print(i)
```