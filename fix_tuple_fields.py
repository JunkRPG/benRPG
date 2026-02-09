"""
Scan all JSON files in cards/ for fields that contain arrays (saved from tuples)
where a plain string is expected. Fix cases where all elements are identical,
and report cases where elements differ for manual review.
"""

import json
import os
import glob

CARDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards")

# Fields known to come from dropdowns (but we'll check ALL fields in data)
DROPDOWN_FIELDS = {
    "2nd_state_Type", "Type", "Allegiance", "2nd_state_Allegiance",
    "Range_Type", "2nd_state_Range_Type", "Ammo_Type", "2nd_state_Ammo_Type",
    "Requires_Ammo", "2nd_state_Requires_Ammo", "Include_Position",
    "2nd_state_Include_Position", "Exclude_Adjacent", "2nd_state_Exclude_Adjacent",
}

fixed_files = {}
needs_review = {}

json_files = glob.glob(os.path.join(CARDS_DIR, "*.json"))
print(f"Scanning {len(json_files)} JSON files in {CARDS_DIR}\n")

for filepath in sorted(json_files):
    filename = os.path.basename(filepath)
    
    # Skip card_index.json and usage_log.json
    if filename in ("card_index.json", "usage_log.json"):
        continue
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            card = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"  ERROR reading {filename}: {e}")
        continue
    
    if "data" not in card:
        continue
    
    data = card["data"]
    file_fixes = []
    file_reviews = []
    modified = False
    
    for key, value in data.items():
        if isinstance(value, list):
            # Check if all elements are the same string
            if len(value) > 0 and all(isinstance(v, str) for v in value):
                unique = set(value)
                if len(unique) == 1:
                    # All elements identical - safe to fix
                    original = list(value)
                    data[key] = value[0]
                    file_fixes.append((key, original, value[0]))
                    modified = True
                else:
                    # Elements differ - needs manual review
                    file_reviews.append((key, list(value)))
            elif len(value) > 0 and all(isinstance(v, bool) for v in value):
                unique_bools = list(set(value))
                if len(unique_bools) == 1:
                    original = list(value)
                    data[key] = value[0]
                    file_fixes.append((key, original, value[0]))
                    modified = True
                else:
                    file_reviews.append((key, list(value)))
    
    if file_fixes:
        fixed_files[filename] = file_fixes
        # Save the fixed file
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(card, f, indent=4)
    
    if file_reviews:
        needs_review[filename] = file_reviews

# Report results
print("=" * 70)
print("FIXED FILES (arrays with identical elements -> single string)")
print("=" * 70)

if fixed_files:
    for filename, fixes in sorted(fixed_files.items()):
        print(f"\n  {filename}:")
        for field, original, replacement in fixes:
            is_dropdown = "(dropdown)" if field in DROPDOWN_FIELDS else "(other field)"
            print(f"    {field} {is_dropdown}: {original} -> \"{replacement}\"")
    print(f"\n  Total: {len(fixed_files)} files fixed")
else:
    print("  None found.")

print()
print("=" * 70)
print("NEEDS MANUAL REVIEW (arrays with DIFFERING elements)")
print("=" * 70)

if needs_review:
    for filename, reviews in sorted(needs_review.items()):
        print(f"\n  {filename}:")
        for field, value in reviews:
            is_dropdown = "(dropdown)" if field in DROPDOWN_FIELDS else "(other field)"
            print(f"    {field} {is_dropdown}: {value}")
    print(f"\n  Total: {len(needs_review)} files need review")
else:
    print("  None found.")

print()
print("Done.")
