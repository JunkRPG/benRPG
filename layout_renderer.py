"""
layout_renderer.py — Pillow-based card rendering engine.

Renders card layout templates + card data into high-quality PIL Images.
No UI code — pure rendering logic, importable by any application.
"""

import os
import json
import glob as glob_module
from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------------------
# Font handling
# ---------------------------------------------------------------------------

_font_path_cache = {}


def get_font_path(family_name):
    """Map a font family name to a .ttf path on Windows.

    Scans C:/Windows/Fonts/ and caches results.
    Fallback: arial.ttf
    """
    if not family_name:
        family_name = "Arial"

    key = family_name.lower().strip()
    if key in _font_path_cache:
        return _font_path_cache[key]

    fonts_dir = "C:/Windows/Fonts"
    if os.path.isdir(fonts_dir):
        # Build a mapping of lowercase stem -> full path
        for fname in os.listdir(fonts_dir):
            if fname.lower().endswith((".ttf", ".otf")):
                stem = os.path.splitext(fname)[0].lower()
                full = os.path.join(fonts_dir, fname)
                # Exact match on stem
                if stem == key:
                    _font_path_cache[key] = full
                    return full

        # Fuzzy: check if family name appears anywhere in the filename
        for fname in os.listdir(fonts_dir):
            if fname.lower().endswith((".ttf", ".otf")):
                if key in fname.lower():
                    full = os.path.join(fonts_dir, fname)
                    _font_path_cache[key] = full
                    return full

    # Fallback
    fallback = os.path.join(fonts_dir, "arial.ttf")
    if os.path.isfile(fallback):
        _font_path_cache[key] = fallback
        return fallback

    # Last resort: let Pillow try the name directly
    _font_path_cache[key] = family_name
    return family_name


def _load_font(family, size, style="normal", cache=None):
    """Load a PIL ImageFont, using *cache* dict if provided."""
    cache_key = (family, size, style)
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    path = get_font_path(family)

    # Try style-specific font files
    if style in ("bold", "bold_italic"):
        bold_path = get_font_path(family + "bd")
        if bold_path != path:
            path = bold_path
    if style in ("italic", "bold_italic"):
        italic_path = get_font_path(family + "i")
        if style == "italic" and italic_path != path:
            path = italic_path

    try:
        font = ImageFont.truetype(path, size)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("arial.ttf", size)
        except (IOError, OSError):
            font = ImageFont.load_default()

    if cache is not None:
        cache[cache_key] = font
    return font


# ---------------------------------------------------------------------------
# Text wrapping
# ---------------------------------------------------------------------------

def wrap_text(text, font, max_width):
    """Word-wrap *text* to fit within *max_width* pixels using Pillow font metrics.

    Returns a list of lines.
    """
    if not text:
        return [""]
    if max_width <= 0:
        return [text]

    words = text.split()
    if not words:
        return [""]

    lines = []
    current_line = words[0]

    for word in words[1:]:
        test_line = current_line + " " + word
        bbox = font.getbbox(test_line)
        line_width = bbox[2] - bbox[0]
        if line_width <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word

    lines.append(current_line)
    return lines


# ---------------------------------------------------------------------------
# Template I/O
# ---------------------------------------------------------------------------

def load_all_templates(layouts_dir="layouts"):
    """Scan layouts/ directory and load all template JSON files."""
    templates = []
    if not os.path.isdir(layouts_dir):
        return templates

    for fpath in glob_module.glob(os.path.join(layouts_dir, "*.json")):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                tmpl = json.load(f)
            # Only include files that look like layout templates
            if "elements" in tmpl and "card_width" in tmpl:
                tmpl["_file_path"] = fpath
                templates.append(tmpl)
        except (json.JSONDecodeError, IOError):
            pass
    return templates


# ---------------------------------------------------------------------------
# Template matching
# ---------------------------------------------------------------------------

