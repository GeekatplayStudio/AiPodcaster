"""Language knowledge used by transcription and cleanup.

* Per-language filler words, phrases and "light" fillers (suggested, not pre-accepted).
* Elongated hesitation detection: "Aaaa", "hmmm", "eee", "ээээ", "м-м-м", "euuuh".
* Profanity lists (stems for inflected languages).
* Stopwords for keywords and statistics.
* Whisper "verbatim" prompts that keep disfluencies in the transcript.
* A small text language detector for pasted transcripts.
"""
from __future__ import annotations

import re
from functools import lru_cache

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English", "ru": "Russian", "uk": "Ukrainian", "es": "Spanish", "de": "German", "fr": "French",
    "it": "Italian", "pt": "Portuguese", "nl": "Dutch", "pl": "Polish", "tr": "Turkish", "cs": "Czech",
    "sv": "Swedish", "ja": "Japanese", "zh": "Chinese", "ko": "Korean", "ar": "Arabic", "he": "Hebrew",
    "hi": "Hindi", "el": "Greek",
}

# Interjection-only fillers: always flagged and pre-accepted.
STRONG_FILLERS: dict[str, set[str]] = {
    "*": {"hmm", "hm", "mm", "mmm", "mhm", "ehm", "uhm", "ähm", "äh"},
    "en": {"um", "umm", "uh", "uhh", "erm", "er", "ah", "eh"},
    "ru": {"э", "ээ", "эм", "эмм", "мм", "хм", "гм", "ммм", "ам"},
    "uk": {"е", "ее", "ем", "мм", "хм", "гм"},
    "es": {"eh", "em", "emm", "mmm"},
    "de": {"äh", "ähm", "öh", "öhm", "hm"},
    "fr": {"euh", "heu", "hum", "bah"},
    "it": {"ehm", "eh", "uhm", "mmm"},
    "pt": {"hum", "ahn", "éé", "hã"},
    "nl": {"eh", "ehm", "uh", "uhm"},
    "pl": {"yyy", "eee", "hmm"},
}

# Words that are fillers only in some contexts: suggested but left for the user to decide.
LIGHT_FILLERS: dict[str, set[str]] = {
    "en": {"like", "literally", "basically", "actually", "so", "well", "right"},
    "ru": {"ну", "вот", "типа", "короче", "значит", "это", "блин", "собственно"},
    "uk": {"ну", "типу", "короче", "значить", "от"},
    "es": {"este", "pues", "bueno", "vale", "tipo", "osea"},
    "de": {"also", "halt", "eben", "quasi", "genau", "irgendwie"},
    "fr": {"ben", "genre", "voilà", "bon", "quoi"},
    "it": {"cioè", "tipo", "allora", "insomma", "praticamente"},
    "pt": {"tipo", "então", "assim", "né"},
    "nl": {"dus", "zeg", "eigenlijk"},
    "pl": {"jakby", "znaczy", "wiesz", "no"},
}

FILLER_PHRASES: dict[str, set[str]] = {
    "en": {"you know", "i mean", "kind of", "sort of"},
    "ru": {"как бы", "в общем", "так сказать", "это самое", "в принципе", "то есть"},
    "uk": {"як би", "в принципі", "так би мовити"},
    "es": {"o sea", "es decir", "a ver"},
    "de": {"weißt du", "ich meine", "sag mal"},
    "fr": {"du coup", "en fait", "tu vois", "je veux dire"},
    "it": {"diciamo che", "come dire"},
    "pt": {"sabe como", "quer dizer"},
}

# Bases that become hesitations when stretched: "aaaa" -> "a", "ммм" -> "м", "esteee" -> "este".
ELONGATION_STRONG = {"a", "e", "i", "u", "m", "hm", "mh", "uh", "um", "ah", "eh", "er", "ehm", "äh", "ä", "ö", "öh", "euh", "eu",
                     "э", "а", "е", "ы", "у", "м", "и", "хм", "гм", "эм", "ам", "y"}
ELONGATION_LIGHT = {"ну", "вот", "so", "well", "este", "pues", "bueno", "also", "alors", "ben", "allora", "então", "jaa"}

