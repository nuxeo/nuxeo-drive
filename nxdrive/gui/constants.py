from ..translator import Translator


def get_known_types_translations():

    KNOWN_FOLDER_TYPES = {
        "OrderedFolder": Translator.get("ORDERED_FOLDER"),
        "Folder": Translator.get("FOLDER"),
    }
    KNOWN_FILE_TYPES = {
        "Audio": Translator.get("AUDIO"),
        "File": Translator.get("FILE"),
        "Picture": Translator.get("PICTURE"),
        "Video": Translator.get("VIDEO"),
    }
    DEFAULT_TYPES = {
        "Automatic": Translator.get("AUTOMATICS"),
        "Create": Translator.get("CREATE"),
    }

    return {
        "FOLDER_TYPES": KNOWN_FOLDER_TYPES,
        "FILE_TYPES": KNOWN_FILE_TYPES,
        "DEFAULT": DEFAULT_TYPES,
    }
