"""
══════════════════════════════════════════════════════════════
Utility Functions — Version 2
══════════════════════════════════════════════════════════════
Terminal formatting, URL validation, ID generation, sentiment
analysis via keyword lexicon, stopword filtering, and shared
text utilities used across the entire application.
══════════════════════════════════════════════════════════════
"""

import os
import re
import sys
import math
import random
import string
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Section 1: Terminal Formatting
# ══════════════════════════════════════════════════════════════

def _supports_ansi() -> bool:
    """
    Detect whether the current terminal supports ANSI escape codes.

    Returns:
        True if ANSI codes will render correctly
    """
    if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
        return False
    if os.name == 'nt':
        try:
            os.system('')
            return True
        except Exception:
            return False
    return True


_ANSI_SUPPORTED = _supports_ansi()


def bold(text: str) -> str:
    """Apply bold formatting to text for terminal output."""
    if _ANSI_SUPPORTED:
        return f"\033[1m{text}\033[0m"
    return f"**{text}**"


def underline(text: str) -> str:
    """Apply underline formatting to text for terminal output."""
    if _ANSI_SUPPORTED:
        return f"\033[4m{text}\033[0m"
    return f"__{text}__"


def dim(text: str) -> str:
    """Apply dim/muted formatting to text for terminal output."""
    if _ANSI_SUPPORTED:
        return f"\033[2m{text}\033[0m"
    return text


def colored(text: str, color: str) -> str:
    """
    Apply color to text for terminal output.

    Supported colors: red, green, yellow, blue, magenta, cyan
    """
    if not _ANSI_SUPPORTED:
        return text
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
    }
    code = colors.get(color.lower(), "")
    if code:
        return f"{code}{text}\033[0m"
    return text


# ══════════════════════════════════════════════════════════════
# Section 2: URL Validation
# ══════════════════════════════════════════════════════════════

_REDDIT_URL_PATTERNS = [
    re.compile(r'^https?://(www\.)?reddit\.com/r/\w+/comments/\w+', re.IGNORECASE),
    re.compile(r'^https?://old\.reddit\.com/r/\w+/comments/\w+', re.IGNORECASE),
    re.compile(r'^https?://new\.reddit\.com/r/\w+/comments/\w+', re.IGNORECASE),
    re.compile(r'^https?://redd\.it/\w+', re.IGNORECASE),
]


def validate_reddit_url(url: str) -> str:
    """
    Validate that a string is a proper Reddit post URL.

    Args:
        url: The URL string to validate

    Returns:
        The validated URL (stripped of whitespace)

    Raises:
        ValueError: If the URL is not a valid Reddit post URL
    """
    if not url:
        raise ValueError("URL cannot be empty")
    url = url.strip()
    for pattern in _REDDIT_URL_PATTERNS:
        if pattern.match(url):
            logger.debug(f"URL validated: {url}")
            return url
    raise ValueError(
        f"Invalid Reddit URL: {url}\n"
        f"Expected formats:\n"
        f"  https://www.reddit.com/r/subreddit/comments/id/title/\n"
        f"  https://old.reddit.com/r/subreddit/comments/id/title/\n"
        f"  https://redd.it/id\n"
    )


# ══════════════════════════════════════════════════════════════
# Section 3: Comment ID Generation
# ══════════════════════════════════════════════════════════════

class CommentIDGenerator:
    """
    Generates unique, hierarchy-preserving comment IDs for a thread.

    Format: {base}-{hierarchy}
    Example: A7X9K2-1.2.3
    """

    def __init__(self, base_length: int = 6):
        if base_length < 4 or base_length > 12:
            raise ValueError(f"base_length must be between 4 and 12, got {base_length}")
        self._base = ''.join(
            random.choices(string.ascii_uppercase + string.digits, k=base_length)
        )
        self._counter = 0

    @property
    def thread_id(self) -> str:
        return self._base

    def generate(self, hierarchy_string: str) -> str:
        self._counter += 1
        return f"{self._base}-{hierarchy_string}"

    def generate_sequential(self) -> str:
        self._counter += 1
        return f"{self._base}-SEQ{self._counter:04d}"


# ══════════════════════════════════════════════════════════════
# Section 4: Time Formatting
# ══════════════════════════════════════════════════════════════

