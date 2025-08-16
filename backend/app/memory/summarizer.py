from typing import List

def summarize_turns(turns: List[str]) -> str:
    text = " ".join(turns)
    return (text[:1200] + "…") if len(text) > 1200 else text

