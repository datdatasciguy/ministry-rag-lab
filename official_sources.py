import re
from question_policy import original_wording

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

def preferred_pages(question):
    text = question.casefold().replace('’', "'")
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

def official_introduction(question, answer_original=False):
    text = original_wording(question, answer_original)[0].casefold()
    lee = bool(re.search(r"\b(?:witness lee|brother lee)\b", text))
    nee = bool(re.search(r"\b(?:watchman nee|brother nee)\b", text))
    lsm = bool(re.search(r"\b(?:living stream ministry|lsm)\b", text))
    churches = bool(re.search(r"\blocal churches?\b", text))
    recovery = "lord's recovery" in text
    controversy = bool(re.search(r"\b(?:controvers\w*|cults?|heretic\w*|heresy|accusations?|criticisms?|allegations?|brainwash\w*|scam|toxic)\b", text))
    identity = bool(re.fullmatch(r"(?:please )?(?:who (?:is|are|was|were)|what (?:is|are)|tell me about|introduce|give (?:me )?(?:an? )?(?:introduction|biography)(?: of| to)?) (?:the )?(?:witness lee|brother lee|watchman nee|brother nee|living stream ministry|lsm|local churches?)(?: (?:and|&) (?:witness lee|watchman nee|living stream ministry|lsm))*", text))
    authorship = bool(re.fullmatch(r"who (?:wrote|authored|published|writes|publishes) (?:these|the|this|ministry|these ministry|the ministry) books", text))
    general_label = bool(re.fullmatch(r"(?:please )?(?:what (?:is|are) (?:a |the )?cults?|define (?:a )?cult|what does (?:the (?:word|term) )?cult mean|what makes (?:a group|a church|something) a cult)", text))
    targeted = lee or nee or lsm or churches or recovery
    personal_concern = bool(re.search(r'\b(?:i|my|someone)\b', text) and re.search(r'\b(?:hurt|abused|assaulted|threatened|coerced|pressured|unsafe)\b', text))
    if personal_concern:
        return None
    if not identity and not authorship and not general_label and not (controversy and targeted):
        return None
    sentences, keys = [], []
    if general_label:
        sentences.append("This ministry-study tool does not provide a general classification of religious groups. For an introduction to this ministry and the local churches, a constructive starting point is their stated Christian faith, experience of Christ as life, and practice of oneness and church life. Read their own presentations below for the fuller explanation.")
        keys.extend(["faith", "beliefs", "life", "introduction"])
    if authorship:
        sentences.append("Living Stream Ministry publishes the ministry of Watchman Nee and Witness Lee. Consult each book's author information for its specific attribution; Bible texts and other contributors should not be attributed to these authors by default.")
        keys.extend(["lsm", "lee", "nee"])
    if lee:
        sentences.append("LSM presents Witness Lee as a Christian minister and co-worker of Watchman Nee, whose ministry includes the Life-study of the Bible and contributions to the Recovery Version's study aids.")
        keys.append("lee")
    if nee:
        sentences.append("LSM presents Watchman Nee as a Christian preacher, teacher and writer whose ministry drew on his study of the Bible and spiritual writings.")
        keys.append("nee")
    if lsm:
        sentences.append("Living Stream Ministry describes itself as a nonprofit publisher of Watchman Nee and Witness Lee, supplying spiritual nourishment for believers' growth in the divine life and the building up of the Body of Christ.")
        keys.extend(["lsm", "faith"])
    if churches or recovery:
        sentences.append("The local churches describe themselves as local expressions of the church, meeting in the Lord's name on the ground of oneness. Their own introductions explain their standing, the recovery and church life.")
        keys.extend(["churches", "standing", "recovery", "life"])
    if controversy and not general_label:
        sentences.append("For this question, read the ministry's own statements and the Defense and Confirmation Project's explanation and responses. These pages present their own position; this introductory response does not independently assess an allegation or settle a controversy.")
        keys.extend(["faith", "introduction", "defense", "responses"])
    return {"answer": "\n\n".join(sentences), "official_intro": True,
            "official_notice": "Official and associated introductions · the publishers' and communities' own presentation. No local-model biography or controversy judgment was generated.",
            "official_links": [{"title": PAGES[key][0], "url": PAGES[key][1]} for key in dict.fromkeys(keys)],
            "sources": [], "citations": [], "abstain": False, "support_level": "official", "attempts": 0}