PROFANITY: dict[str, set[str]] = {
    "en": {"fuck", "fucking", "fucked", "fucker", "shit", "shitty", "bullshit", "bitch", "bastard", "asshole", "damn", "goddamn",
           "crap", "dick", "piss", "pissed", "cunt", "motherfucker", "whore", "slut"},
    "es": {"mierda", "joder", "puta", "puto", "coño", "cabrón", "cabron", "gilipollas", "carajo", "pendejo", "chingar", "hostia"},
    "de": {"scheiße", "scheisse", "verdammt", "arschloch", "fick", "ficken", "wichser", "hure", "fotze"},
    "fr": {"merde", "putain", "connard", "connasse", "bordel", "salope", "enculé", "foutre", "chier", "con"},
    "it": {"cazzo", "merda", "stronzo", "vaffanculo", "puttana", "minchia", "coglione"},
    "pt": {"merda", "porra", "caralho", "foda", "puta", "cacete", "fdp"},
    "nl": {"kut", "godverdomme", "klootzak", "lul", "shit"},
    "pl": {"kurwa", "chuj", "pierdole", "jebać", "kurde", "spierdalaj"},
}
# Russian and Ukrainian obscenities are heavily inflected and take prefixes ("на-", "за-", "о-").
# Patterns are anchored at the word start so ordinary words ("рубля", "употреблять", "страхуйте") never match.
_RU_PREFIX = r"(?:за|на|вы|от|отъ|по|у|въ|съ|раз|разъ|до|при|про|пере|недо|о|об|подъ|из|изъ|с)?"
_UK_PREFIX = r"(?:за|на|ви|від|по|у|роз|до|при|про|пере|о|об|під|з|с)?"
PROFANITY_STEMS: dict[str, re.Pattern[str]] = {
    "ru": re.compile(
        rf"^(?:{_RU_PREFIX}ху[йеёяи]|{_RU_PREFIX}[её]б(?:а|у|ы|л|н|т|и|с)|бляд|блят|бля$|\w*пизд|муда[кч]|мудил|сук[аи]$|сукин|сучар|"
        r"говн|\w*залуп|шлюх|гандон|дерьм)"
    ),
    "uk": re.compile(
        rf"^(?:{_UK_PREFIX}ху[йєяї]|{_UK_PREFIX}[їє]б(?:а|у|л|н|т|и)|бляд|блят|бля$|\w*пизд|мудак|сук[аи]$|гівн|лайн[оау]$)"
    ),
}


STOPWORDS: dict[str, set[str]] = {
    "en": set(
        "the a an and or but so to of in on for with at by from is are was were be been being this that these those it its as if then than there here what "
        "which who whom how when where why not no yes do does did have has had will would can could should may might just very really also about into over out "
        "up down like um uh okay ok well yeah right get got go going i you we they he she them our your their my me us him her "
        .split()),
    "ru": set(
        "и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня еще нет о из ему теперь когда даже ну "
        "вдруг ли если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей может они тут где есть надо ней для мы тебя их чем "
        "была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом один почти мой тем чтобы нее "
        "сейчас были куда зачем всех никогда можно при наконец два об другой хоть после над больше тот через эти нас про всего них какая много разве три эту "
        "моя впрочем хорошо свою этой перед иногда лучше чуть том нельзя такой им более всегда конечно всю между это как бы "
        .split()),
    "uk": set(
        "і в у не що він на я з як а то все вона так його але так ти до ж ви за б по тільки її мені було ось від мене ще ні о з йому тепер коли навіть ну чи "
        "якщо вже або бути був нього це ці цей та те які який "
        .split()),
    "es": set(
        "de la que el en y a los del se las por un para con no una su al lo como más pero sus le ya o este sí porque esta entre cuando muy sin sobre también me "
        "hasta hay donde quien desde todo nos durante todos uno les ni contra otros ese eso ante ellos e esto mí antes algunos qué unos yo otro otras otra él "
        "tanto esa estos mucho quienes nada muchos cual poco ella estar estas algunas algo nosotros es son fue era "
        .split()),
    "de": set(
        "der die das und in den von zu mit sich des auf für ist im dem nicht ein eine als auch es an werden aus er hat dass sie nach wird bei einer um am sind "
        "noch wie einem über einen so zum war haben nur oder aber vor zur bis mehr durch man sein wurde sei ich du wir ihr ja nein "
        .split()),
    "fr": set(
        "le la les de des du un une et à en est que qui dans pour pas sur au ce il elle on ne se plus par avec tout mais ou son sa ses nous vous ils elles leur "
        "cette ces été être avoir je tu y aux comme si "
        .split()),
    "it": set("il lo la i gli le di a da in con su per tra fra e è che non un una uno del della dei delle al alla ai come ma se più anche ci si io tu lui lei noi voi loro questo questa".split()),
    "pt": set("o a os as de do da dos das em no na nos nas um uma e é que não para com por se mais mas como ao à eu você ele ela nós eles elas isso este esta".split()),
    "nl": set("de het een en van in is dat op te zijn met voor niet aan er ook als bij door maar om uit dan of wat ik je we ze hij zij".split()),
    "pl": set("i w na nie z do się to że jest o jak a co po ale tak za od jego tylko czy już ja ty my wy on ona oni być był była".split()),
}