def format_timestamp(utc_timestamp: float) -> str:
    """Convert a UTC timestamp to a human-readable string."""
    try:
        dt = datetime.fromtimestamp(utc_timestamp, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (OSError, ValueError, OverflowError):
        return "Unknown date"


def format_relative_time(utc_timestamp: float) -> str:
    """Convert a UTC timestamp to a relative time string."""
    try:
        now = datetime.now(tz=timezone.utc)
        dt = datetime.fromtimestamp(utc_timestamp, tz=timezone.utc)
        delta = now - dt
        seconds = int(delta.total_seconds())
        if seconds < 0:
            return "just now"
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif seconds < 2592000:
            days = seconds // 86400
            return f"{days} day{'s' if days != 1 else ''} ago"
        elif seconds < 31536000:
            months = seconds // 2592000
            return f"{months} month{'s' if months != 1 else ''} ago"
        else:
            years = seconds // 31536000
            return f"{years} year{'s' if years != 1 else ''} ago"
    except (OSError, ValueError, OverflowError):
        return "Unknown"


def compute_engagement_duration(start_utc: float, end_utc: float) -> dict:
    """
    Compute the wall-clock duration between two UTC timestamps,
    broken into years, months, days, hours, and minutes.
    All components are floored (never rounded up).
    Zero-valued components are omitted from the result.

    Args:
        start_utc: Unix timestamp of the first event (post creation)
        end_utc:   Unix timestamp of the last event (last comment)

    Returns:
        dict with 'parts' list of (value, unit) tuples and 'text' string
    """
    try:
        start_dt = datetime.fromtimestamp(start_utc, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(end_utc, tz=timezone.utc)

        if end_dt <= start_dt:
            return {"parts": [], "text": "0 minutes", "total_seconds": 0}

        total_seconds = int((end_dt - start_dt).total_seconds())

        years = 0
        months = 0
        days = 0
        hours = 0
        minutes = 0

        # Compute years
        remaining = total_seconds
        years = remaining // 31536000
        remaining -= years * 31536000

        # Compute months (approximate 30.44 days)
        months = remaining // 2629746
        remaining -= months * 2629746

        # Compute days
        days = remaining // 86400
        remaining -= days * 86400

        # Compute hours
        hours = remaining // 3600
        remaining -= hours * 3600

        # Compute minutes
        minutes = remaining // 60

        parts = []
        if years > 0:
            parts.append((int(years), "Year" if years == 1 else "Years"))
        if months > 0:
            parts.append((int(months), "Month" if months == 1 else "Months"))
        if days > 0:
            parts.append((int(days), "Day" if days == 1 else "Days"))
        if hours > 0:
            parts.append((int(hours), "Hour" if hours == 1 else "Hours"))
        if minutes > 0:
            parts.append((int(minutes), "Minute" if minutes == 1 else "Minutes"))

        if not parts:
            parts.append((0, "Minutes"))

        text = ", ".join(f"{v} {u}" for v, u in parts)

        return {
            "parts": parts,
            "text": text,
            "total_seconds": total_seconds,
        }

    except (OSError, ValueError, OverflowError):
        return {"parts": [], "text": "Unknown", "total_seconds": 0}


# ══════════════════════════════════════════════════════════════
# Section 5: Text Utilities
# ══════════════════════════════════════════════════════════════

def truncate_text(text: str, max_length: int = 500, suffix: str = "...") -> str:
    if not text or len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def safe_author(comment) -> str:
    if comment.author is None:
        return "[deleted]"
    try:
        return comment.author.name
    except AttributeError:
        return "[unknown]"


# ══════════════════════════════════════════════════════════════
# Section 6: Stopwords
# ══════════════════════════════════════════════════════════════

STOPWORDS = frozenset({
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself", "she", "her", "hers", "herself",
    "it", "its", "itself", "they", "them", "their", "theirs", "themselves",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "am", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having", "do", "does", "did", "doing",
    "a", "an", "the", "and", "but", "if", "or", "because", "as",
    "until", "while", "of", "at", "by", "for", "with", "about",
    "against", "between", "through", "during", "before", "after",
    "above", "below", "to", "from", "up", "down", "in", "out",
    "on", "off", "over", "under", "again", "further", "then", "once",
    "here", "there", "when", "where", "why", "how", "all", "both",
    "each", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "s", "t", "can", "will", "just", "don", "should", "now",
    "d", "ll", "m", "o", "re", "ve", "y", "ain",
    "aren", "couldn", "didn", "doesn", "hadn", "hasn", "haven",
    "isn", "ma", "mightn", "mustn", "needn", "shan", "shouldn",
    "wasn", "weren", "won", "wouldn",
    "also", "would", "could", "may", "might", "shall", "must",
    "let", "us", "get", "got", "go", "went", "gone", "come",
    "came", "take", "took", "taken", "make", "made", "give", "gave",
    "given", "say", "said", "tell", "told", "think", "thought",
    "know", "knew", "known", "see", "saw", "seen", "want", "like",
    "one", "two", "even", "still", "well", "back", "much",
    "way", "thing", "things", "something", "anything", "nothing",
    "everything", "someone", "anyone", "everyone", "nobody",
    "really", "actually", "basically", "literally", "probably",
    "maybe", "perhaps", "however", "though", "although", "yet",
    "since", "already", "always", "never", "often", "sometimes",
    "rather", "quite", "pretty", "enough", "many", "several",
    "whether", "either", "neither", "else", "another",
    "around", "into", "onto", "upon", "along", "across",
    "behind", "beside", "beyond", "within", "without",
    "isn't", "aren't", "wasn't", "weren't", "hasn't", "haven't",
    "hadn't", "doesn't", "don't", "didn't", "won't", "wouldn't",
    "shan't", "shouldn't", "can't", "cannot", "couldn't",
    "mustn't", "needn't", "it's", "i'm", "you're", "he's",
    "she's", "we're", "they're", "i've", "you've", "we've",
    "they've", "i'd", "you'd", "he'd", "she'd", "we'd",
    "they'd", "i'll", "you'll", "he'll", "she'll", "we'll",
    "they'll", "that's", "what's", "who's", "here's", "there's",
    "when's", "where's", "why's", "how's", "let's",
    "im", "youre", "hes", "shes", "its", "were", "theyre",
    "ive", "youve", "weve", "theyve", "id", "youd", "hed",
    "shed", "wed", "theyd", "ill", "youll", "hell", "shell",
    "well", "theyll", "thats", "whats", "whos", "heres",
    "theres", "whens", "wheres", "whys", "hows", "lets",
    "didnt", "doesnt", "dont", "isnt", "arent", "wasnt",
    "werent", "hasnt", "havent", "hadnt", "wont", "wouldnt",
    "shant", "shouldnt", "cant", "couldnt", "mustnt", "neednt",
    "been", "being", "having", "doing",
    "able", "need", "going", "keep", "kept", "put",
    "every", "sure", "seems", "seem", "look", "looking",
    "right", "left", "good", "bad", "new", "old", "long",
    "great", "little", "big", "small", "large",
    "first", "last", "next", "used", "using", "use",
    "set", "try", "trying", "tried",
    "http", "https", "www", "com", "org", "reddit",
    "gt", "lt", "amp", "nbsp",
    "edit", "deleted", "removed", "etc", "eg", "ie",
})


def tokenize(text: str) -> list[str]:
    """
    Tokenize text into lowercase alphabetic words.
    Strips URLs, markdown, and punctuation.
    """
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    # Remove markdown links
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    # Remove markdown formatting
    text = re.sub(r'[*_~`>#\-|]', ' ', text)
    # Extract words (alpha only, 2+ chars)
    words = re.findall(r'[a-zA-Z]{2,}', text.lower())
    return words


def tokenize_no_stopwords(text: str) -> list[str]:
    """Tokenize and remove stopwords."""
    return [w for w in tokenize(text) if w not in STOPWORDS]


# ══════════════════════════════════════════════════════════════
# Section 7: Sentiment Analysis — Keyword Lexicon
# ══════════════════════════════════════════════════════════════

POSITIVE_WORDS = frozenset({
    # ── Agreement & Approval ──
    "agree", "agreed", "agrees", "agreeing", "agreement",
    "approve", "approved", "approves", "approval",
    "accept", "accepted", "accepting", "acceptable",
    "acknowledge", "acknowledged",
    "support", "supported", "supporting", "supportive",
    "endorse", "endorsed",
    "correct", "correctly",
    "valid", "validated",
    "fair", "fairly", "fairness",
    "reasonable", "reasonably",
    "legitimate", "legitimately",

    # ── Positive Emotion ──
    "good", "great", "excellent", "amazing", "awesome",
    "wonderful", "fantastic", "brilliant", "outstanding",
    "superb", "terrific", "marvelous", "magnificent",
    "exceptional", "remarkable", "incredible", "phenomenal",
    "love", "loved", "loving", "lovely",
    "happy", "happily", "happiness",
    "joy", "joyful", "joyous",
    "glad", "gladly",
    "pleased", "pleasant", "pleasure",
    "delight", "delighted", "delightful",
    "enjoy", "enjoyed", "enjoying", "enjoyable", "enjoyment",
    "fun", "funny", "humor", "humorous", "hilarious",
    "laugh", "laughing", "laughter",
    "smile", "smiling",
    "cheerful", "cheery",
    "grateful", "gratitude", "thankful", "thanks", "thank",
    "appreciate", "appreciated", "appreciating", "appreciation", "appreciative",

    # ── Quality & Value ──
    "best", "better", "finest",
    "perfect", "perfectly", "perfection",
    "ideal", "ideally",
    "beautiful", "beautifully", "beauty",
    "elegant", "elegantly", "elegance",
    "impressive", "impressed",
    "admire", "admired", "admirable", "admiration",
    "respect", "respected", "respectful", "respectfully",
    "worthy", "worthwhile", "worth",
    "valuable", "invaluable",
    "quality", "superior",
    "genuine", "genuinely",
    "authentic", "authentically",
    "meaningful", "meaningfully",

    # ── Helpfulness & Kindness ──
    "help", "helped", "helpful", "helpfully", "helping",
    "kind", "kindly", "kindness",
    "generous", "generously", "generosity",
    "caring", "compassion", "compassionate",
    "thoughtful", "thoughtfully", "thoughtfulness",
    "considerate", "consideration",
    "empathy", "empathetic", "empathize",
    "sympathetic", "sympathy", "sympathize",
    "warm", "warmth", "warmly",
    "friendly", "friendliness",
    "gentle", "gently", "gentleness",
    "patient", "patiently", "patience",
    "polite", "politely", "politeness",
    "courteous", "courtesy",
    "welcoming", "welcome", "welcomed",

    # ── Intelligence & Insight ──
    "smart", "intelligent", "intelligence",
    "wise", "wisely", "wisdom",
    "insightful", "insight", "insights",
    "clever", "cleverly",
    "creative", "creatively", "creativity",
    "innovative", "innovation",
    "brilliant", "brilliantly", "brilliance",
    "genius", "ingenious",
    "articulate", "articulated", "eloquent", "eloquently",
    "informative", "informed",
    "knowledgeable", "knowledge",
    "educational", "educate", "educated",
    "enlightening", "enlightened",
    "interesting", "intriguing", "fascinating", "captivating",
    "compelling", "convincing", "persuasive",
    "logical", "logically", "rational", "rationally",
    "nuanced", "nuance",
    "thorough", "thoroughly",
    "detailed", "comprehensive",

    # ── Success & Achievement ──
    "success", "successful", "successfully",
    "achieve", "achieved", "achievement",
    "accomplish", "accomplished", "accomplishment",
    "win", "winning", "winner", "won",
    "triumph", "triumphant",
    "progress", "progressing", "progressive",
    "improve", "improved", "improvement", "improving",
    "advance", "advanced", "advancement",
    "grow", "growing", "growth",
    "thrive", "thriving",
    "prosper", "prospering", "prosperity", "prosperous",
    "flourish", "flourishing",
    "excel", "excelling",
    "effective", "effectively", "effectiveness",
    "efficient", "efficiently", "efficiency",
    "productive", "productively", "productivity",
    "solution", "solve", "solved", "solving",

    # ── Strength & Courage ──
    "strong", "strongly", "strength", "strengthen",
    "brave", "bravely", "bravery",
    "courage", "courageous", "courageously",
    "bold", "boldly", "boldness",
    "confident", "confidently", "confidence",
    "determined", "determination",
    "resilient", "resilience",
    "capable", "capably", "capability",
    "powerful", "powerfully",
    "inspiring", "inspired", "inspiration", "inspirational",
    "motivating", "motivated", "motivation",
    "encouraging", "encouraged", "encouragement",
    "uplifting",
    "empowering", "empowered", "empowerment",
    "heroic", "hero", "heroes",
    "noble", "nobly",

    # ── Peace & Harmony ──
    "peace", "peaceful", "peacefully",
    "calm", "calmly", "calmness",
    "serene", "serenity",
    "tranquil", "tranquility",
    "harmonious", "harmony",
    "balanced", "balance",
    "stable", "stability",
    "safe", "safely", "safety",
    "secure", "securely", "security",
    "comfort", "comfortable", "comfortably", "comforting",
    "relax", "relaxed", "relaxing",
    "soothe", "soothing",

    # ── Trust & Honesty ──
    "trust", "trusted", "trusting", "trustworthy",
    "honest", "honestly", "honesty",
    "truthful", "truthfully", "truth",
    "sincere", "sincerely", "sincerity",
    "loyal", "loyally", "loyalty",
    "faithful", "faithfully",
    "reliable", "reliably", "reliability",
    "dependable",
    "credible", "credibility",
    "integrity",
    "transparent", "transparency",

    # ── Hope & Optimism ──
    "hope", "hopeful", "hopefully", "hoping",
    "optimistic", "optimism",
    "promise", "promising",
    "potential", "potentially",
    "opportunity", "opportunities",
    "possible", "possibility",
    "bright", "brighter",
    "positive", "positively", "positivity",
    "upbeat",

    # ── Common Reddit Positive ──
    "upvote", "upvoted",
    "based",
    "wholesome",
    "kudos",
    "bravo",
    "cheers",
    "congrats", "congratulations", "congratulate",
    "props",
    "spot", # as in "spot on"
    "nailed",
    "exactly",
    "absolutely",
    "definitely", "definite",
    "certainly", "certain",
    "precisely",
    "undoubtedly",
    "indeed",
    "clearly",
    "obviously",
    "truly", "true",
    "beautifully",
    "wonderfully",
    "fantastically",
    "amazingly",
    "incredibly",
    "remarkably",
    "exceptionally",
    "perfectly",
    "nicely",
    "splendid",
    "stellar",
    "tops",
    "gem",
    "masterpiece",
    "goat",
    "legend", "legendary",
    "clutch",
    "fire",
    "lit",
    "dope",
    "sick",
    "rad",
    "epic",
    "mint",
    "solid",
    "clean",
    "fresh",
    "crisp",
    "smooth",
    "slick",
    "sweet",
    "neat",
    "cool",
    "wow",
    "yay",
    "hooray",
    "hurray",
})

NEGATIVE_WORDS = frozenset({
    # ── Disagreement & Disapproval ──
    "disagree", "disagreed", "disagrees", "disagreeing", "disagreement",
    "disapprove", "disapproved", "disapproval",
    "reject", "rejected", "rejecting", "rejection",
    "deny", "denied", "denying", "denial",
    "refuse", "refused", "refusing", "refusal",
    "oppose", "opposed", "opposing", "opposition",
    "object", "objected", "objecting", "objection",
    "invalid", "invalidated",
    "wrong", "wrongly", "wrongful",
    "incorrect", "incorrectly",
    "false", "falsely", "falsehood", "fallacy", "fallacious",
    "misleading", "mislead", "misled",
    "misinformation", "disinformation",
    "flawed", "flaw", "flaws",
    "faulty",
    "illogical", "irrational", "irrationally",
    "absurd", "absurdly", "absurdity",
    "ridiculous", "ridiculously",
    "nonsense", "nonsensical",
    "preposterous",
    "ludicrous",

    # ── Negative Emotion ──
    "bad", "badly",
    "terrible", "terribly",
    "horrible", "horribly",
    "awful", "awfully",
    "dreadful", "dreadfully",
    "atrocious", "atrociously",
    "abysmal", "abysmally",
    "appalling",
    "deplorable",
    "miserable", "miserably", "misery",
    "wretched",
    "pathetic", "pathetically",
    "pitiful", "pitifully",
    "sad", "sadly", "sadness", "saddening",
    "unhappy", "unhappily", "unhappiness",
    "depressed", "depressing", "depression",
    "hopeless", "hopelessly", "hopelessness",
    "despair", "despairing",
    "gloomy", "gloom",
    "bleak", "bleakly",
    "dismal", "dismally",
    "tragic", "tragically", "tragedy",
    "devastating", "devastated", "devastation",
    "heartbreaking", "heartbroken",
    "sorrowful", "sorrow",
    "grief", "grieving", "grieve",
    "mourn", "mourning",
    "suffer", "suffered", "suffering", "suffers",
    "pain", "painful", "painfully",
    "hurt", "hurting", "hurtful",
    "anguish", "anguished",
    "agony", "agonizing",
    "torment", "tormenting", "tormented",
    "distress", "distressing", "distressed",
    "upset", "upsetting",
    "frustrated", "frustrating", "frustration",
    "annoyed", "annoying", "annoyance",
    "irritated", "irritating", "irritation",
    "angry", "angrily", "anger",
    "furious", "furiously", "fury",
    "enraged", "enraging", "rage", "raging",
    "outraged", "outrageous", "outrageously", "outrage",
    "infuriated", "infuriating",
    "livid",
    "hostile", "hostility",
    "aggressive", "aggressively", "aggression",
    "violent", "violently", "violence",
    "bitter", "bitterly", "bitterness",
    "resentful", "resentment", "resent",
    "vengeful", "vengeance",
    "spiteful", "spite",
    "malicious", "maliciously", "malice",
    "hateful", "hate", "hatred", "hating",
    "loathe", "loathing", "loathsome",
    "detest", "detested", "detesting", "detestable",
    "despise", "despised", "despising", "despicable",
    "disgusting", "disgusted", "disgust",
    "revolting", "repulsive", "repulsed",
    "sickening", "sickened",
    "nauseating", "nauseous",
    "vile", "vileness",
    "repugnant",
    "abhorrent", "abhor",
    "contempt", "contemptuous", "contemptible",

    # ── Fear & Anxiety ──
    "fear", "fearful", "fearfully", "fearing", "feared",
    "afraid", "frightened", "frightening", "fright",
    "scared", "scary", "scare",
    "terrified", "terrifying", "terror", "terrorism", "terrorist",
    "horrified", "horrifying", "horror", "horrific",
    "alarmed", "alarming", "alarm",
    "panicked", "panic", "panicking",
    "anxious", "anxiously", "anxiety",
    "worried", "worrying", "worry", "worries",
    "nervous", "nervously", "nervousness",
    "dread", "dreading", "dreaded",
    "uneasy", "uneasily", "unease",
    "tense", "tension",
    "stressed", "stressful", "stress",
    "overwhelmed", "overwhelming",
    "paranoid", "paranoia",

    # ── Insults & Attacks ──
    "stupid", "stupidly", "stupidity",
    "idiot", "idiotic", "idiotically", "idiots",
    "dumb", "dumber", "dumbest",
    "fool", "foolish", "foolishly", "foolishness", "fools",
    "moron", "moronic", "morons",
    "imbecile", "imbeciles",
    "ignorant", "ignorance", "ignorantly",
    "incompetent", "incompetence",
    "inept", "ineptly", "ineptitude",
    "useless", "uselessly", "uselessness",
    "worthless", "worthlessness",
    "pointless", "pointlessly", "pointlessness",
    "meaningless",
    "brainless",
    "clueless",
    "senseless", "senselessly",
    "mindless", "mindlessly",
    "thoughtless", "thoughtlessly", "thoughtlessness",
    "careless", "carelessly", "carelessness",
    "reckless", "recklessly", "recklessness",
    "irresponsible", "irresponsibly", "irresponsibility",
    "negligent", "negligence", "negligently",
    "lazy", "lazily", "laziness",
    "coward", "cowardly", "cowardice", "cowards",
    "weak", "weakly", "weakness", "weaknesses",
    "pathetic", "loser", "losers",

    # ── Deception & Dishonesty ──
    "lie", "lied", "lies", "lying", "liar", "liars",
    "cheat", "cheated", "cheating", "cheater", "cheaters",
    "fraud", "fraudulent", "fraudulently",
    "scam", "scammed", "scammer", "scammers",
    "deceive", "deceived", "deceiving", "deception", "deceptive",
    "manipulate", "manipulated", "manipulating", "manipulation", "manipulative",
    "exploit", "exploited", "exploiting", "exploitation", "exploitative",
    "corrupt", "corrupted", "corruption",
    "dishonest", "dishonestly", "dishonesty",
    "hypocrite", "hypocritical", "hypocrisy", "hypocrites",
    "pretend", "pretending", "pretentious",
    "fake", "faked", "faking",
    "phony", "sham",
    "betray", "betrayed", "betrayal", "betraying",
    "treacherous", "treachery",

    # ── Harm & Destruction ──
    "harm", "harmed", "harmful", "harmfully", "harming",
    "damage", "damaged", "damaging", "damages",
    "destroy", "destroyed", "destroying", "destruction", "destructive",
    "ruin", "ruined", "ruining", "ruinous",
    "wreck", "wrecked", "wrecking",
    "devastate", "devastated", "devastating", "devastation",
    "demolish", "demolished",
    "annihilate", "annihilated", "annihilation",
    "obliterate", "obliterated",
    "ravage", "ravaged",
    "sabotage", "sabotaged",
    "undermine", "undermined", "undermining",
    "threaten", "threatened", "threatening", "threat", "threats",
    "endanger", "endangered", "endangering",
    "abuse", "abused", "abusing", "abusive", "abusively",
    "assault", "assaulted", "assaulting",
    "attack", "attacked", "attacking", "attacks",
    "persecute", "persecuted", "persecution",
    "oppress", "oppressed", "oppressing", "oppression", "oppressive",
    "tyranny", "tyrannical", "tyrant",
    "brutality", "brutal", "brutally",
    "cruelty", "cruel", "cruelly",
    "vicious", "viciously", "viciousness",
    "savage", "savagely", "savagery",
    "barbaric", "barbarous", "barbarism",
    "inhumane", "inhumanely", "inhumanity",
    "atrocity", "atrocities",
    "genocide", "genocidal",
    "murder", "murdered", "murdering", "murderous", "murderer",
    "kill", "killed", "killing", "killer",
    "slaughter", "slaughtered",
    "massacre", "massacred",
    "torture", "tortured", "torturing",

    # ── Prejudice & Discrimination ──
    "racist", "racism", "racists", "racially",
    "sexist", "sexism", "sexists",
    "bigot", "bigoted", "bigotry", "bigots",
    "prejudice", "prejudiced", "prejudicial",
    "discriminate", "discriminated", "discrimination", "discriminatory",
    "xenophobia", "xenophobic",
    "intolerant", "intolerance",
    "supremacist", "supremacy",
    "chauvinist", "chauvinistic", "chauvinism",
    "misogynist", "misogynistic", "misogyny",
    "homophobic", "homophobia",
    "transphobic", "transphobia",
    "stereotype", "stereotyped", "stereotyping", "stereotypes",
    "marginalize", "marginalized", "marginalization",

    # ── Failure & Inadequacy ──
    "fail", "failed", "failing", "failure", "failures",
    "lose", "losing", "loss", "lost",
    "defeat", "defeated",
    "collapse", "collapsed", "collapsing",
    "decline", "declined", "declining",
    "deteriorate", "deteriorated", "deteriorating", "deterioration",
    "stagnate", "stagnated", "stagnating", "stagnation",
    "regress", "regressed", "regression",
    "disaster", "disastrous", "disastrously",
    "catastrophe", "catastrophic",
    "fiasco",
    "debacle",
    "mediocre", "mediocrity",
    "inferior", "inferiority",
    "substandard",
    "inadequate", "inadequacy",
    "deficient", "deficiency",
    "lacking",
    "insufficient", "insufficiently",

    # ── Negativity & Cynicism ──
    "never", "nobody", "none", "nothing", "nowhere",
    "impossible", "impossibly", "impossibility",
    "hopeless", "hopelessly", "hopelessness",
    "pointless", "meaningless", "futile", "futility",
    "cynical", "cynicism", "cynic",
    "pessimistic", "pessimism", "pessimist",
    "skeptical", "skepticism",
    "doubtful", "doubt", "doubting", "doubts",
    "suspicious", "suspiciously", "suspicion",
    "distrust", "distrustful",
    "apathetic", "apathy",
    "indifferent", "indifference",

    # ── Common Reddit Negative ──
    "downvote", "downvoted",
    "cringe", "cringy", "cringeworthy",
    "toxic", "toxicity",
    "troll", "trolling", "trolls",
    "spam", "spamming", "spammer",
    "clickbait",
    "shill", "shilling", "shills",
    "circlejerk",
    "gatekeep", "gatekeeping", "gatekeepers",
    "strawman", "strawmen",
    "whataboutism",
    "gaslighting", "gaslight", "gaslighted",
    "cope", "copium",
    "delusional", "delusion", "delusions",
    "naive", "naively", "naivety",
    "gullible",
    "brainwashed", "brainwashing",
    "propaganda",
    "censorship", "censored", "censor",
    "ban", "banned", "banning",
    "removed", "removal",
    "trash", "trashed", "trashy",
    "garbage",
    "junk",
    "crap", "crappy",
    "suck", "sucks", "sucked", "sucking",
    "stink", "stinks", "stunk", "stinking",
    "boring", "bored", "boredom",
    "lame", "lamest",
    "meh",
    "ugh",
    "yikes",
    "smh",
    "facepalm",
    "wtf",
    "bs",
})

# Words that negate the next sentiment word
NEGATION_WORDS = frozenset({
    "not", "no", "never", "neither", "nor", "none",
    "nobody", "nothing", "nowhere", "hardly", "barely",
    "scarcely", "seldom", "rarely",
    "don't", "doesn't", "didn't", "isn't", "aren't",
    "wasn't", "weren't", "hasn't", "haven't", "hadn't",
    "won't", "wouldn't", "shouldn't", "couldn't", "can't",
    "cannot", "mustn't",
    "dont", "doesnt", "didnt", "isnt", "arent",
    "wasnt", "werent", "hasnt", "havent", "hadnt",
    "wont", "wouldnt", "shouldnt", "couldnt", "cant",
    "mustnt",
})

# Intensifier words that amplify the next sentiment word
INTENSIFIER_WORDS = frozenset({
    "very", "really", "extremely", "incredibly", "absolutely",
    "completely", "totally", "utterly", "entirely", "thoroughly",
    "highly", "deeply", "strongly", "immensely", "enormously",
    "particularly", "especially", "exceptionally", "extraordinarily",
    "remarkably", "significantly", "substantially", "considerably",
    "seriously", "genuinely", "truly", "profoundly",
    "so", "such", "quite", "rather", "pretty",
    "super", "mega", "ultra",
})


def analyze_sentiment(text: str) -> dict:
    """
    Perform keyword-based sentiment analysis on a text.

    Uses a lexicon of positive and negative words with support
    for negation handling and intensity modifiers.

    Args:
        text: The text to analyze

    Returns:
        Dictionary with:
            - score: float between -1.0 and 1.0
            - label: 'positive', 'negative', or 'neutral'
            - positive_count: number of positive words found
            - negative_count: number of negative words found
            - positive_words: list of positive words found
            - negative_words: list of negative words found
            - magnitude: absolute strength of sentiment (0.0 to 1.0)
    """
    words = tokenize(text)
    if not words:
        return {
            "score": 0.0,
            "label": "neutral",
            "positive_count": 0,
            "negative_count": 0,
            "positive_words": [],
            "negative_words": [],
            "magnitude": 0.0,
        }

    positive_found = []
    negative_found = []
    raw_score = 0.0

    negated = False
    intensified = False

    for i, word in enumerate(words):
        # Check for negation
        if word in NEGATION_WORDS:
            negated = True
            continue

        # Check for intensifier
        if word in INTENSIFIER_WORDS:
            intensified = True
            continue

        # Determine base sentiment value
        base_value = 0.0
        if word in POSITIVE_WORDS:
            base_value = 1.0
        elif word in NEGATIVE_WORDS:
            base_value = -1.0

        if base_value != 0.0:
            # Apply intensifier (1.5x)
            if intensified:
                base_value *= 1.5

            # Apply negation (flip sign, reduce magnitude slightly)
            if negated:
                base_value *= -0.75

            raw_score += base_value

            if base_value > 0:
                positive_found.append(word)
            else:
                negative_found.append(word)

        # Reset modifiers (they apply to the very next content word)
        negated = False
        intensified = False

    # Normalize score to [-1, 1] using a sigmoid-like function
    # This prevents extreme scores from dominating
    total_sentiment_words = len(positive_found) + len(negative_found)

    if total_sentiment_words == 0:
        normalized_score = 0.0
    else:
        # Scale by total words to account for text length
        raw_ratio = raw_score / max(len(words), 1)
        # Apply tanh to compress into [-1, 1]
        normalized_score = math.tanh(raw_ratio * 5)

    # Determine label
    if normalized_score > 0.05:
        label = "positive"
    elif normalized_score < -0.05:
        label = "negative"
    else:
        label = "neutral"

    # Magnitude is the absolute sentiment strength
    magnitude = min(abs(normalized_score), 1.0)

    return {
        "score": round(normalized_score, 4),
        "label": label,
        "positive_count": len(positive_found),
        "negative_count": len(negative_found),
        "positive_words": sorted(set(positive_found)),
        "negative_words": sorted(set(negative_found)),
        "magnitude": round(magnitude, 4),
    }


# ══════════════════════════════════════════════════════════════
# Section 8: User / Author Analysis
# ══════════════════════════════════════════════════════════════

def analyze_user_activity(tree: list[dict], post_author: str = "") -> dict[str, dict]:
    """
    Walk the entire comment tree and build per-user analytics.

    For each author, computes:
        - total_comments: number of comments/replies
        - total_score: sum of all scores
        - avg_score: average score per comment
        - total_words: total word count across all comments
        - unique_words: number of distinct words (after stopword removal)
        - vocabulary_richness: unique_words / total_content_words
        - most_used_words: top 20 words by frequency (stopwords removed)
        - word_frequencies: dict of word -> count (top 50)
        - deepest_reply: maximum depth reached
        - sentiment_avg: average sentiment score across comments
        - sentiment_label: overall sentiment label
        - is_post_author: whether this user is the OP
        - comments: list of hierarchy strings for all their comments
        - first_comment_utc: timestamp of earliest comment
        - last_comment_utc: timestamp of latest comment

    Args:
        tree: Structured comment tree
        post_author: Username of the post author (for OP tagging)

    Returns:
        Dictionary mapping author names to their analytics dicts
    """
    users = {}

    def _walk(comments: list[dict]):
        for c in comments:
            if "_truncated" in c:
                continue

            author = c.get("author", "[unknown]")

            if author not in users:
                users[author] = {
                    "total_comments": 0,
                    "total_score": 0,
                    "total_words": 0,
                    "unique_words_set": set(),
                    "all_content_words": [],
                    "word_counter": Counter(),
                    "deepest_reply": 0,
                    "sentiment_scores": [],
                    "is_post_author": (author == post_author and author not in ("[deleted]", "[unknown]")),
                    "comments": [],
                    "first_comment_utc": float('inf'),
                    "last_comment_utc": 0,
                }

            u = users[author]
            u["total_comments"] += 1
            u["total_score"] += c.get("score", 0)
            u["deepest_reply"] = max(u["deepest_reply"], c.get("depth", 0))
            u["comments"].append(c.get("hierarchy", ""))

            # Timestamps
            created = c.get("created_utc", 0)
            if created > 0:
                u["first_comment_utc"] = min(u["first_comment_utc"], created)
                u["last_comment_utc"] = max(u["last_comment_utc"], created)

            # Word analysis
            body = c.get("body", "")
            all_words = tokenize(body)
            content_words = tokenize_no_stopwords(body)

            u["total_words"] += len(all_words)
            u["unique_words_set"].update(content_words)
            u["all_content_words"].extend(content_words)
            u["word_counter"].update(content_words)

            # Sentiment
            sentiment = c.get("sentiment")
            if sentiment:
                u["sentiment_scores"].append(sentiment.get("score", 0))

            _walk(c.get("replies", []))

    _walk(tree)

    # Post-process each user
    result = {}
    for author, u in users.items():
        total = u["total_comments"]
        avg_score = round(u["total_score"] / total, 1) if total > 0 else 0

        content_word_count = len(u["all_content_words"])
        unique_count = len(u["unique_words_set"])
        vocab_richness = round(unique_count / content_word_count, 4) if content_word_count > 0 else 0

        top_words = u["word_counter"].most_common(20)
        word_freq_top50 = dict(u["word_counter"].most_common(50))

        sentiment_scores = u["sentiment_scores"]
        if sentiment_scores:
            sentiment_avg = round(sum(sentiment_scores) / len(sentiment_scores), 4)
        else:
            sentiment_avg = 0.0

        if sentiment_avg > 0.05:
            sentiment_label = "positive"
        elif sentiment_avg < -0.05:
            sentiment_label = "negative"
        else:
            sentiment_label = "neutral"

        first_utc = u["first_comment_utc"] if u["first_comment_utc"] != float('inf') else 0
        last_utc = u["last_comment_utc"]

        result[author] = {
            "total_comments": total,
            "total_score": u["total_score"],
            "avg_score": avg_score,
            "total_words": u["total_words"],
            "unique_words": unique_count,
            "vocabulary_richness": vocab_richness,
            "most_used_words": top_words,
            "word_frequencies": word_freq_top50,
            "deepest_reply": u["deepest_reply"],
            "sentiment_avg": sentiment_avg,
            "sentiment_label": sentiment_label,
            "is_post_author": u["is_post_author"],
            "comments": u["comments"],
            "comment_count": total,
            "first_comment_utc": first_utc,
            "last_comment_utc": last_utc,
            "first_comment_readable": format_timestamp(first_utc) if first_utc else "N/A",
            "last_comment_readable": format_timestamp(last_utc) if last_utc else "N/A",
        }

    return result