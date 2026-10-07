import re

PAGES = {
    "lee": ("LSM: About Witness Lee", "https://www.livingstream.com/en/content/7-about-witness-lee"),
    "nee": ("LSM: About Watchman Nee", "https://www.livingstream.com/en/content/6-about-watchman-nee"),
    "lsm": ("About Living Stream Ministry", "https://www.livingstream.com/en/content/4-about-us"),
    "faith": ("LSM: Statement of Faith", "https://www.lsm.org/lsm-statement-faith.html"),
    "churches": ("The local churches: Frequently Asked Questions", "https://localchurches.org/faq/"),
    "standing": ("The local churches: Our Standing", "https://localchurches.org/beliefs/our-standing/"),
    "recovery": ("The local churches: Concerning the Recovery", "https://localchurches.org/beliefs/recovery/"),
    "life": ("The local churches: Concerning the Church Life", "https://localchurches.org/beliefs/church-life/"),
    "beliefs": ("The local churches: Our Beliefs", "https://localchurches.org/beliefs/our-beliefs/"),
    "introduction": ("DCP: An Introduction to Watchman Nee and Witness Lee", "https://contendingforthefaith.org/en/an-introduction-to-watchman-nee-and-witness-lee/"),
    "responses": ("DCP: Responses to Criticism", "https://contendingforthefaith.org/en/responses-to-criticism/"),
    "dcp_faith": ("DCP: The Faith", "https://contendingforthefaith.org/en/the-faith/"),
    "faithfulword": ("A Faithful Word: Ministry and church-life articles", "https://afaithfulword.org/"),
    "faq2": ("The local churches: FAQs on God's economy and the Trinity", "https://localchurches.org/faq/?page=2"),
    "faq3": ("The local churches: FAQs on other Christians and practical matters", "https://localchurches.org/faq/?page=3"),
    "defense": ("Defense and Confirmation Project: Who Are We", "https://contendingforthefaith.org/en/who-are-we/"),
}

def normalize_ministry_question(question):
    # Correct only known spellings of this ministry term, not unrelated uses of recovery.
    return re.sub(r"\blord(?:['’]s|s)?\s+(?:recovery|recvoery|recovrey|reocvery|revovery|recoverey)\b",
                  "Lord's recovery", question, flags=re.I)

TOPICS = {
    'recovery': ['recovery'],
    'church_life': ['life', 'standing'],
    'faith': ['faith', 'beliefs', 'dcp_faith'],
    'witness_lee': ['lee', 'introduction'],
    'watchman_nee': ['nee', 'introduction'],
    'publisher': ['lsm'],
    'church_practice': ['churches', 'standing'],
    'trinity': ['faq2', 'faith'],
    'practical_matters': ['faq3'],
    'clarification': ['faithfulword', 'dcp_faith', 'defense', 'responses'],
}

def preferred_pages(question, topics=None):
    text = normalize_ministry_question(question).casefold().replace('’', "'")
    if topics is not None:
        return [PAGES[key][1] for key in dict.fromkeys(key for topic in topics for key in TOPICS.get(topic, []))]
    keys = []
    if "lord's recovery" in text or re.search(r"\b(?:the|what is) recovery\b", text):
        keys.append('recovery')
    if 'church life' in text:
        keys.append('life')
    if text.strip(' ?.!') in {'life', 'oneness', 'church', 'salvation'}:
        keys.extend(['life', 'faith', 'beliefs'])
    if re.search(r'\b(?:statement of faith|believe|beliefs|trinity|triune)\b', text):
        keys.extend(['faith', 'beliefs', 'dcp_faith'])
    if re.search(r'\b(?:modalism|modalistic|tritheism|economy of god)\b', text):
        keys.append('faq2')
    if re.search(r'\b(?:financ\w*|money|other christians|other believers|government)\b', text):
        keys.append('faq3')
    if re.search(r'\b(?:headquarters|leader|leadership|pray.reading|meetings)\b', text):
        keys.append('churches')
    return [PAGES[key][1] for key in dict.fromkeys(keys)]
