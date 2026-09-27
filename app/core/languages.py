"""Supported subtitle target languages."""
TARGET_LANGUAGES = (
    ('vi', 'Tiếng Việt'), ('en', 'Tiếng Anh'), ('fr', 'Tiếng Pháp'),
    ('de', 'Tiếng Đức'), ('es', 'Tiếng Tây Ban Nha'), ('pt', 'Tiếng Bồ Đào Nha'),
    ('it', 'Tiếng Ý'), ('id', 'Tiếng Indonesia'), ('ms', 'Tiếng Mã Lai'),
    ('fil', 'Tiếng Filipino (Philippines)'), ('ja', 'Tiếng Nhật'),
    ('ko', 'Tiếng Hàn'), ('th', 'Tiếng Thái'),
    ('tr', 'Tiếng Thổ Nhĩ Kỳ'), ('nl', 'Tiếng Hà Lan'), ('pl', 'Tiếng Ba Lan'),
)
TARGET_LANGUAGE_CODES = frozenset(code for code, _ in TARGET_LANGUAGES)