def find_matching_template(card_data, templates):
    """Find the best matching template(s) for a card.

    Returns:
        - A single template dict for 1-state / full cards
        - A (state1_template, state2_template) tuple for 2-state cards
        - None if no match found
    """
    card_type = card_data.get("card_type", "")
    subclass = card_data.get("subclass") or None
    states = card_data.get("states", 1)

    def best_match(target_state):
        exact = None
        type_only = None
        for t in templates:
            t_type = t.get("target_type", "")
            t_sub = t.get("target_subclass") or None
            t_state = t.get("target_state", "full")
            if t_type != card_type or t_state != target_state:
                continue
            if t_sub == subclass:
                exact = t
                break
            if t_sub is None:
                type_only = t
        return exact or type_only

    if states == 1 or states is None:
        match = best_match("full")
        return match
    else:
        s1 = best_match("state1")
        s2 = best_match("state2")
        if s1 or s2:
            return (s1, s2)
        # Fallback: try a "full" template
        full = best_match("full")
        return full


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_template_region(template, field_data, fonts_cache=None):
    """Render a single template region (full card, or one half) to a PIL Image.

    Args:
        template: Template dict with card_width, card_height, elements, etc.
        field_data: Dict of field_key -> value strings
        fonts_cache: Optional dict for caching loaded fonts

    Returns:
        PIL Image of the rendered region
    """
    if fonts_cache is None:
        fonts_cache = {}

    width = template.get("card_width", 750)
    height = template.get("card_height", 1050)
    bg_color = template.get("background_color", "#1a1a2e")
    border_color = template.get("border_color", "#3a3a5c")
    border_width = template.get("border_width", 2)

    img = Image.new("RGBA", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # Draw border
    if border_width > 0:
        for i in range(border_width):
            draw.rectangle(
                [i, i, width - 1 - i, height - 1 - i],
                outline=border_color,
            )

    # Render elements
    for elem in template.get("elements", []):
        etype = elem.get("type", "text")

        if etype == "text":
            _render_text_element(draw, elem, field_data, fonts_cache)
        elif etype == "static_text":
            _render_static_text_element(draw, elem, fonts_cache)
        elif etype == "image":
            _render_image_element(img, elem, field_data)

    return img


def _render_text_element(draw, elem, field_data, fonts_cache):
    """Render a data-mapped text element."""
    field_key = elem.get("field_key", "")
    value = field_data.get(field_key, "")
    if value is None:
        value = ""
    value = str(value)

    prefix = elem.get("label_prefix", "")
    text = prefix + value
    if not text.strip():
        text = f"[{field_key}]"

    _draw_text(draw, elem, text, fonts_cache)


def _render_static_text_element(draw, elem, fonts_cache):
    """Render a static (literal) text element."""
    text = elem.get("text", "")
    _draw_text(draw, elem, text, fonts_cache)


def _draw_text(draw, elem, text, fonts_cache):
    """Common text drawing logic for text and static_text elements."""
    font_family = elem.get("font_family", "Arial")
    font_size = elem.get("font_size", 16)
    font_style = elem.get("font_style", "normal")
    font_color = elem.get("font_color", "#ffffff")
    alignment = elem.get("alignment", "left")
    max_width = elem.get("max_width", 700)
    x = elem.get("x", 0)
    y = elem.get("y", 0)

    font = _load_font(font_family, font_size, font_style, fonts_cache)
    lines = wrap_text(text, font, max_width)

    line_y = y
    for line in lines:
        bbox = font.getbbox(line)
        line_width = bbox[2] - bbox[0]
        line_height = bbox[3] - bbox[1]

        if alignment == "center":
            line_x = x - line_width // 2
        elif alignment == "right":
            line_x = x - line_width
        else:
            line_x = x

        draw.text((line_x, line_y), line, font=font, fill=font_color)
        line_y += line_height + 4  # small line spacing


def _render_image_element(img, elem, field_data):
    """Render an image element by loading the file from card data."""
    field_key = elem.get("field_key", "")
    file_path = field_data.get(field_key, "")
    if not file_path or not isinstance(file_path, str):
        return

    # Try the path as-is, then relative to current directory
    if not os.path.isfile(file_path):
        alt = os.path.join(os.getcwd(), file_path)
        if os.path.isfile(alt):
            file_path = alt
        else:
            return

    try:
        elem_img = Image.open(file_path).convert("RGBA")
        w = elem.get("width", elem_img.width)
        h = elem.get("height", elem_img.height)
        elem_img = elem_img.resize((w, h), Image.Resampling.LANCZOS)
        x = elem.get("x", 0)
        y = elem.get("y", 0)
        img.paste(elem_img, (x, y), elem_img)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Two-state composition
# ---------------------------------------------------------------------------

def compose_two_state_card(state1_img, state2_img, full_width, full_height):
    """Compose a two-state card.

    state1 on top, state2 rotated 180 degrees on bottom.
    A thin divider line is drawn between halves.
    """
    half_height = full_height // 2
    card = Image.new("RGBA", (full_width, full_height), "#000000")

    # Resize halves if needed
    if state1_img.size != (full_width, half_height):
        state1_img = state1_img.resize((full_width, half_height), Image.Resampling.LANCZOS)
    if state2_img.size != (full_width, half_height):
        state2_img = state2_img.resize((full_width, half_height), Image.Resampling.LANCZOS)

    # Paste state 1 at top
    card.paste(state1_img, (0, 0))

    # Rotate state 2 by 180 degrees and paste at bottom
    state2_rotated = state2_img.rotate(180)
    card.paste(state2_rotated, (0, half_height))

    # Draw divider line
    draw = ImageDraw.Draw(card)
    draw.line([(0, half_height), (full_width, half_height)], fill="#666666", width=2)

    return card


# ---------------------------------------------------------------------------
# State field extraction
# ---------------------------------------------------------------------------

def _extract_state_fields(card_data, state_num):
    """Extract field data for a specific state from card data.

    For state 1: returns all keys NOT starting with '2nd_state_' or '2nd_State_'
    For state 2: returns keys starting with '2nd_state_' or '2nd_State_' with prefix stripped
    """
    data = card_data.get("data", {})
    result = {}

    if state_num == 1:
        for k, v in data.items():
            if not k.startswith("2nd_state_") and not k.startswith("2nd_State_"):
                result[k] = v
    elif state_num == 2:
        for k, v in data.items():
            if k.startswith("2nd_state_"):
                result[k[len("2nd_state_"):]] = v
            elif k.startswith("2nd_State_"):
                result[k[len("2nd_State_"):]] = v

    return result


# ---------------------------------------------------------------------------
# Top-level render
# ---------------------------------------------------------------------------

def render_card(card_data, template_or_pair, fonts_cache=None):
    """Render a card to a PIL Image.

    Args:
        card_data: Card JSON dict (with card_type, subclass, states, data)
        template_or_pair: Either a single template dict (full/1-state) or a
                          tuple (state1_template, state2_template) for 2-state
        fonts_cache: Optional dict to cache loaded fonts

    Returns:
        PIL Image at template resolution, or None if templates are missing
    """
    if fonts_cache is None:
        fonts_cache = {}

    if template_or_pair is None:
        return None

    # Two-state card with template pair
    if isinstance(template_or_pair, tuple):
        s1_tmpl, s2_tmpl = template_or_pair
        if s1_tmpl is None and s2_tmpl is None:
            return None

        # Determine full card dimensions from state1 template or defaults
        ref = s1_tmpl or s2_tmpl
        full_width = ref.get("card_width", 750)
        full_height = full_width * 1050 // 750  # maintain standard ratio

        s1_fields = _extract_state_fields(card_data, 1)
        s2_fields = _extract_state_fields(card_data, 2)

        if s1_tmpl:
            s1_img = render_template_region(s1_tmpl, s1_fields, fonts_cache)
        else:
            s1_img = Image.new("RGBA", (full_width, full_height // 2), "#333333")

        if s2_tmpl:
            s2_img = render_template_region(s2_tmpl, s2_fields, fonts_cache)
        else:
            s2_img = Image.new("RGBA", (full_width, full_height // 2), "#333333")

        return compose_two_state_card(s1_img, s2_img, full_width, full_height)

    # Single template (full or 1-state)
    template = template_or_pair
    all_data = card_data.get("data", {})
    return render_template_region(template, all_data, fonts_cache)
