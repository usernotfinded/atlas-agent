import re

with open("src/atlas_agent/update/sources.py", "r") as f:
    content = f.read()

# Add is_public_stable
public_stable_func = """
def is_public_stable(value: str) -> bool:
    clean = strip_version_prefix(value)
    if Version is not None:
        try:
            v = Version(clean)
            return not (v.is_prerelease or v.is_devrelease)
        except InvalidVersion:
            pass
    lower = clean.lower()
    return "dev" not in lower and "rc" not in lower and "a" not in lower and "b" not in lower
"""

content = content.replace("def is_version_newer(", public_stable_func + "\n\ndef is_version_newer(")

# Replace the tags fetching logic
old_tags_logic = """
        if not raw_version:
            tags_url = f"https://api.github.com/repos/{self.repo}/tags?per_page=1"
            try:
                tags = fetch_json(tags_url)
            except Exception as exc:
                raise UpdateSourceError(f"GitHub tags request failed: {exc}") from exc
            if isinstance(tags, list) and tags:
                first = tags[0]
                if isinstance(first, dict):
                    raw_version = str(first.get("name") or "").strip()

        latest = strip_version_prefix(raw_version)
        if not latest:
            return None
"""

new_tags_logic = """
        if not raw_version:
            tags_url = f"https://api.github.com/repos/{self.repo}/tags?per_page=10"
            try:
                tags = fetch_json(tags_url)
            except Exception as exc:
                raise UpdateSourceError(f"GitHub tags request failed: {exc}") from exc
            if isinstance(tags, list):
                for t in tags:
                    if isinstance(t, dict):
                        tv = str(t.get("name") or "").strip()
                        if tv and is_public_stable(tv):
                            raw_version = tv
                            break

        latest = strip_version_prefix(raw_version)
        if not latest or not is_public_stable(latest):
            return None
"""

content = content.replace(old_tags_logic.strip(), new_tags_logic.strip())

with open("src/atlas_agent/update/sources.py", "w") as f:
    f.write(content)
