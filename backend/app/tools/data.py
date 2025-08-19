from pathlib import Path
import pandas as pd

def csv_head(path: str, n: int = 5, sep: str | None = None) -> dict:
    p = Path(path).expanduser().resolve()
    df = pd.read_csv(p, sep=sep)
    head = df.head(n)
    return {"columns": list(head.columns), "rows": head.astype(str).values.tolist(), "shape": list(df.shape)}

