import os

search_roots = [
    os.path.join(os.environ.get("USERPROFILE", ""), ".gemini"),
    os.path.join(os.environ.get("APPDATA", "")),
    os.path.join(os.environ.get("LOCALAPPDATA", "")),
]

target_str = "Select-String"
found = []

for sroot in search_roots:
    if not os.path.exists(sroot):
        continue
    for root, _dirs, files in os.walk(sroot):
        # Exclude transcripts and chat logs completely
        if any(
            x in root for x in ["brain", "transcripts", "logs", ".git", "Cache", "cache", "temp"]
        ):
            continue
        for f in files:
            if f.endswith((".json", ".yaml", ".yml")):
                fp = os.path.join(root, f)
                try:
                    with open(fp, encoding="utf-8", errors="ignore") as file_obj:
                        text = file_obj.read()
                        if target_str in text:
                            print(f"FOUND CONFIG: {fp}")
                            found.append(fp)
                except Exception:
                    pass

print("\nDONE. Total found:", len(found))
