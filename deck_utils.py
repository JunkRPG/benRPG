"""
Deck Utilities - Centralized deck path resolution for JunkRPG.

All deck files should be stored in the 'decks/' directory.
This module provides consistent path resolution across all game systems.
"""

import os

# The single canonical location for deck files
DECKS_DIR = "decks"


def resolve_deck_path(deck_file):
    """
    Resolve a deck filename or path to the canonical deck location.

    Args:
        deck_file: Either a filename (e.g., "test_deck.json") or a path
                   (e.g., "decks/test_deck.json")

    Returns:
        Full path to the deck file in the decks/ directory.

    Examples:
        resolve_deck_path("test_deck.json") -> "decks/test_deck.json"
        resolve_deck_path("decks/test_deck.json") -> "decks/test_deck.json"
        resolve_deck_path("cards/decks/old.json") -> "decks/old.json"
    """
    if not deck_file:
        return None

    # Extract just the filename if a full path was provided
    filename = os.path.basename(deck_file)

    # Return path in canonical location
    return os.path.join(DECKS_DIR, filename)


def deck_exists(deck_file):
    """
    Check if a deck file exists.

    Args:
        deck_file: Deck filename or path

    Returns:
        True if deck exists, False otherwise
    """
    path = resolve_deck_path(deck_file)
    return path is not None and os.path.exists(path)


def list_decks():
    """
    List all available deck files.

    Returns:
        List of deck filenames (not full paths)
    """
    if not os.path.exists(DECKS_DIR):
        return []

    return [f for f in os.listdir(DECKS_DIR) if f.endswith('.json')]
