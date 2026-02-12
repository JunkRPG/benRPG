import os
import time

import pygame

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


SOUNDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")
SAMPLE_RATE = 44100


class SoundManager:
    """Generates and plays sound effects. Gracefully disables itself if audio fails."""

    def __init__(self):
        self.enabled = False
        self.sounds = {}
        self._last_play_time = {}
        self._cooldown_ms = 50

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=512)
            mixer_info = pygame.mixer.get_init()
            self._channels = mixer_info[2] if mixer_info else 2
            self.enabled = True
        except Exception:
            return

        if not HAS_NUMPY:
            self.enabled = False
            return

        generators = {
            "projectile_shot": self._gen_projectile_shot,
            "melee_swing": self._gen_melee_swing,
            "entity_defeated": self._gen_entity_defeated,
            "junk_acquired": self._gen_junk_acquired,
            "document_acquired": self._gen_document_acquired,
        }
        for name, gen_func in generators.items():
            self._load_or_generate(name, gen_func)

    def _load_or_generate(self, name, gen_func):
        """Load from sounds/ folder if available, otherwise generate."""
        for ext in (".wav", ".ogg"):
            path = os.path.join(SOUNDS_DIR, name + ext)
            if os.path.isfile(path):
                try:
                    self.sounds[name] = pygame.mixer.Sound(path)
                    return
                except Exception:
                    pass
        try:
            self.sounds[name] = gen_func()
        except Exception:
            pass

    def play(self, name):
        """Play a named sound effect with cooldown to prevent overlap spam."""
        if not self.enabled or name not in self.sounds:
            return
        now = time.time() * 1000
        if now - self._last_play_time.get(name, 0) < self._cooldown_ms:
            return
        self._last_play_time[name] = now
        try:
            self.sounds[name].play()
        except Exception:
            pass

    # --- Sound generators ---

    def _make_sound(self, samples):
        """Convert a float64 numpy array (-1..1) to a pygame Sound."""
        samples = np.clip(samples, -1.0, 1.0)
        pcm = (samples * 32767).astype(np.int16)
        if self._channels == 2:
            pcm = np.column_stack([pcm, pcm])
        else:
            pcm = pcm.reshape(-1, 1)
        return pygame.sndarray.make_sound(pcm)

    def _gen_projectile_shot(self):
        """150ms rising sine sweep 300-800Hz with fast decay — twang."""
        duration = 0.15
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
        freq = 300 + (800 - 300) * (t / duration)
        phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
        envelope = np.exp(-t * 20)
        samples = np.sin(phase) * envelope * 0.5
        return self._make_sound(samples)

    def _gen_melee_swing(self):
        """120ms noise + downward sweep 500-150Hz — whoosh."""
        duration = 0.12
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
        freq = 500 - (500 - 150) * (t / duration)
        phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
        envelope = np.exp(-t * 15)
        noise = np.random.default_rng(42).uniform(-0.3, 0.3, len(t))
        samples = (np.sin(phase) * 0.4 + noise) * envelope * 0.5
        return self._make_sound(samples)

    def _gen_entity_defeated(self):
        """300ms bass thud 80Hz + descending tone 200-60Hz — low thud."""
        duration = 0.3
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
        bass = np.sin(2 * np.pi * 80 * t) * np.exp(-t * 10)
        freq = 200 - (200 - 60) * (t / duration)
        phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
        tone = np.sin(phase) * np.exp(-t * 8)
        samples = (bass * 0.5 + tone * 0.4) * 0.6
        return self._make_sound(samples)

    def _gen_junk_acquired(self):
        """500ms rising C major arpeggio (C4-E4-G4-C5) — triumphant motif."""
        notes = [261.63, 329.63, 392.00, 523.25]  # C4, E4, G4, C5
        note_dur = 0.125
        all_samples = []
        for i, freq in enumerate(notes):
            t = np.linspace(0, note_dur, int(SAMPLE_RATE * note_dur), endpoint=False)
            envelope = np.exp(-t * 4) * np.minimum(t * 100, 1.0)
            tone = np.sin(2 * np.pi * freq * t) * 0.5
            tone += np.sin(2 * np.pi * freq * 2 * t) * 0.15  # octave harmonic
            all_samples.append(tone * envelope)
        samples = np.concatenate(all_samples) * 0.6
        return self._make_sound(samples)

    def _gen_document_acquired(self):
        """580ms rising D major arpeggio (D4-F#4-A4-D5) with overtone — richer motif."""
        notes = [293.66, 369.99, 440.00, 587.33]  # D4, F#4, A4, D5
        note_dur = 0.145
        all_samples = []
        for i, freq in enumerate(notes):
            t = np.linspace(0, note_dur, int(SAMPLE_RATE * note_dur), endpoint=False)
            envelope = np.exp(-t * 3.5) * np.minimum(t * 100, 1.0)
            tone = np.sin(2 * np.pi * freq * t) * 0.45
            tone += np.sin(2 * np.pi * freq * 2 * t) * 0.2   # octave harmonic
            tone += np.sin(2 * np.pi * freq * 3 * t) * 0.08  # 3rd harmonic
            all_samples.append(tone * envelope)
        samples = np.concatenate(all_samples) * 0.6
        return self._make_sound(samples)


# Module-level singleton
sound_manager = SoundManager()


def play_card_acquired_sound(card):
    """Play the appropriate acquisition sound based on card type."""
    try:
        card_type = card.card_data.get("card_type", "")
    except (AttributeError, TypeError):
        return
    if "Document" in card_type or "Blueprint" in card_type:
        sound_manager.play("document_acquired")
    elif "Junk" in card_type:
        sound_manager.play("junk_acquired")
