"""Search all study files: save each file's text once, then find words in it.

Pure helpers plus one function that reads files through the owner-only services. Nothing here
calls an AI service, and nothing is shown to anyone but the file's owner.
"""
import re
from academics import services
from . import text_extraction

PREPARE_PER_VISIT = 3   # files read per search visit (a long PDF can take a few seconds)
SNIPPETS_PER_FILE = 3
SNIPPET_SIDE = 90       # characters shown on each side of a match
_SPACES = re.compile(r"\s+")


def save_text(identity, material_id, content, file_type):
    """Read one file's text and save it (or why there is none). False when busy: try later."""
    try:
        extracted = text_extraction.extract_text_remembered(file_type, content)
    except text_extraction.ExtractionFailed as failure:
        if failure.reason == "busy":
            return False
        problem = failure.reason if failure.reason in ("no_text", "encrypted", "unsupported") else "unreadable"
        services.search_texts.save(identity, material_id, problem=problem)
        return True
    services.search_texts.save(identity, material_id, text=extracted.text, truncated=extracted.truncated)
    return True


def prepare(identity, limit=PREPARE_PER_VISIT):
    """Save the text of up to `limit` files that have none yet. Returns how many still wait."""
    waiting, count = services.search_texts.missing(identity, limit)
    done = 0
    for material_id in waiting:
        try:
            material, content = services.materials.read_file(identity, material_id)
        except services.StoredFileDamaged:
            services.search_texts.save(identity, material_id, problem="unreadable")
            done += 1
            continue
        except services.RecordNotFound:
            continue  # deleted meanwhile
        if not save_text(identity, material.pk, content, material.file_type):
            break
        done += 1
    return count - done


def snippets(text, words, limit=SNIPPETS_PER_FILE, side=SNIPPET_SIDE):
    """Up to `limit` (before, match, after) pieces around each place `words` appears (any letter
    case, taken literally), plus the total number of matches. The template escapes every piece."""
    found = [match.span() for match in re.finditer(re.escape(words), text, re.IGNORECASE)]
    pieces = []
    for start, end in found[:limit]:
        before = text[max(0, start - side):start]
        after = text[end:end + side]
        # Runs of spaces and line breaks become one space; the space beside the match is kept.
        pieces.append({"before": ("…" if start > side else "") + _SPACES.sub(" ", before).lstrip(),
                       "match": text[start:end],
                       "after": _SPACES.sub(" ", after).rstrip() + ("…" if end + side < len(text) else "")})
    return pieces, len(found)