VERBATIM_PROMPTS: dict[str, str] = {
    "en": "Umm, let me think like, hmm... Okay, here's what I'm, like, thinking. Uh, so, you know.",
    "ru": "Ээ, ну, ммм... Так, значит, это, как бы, вот что я думаю. Эм, ну, в общем.",
    "uk": "Ее, ну, ммм... Так, значить, це, типу, ось що я думаю.",
    "es": "Eh, este, mmm... Bueno, o sea, pues, lo que pienso es esto.",
    "de": "Äh, ähm, also... Naja, halt, sozusagen, ich denke, dass...",
    "fr": "Euh, ben, hum... Alors, du coup, en fait, je pense que...",
    "it": "Ehm, cioè, mmm... Allora, tipo, insomma, penso che...",
    "pt": "Hum, tipo, né... Então, assim, eu acho que...",
    "nl": "Eh, ehm, nou... Dus, eigenlijk, ik denk dat...",
    "pl": "Yyy, eee, no... Więc, jakby, znaczy, myślę, że...",
}

PUNCT = re.compile(r"[^\w'’-]+", re.UNICODE)
WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def base_language(code: str | None) -> str | None:
    if not code:
        return None
    return code.lower().split("-")[0].split("_")[0]


def normalise(token: str) -> str:
    return PUNCT.sub("", token.lower()).strip("'’-")


def _collapse(token: str) -> str:
    """'aaaa' -> 'a', 'хммм' -> 'хм', 'a-a-a' -> 'a'."""
    letters = token.replace("-", "")
    return re.sub(r"(.)\1+", r"\1", letters)


def elongation_kind(token: str) -> str | None:
    """Return "strong" or "light" when the token is a stretched hesitation, else None."""
    core = normalise(token)
    if not core:
        return None
    collapsed = _collapse(core)
    stretched = len(core.replace("-", "")) > len(collapsed) or ("-" in core and len(set(core.replace("-", ""))) == 1)
    if not stretched:
        return None
    if collapsed in ELONGATION_STRONG:
        return "strong"
    if collapsed in ELONGATION_LIGHT:
        return "light"
    return None


@lru_cache(maxsize=32)
def strong_fillers(language: str | None) -> frozenset[str]:
    lang = base_language(language) or "en"
    return frozenset(STRONG_FILLERS["*"] | STRONG_FILLERS.get(lang, STRONG_FILLERS["en"]))


@lru_cache(maxsize=32)
def light_fillers(language: str | None) -> frozenset[str]:
    lang = base_language(language) or "en"
    return frozenset(LIGHT_FILLERS.get(lang, LIGHT_FILLERS["en"]))


@lru_cache(maxsize=32)
def filler_phrases(language: str | None) -> frozenset[str]:
    lang = base_language(language) or "en"
    return frozenset(FILLER_PHRASES.get(lang, set()) | FILLER_PHRASES["en"])


def profanity_words(language: str | None) -> set[str]:
    lang = base_language(language)
    words = set(PROFANITY["en"])
    if lang and lang in PROFANITY:
        words |= PROFANITY[lang]
    return words


def profanity_stem(language: str | None) -> re.Pattern[str] | None:
    lang = base_language(language)
    return PROFANITY_STEMS.get(lang or "")


def is_profane_stem(core: str, language: str | None) -> bool:
    pattern = profanity_stem(language)
    return bool(pattern and pattern.match(core))


@lru_cache(maxsize=1)
def all_stopwords() -> frozenset[str]:
    merged: set[str] = set()
    for words in STOPWORDS.values():
        merged |= words
    return frozenset(merged)


def verbatim_prompt(language: str | None) -> str:
    return VERBATIM_PROMPTS.get(base_language(language) or "en", VERBATIM_PROMPTS["en"])


def language_name(code: str | None) -> str:
    base = base_language(code)
    return LANGUAGE_NAMES.get(base or "", base or "the same language as the transcript")


def detect_text_language(text: str) -> str | None:
    """Script + stopword heuristics; good enough to pick fillers and prompts for pasted text."""
    sample = text[:20_000]
    letters = [c for c in sample if c.isalpha()]
    if len(letters) < 20:
        return None
    total = len(letters)

    def share(pattern: str) -> float:
        return len(re.findall(pattern, sample)) / total

    if share(r"[Ѐ-ӿ]") > 0.3:
        return "uk" if share(r"[іїєґІЇЄҐ]") > 0.005 else "ru"
    if share(r"[぀-ヿ]") > 0.05:
        return "ja"
    if share(r"[一-鿿]") > 0.3:
        return "zh"
    if share(r"[가-힯]") > 0.3:
        return "ko"
    if share(r"[؀-ۿ]") > 0.3:
        return "ar"
    if share(r"[֐-׿]") > 0.3:
        return "he"
    if share(r"[Ͱ-Ͽ]") > 0.3:
        return "el"
    if share(r"[ऀ-ॿ]") > 0.3:
        return "hi"
    tokens = [t.lower() for t in WORD.findall(sample)]
    if not tokens:
        return None
    scores = {lang: sum(1 for t in tokens if t in words) for lang, words in STOPWORDS.items() if lang not in {"ru", "uk"}}
    best = max(scores, key=lambda lang: scores[lang])
    return best if scores[best] >= max(3, len(tokens) * 0.05) else None
