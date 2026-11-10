"""Plain-language wording for the main window. The service's own messages stay available under "Details"."""

PLATFORM = {"pc": "PC (Steam)", "ps1": "PlayStation"}

# why one save cannot be converted: (short title, what to do)
PROBLEM = {
    "checksum": ("looks damaged",
                 "Its checksum does not match, so the PlayStation itself would call it corrupted. Leave it out, or "
                 "allow damaged saves under Advanced > Options."),
    "mod-data": ("holds data from a game mod",
                 "It uses things the PlayStation version does not have (from a Memoria or Moguri mod). Leave it out, "
                 "or allow dropping that data under Advanced > Options (every change is listed)."),
    "memoria-damaged": ("has a damaged Memoria data file",
                        "Memoria could not load this save itself. Leave it out, or convert the save without that file "
                        "under Advanced > Options."),
    "memoria-overlay": ("would be covered by old Memoria data",
                        "A Memoria data file of the save now in that place would load over the converted save. "
                        "Choose another slot under Advanced > Placement, or move that file away first."),
    "convert": ("cannot be converted", "See Details for the exact reason."),
    "verify": ("did not pass the safety check", "The converted copy did not read back exactly. Nothing is written. "
                                                "Please report this with the details."),
    "no-room": ("does not fit", "There is no free place for it on the memory card."),
    None: ("cannot be converted", "See Details for the exact reason."),
}

MEMORIA = {"none": "", "valid": "with Memoria data", "untimed": "with Memoria data", "stale": "old Memoria data ignored",
           "corrupt": "damaged Memoria data"}


def plural(n, word, many=None):
    return f"{n} {word if n == 1 else (many or word + 's')}"


def file_ranges(nums):
    """[1, 2, 3, 5] -> '1–3, 5'."""
    nums = sorted(nums)
    out, start, prev = [], None, None
    for n in nums + [None]:
        if start is None:
            start = prev = n
        elif n is not None and n == prev + 1:
            prev = n
        else:
            out.append(f"{start}" if start == prev else f"{start}–{prev}")
            start = prev = n
    return ", ".join(out)


def ps1_files(nums):
    nums = sorted(nums)
    if len(nums) == 1:
        return f"FILE{nums[0]:02d}"
    if nums == list(range(nums[0], nums[-1] + 1)):
        return f"FILE{nums[0]:02d}–FILE{nums[-1]:02d}"
    return ", ".join(f"FILE{n:02d}" for n in nums)
