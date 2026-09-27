"""Default Edge voices, verified against the service voice list."""
VOICES = {
    'vi': ('vi-VN-HoaiMyNeural', 'vi-VN-NamMinhNeural'),
    'en': ('en-US-JennyNeural', 'en-US-GuyNeural'),
    'fr': ('fr-FR-DeniseNeural', 'fr-FR-HenriNeural'),
    'de': ('de-DE-KatjaNeural', 'de-DE-ConradNeural'),
    'es': ('es-ES-ElviraNeural', 'es-ES-AlvaroNeural'),
    'pt': ('pt-BR-FranciscaNeural', 'pt-BR-AntonioNeural'),
    'it': ('it-IT-ElsaNeural', 'it-IT-DiegoNeural'),
    'id': ('id-ID-GadisNeural', 'id-ID-ArdiNeural'),
    'ms': ('ms-MY-YasminNeural', 'ms-MY-OsmanNeural'),
    'fil': ('fil-PH-BlessicaNeural', 'fil-PH-AngeloNeural'),
    'ja': ('ja-JP-NanamiNeural', 'ja-JP-KeitaNeural'),
    'ko': ('ko-KR-SunHiNeural', 'ko-KR-InJoonNeural'),
    'th': ('th-TH-PremwadeeNeural', 'th-TH-NiwatNeural'),
    'tr': ('tr-TR-EmelNeural', 'tr-TR-AhmetNeural'),
    'nl': ('nl-NL-ColetteNeural', 'nl-NL-MaartenNeural'),
    'pl': ('pl-PL-ZofiaNeural', 'pl-PL-MarekNeural'),
}


def resolve_voices(language, female, male):
    if language not in VOICES:
        raise ValueError(f'Chưa có giọng đọc cho ngôn ngữ: {language}')
    if not female.strip() or not male.strip():
        raise ValueError('dubbing requires both a female and a male voice id')
    defaults = VOICES[language]
    # Older saved batches have the Vietnamese defaults even for other targets.
    return tuple(voice.strip() if voice.strip().startswith(language + '-') else fallback
                 for voice, fallback in zip((female, male), defaults))
