import re

def original_wording(question, requested=False):
    text = re.sub(r'\s+', ' ', question.replace('’', "'")).strip(' ?.! ')
    insist = re.search(r"(?:[.,;:?!]\s*|\s+)(?:answer )?(?:exactly as (?:i )?asked|do not rephrase|use (?:my|the) original wording)$", text, re.I)
    return (text[:insist.start()].strip(' ?.!,:;'), True) if insist else (text, requested)

def respectful_question(question, answer_original=False):
    text, original = original_wording(question, answer_original)
    slur = re.fullmatch(r"(?:what (?:is|are)|what'?s|whats|define) (?:a |an |the )?(?:faggots?|kikes?|niggers?|trannies)", text, re.I)
    groups = r'(?:jews|jewish people|muslims|christians|black people|white people|asian people|women|men|gay people|transgender people|disabled people)'
    demeaning = re.fullmatch(r"(?:what(?: is|'s|s) wrong with (?:all |the )?" + groups + r"|why are (?:all |the )?" + groups + r" (?:so )?(?:evil|inferior|stupid|worthless|disgusting|vermin))", text, re.I)
    if not slur and not demeaning:
        return None
    if original:
        return {'answer': 'I cannot answer in a way that demeans people through a slur or treats a whole group as defective. I can explain a term respectfully or discuss a specific belief, practice or concern.',
                'question_refused': True, 'policy_notice': 'Original wording requested; no substitute question was answered.',
                'sources': [], 'citations': [], 'abstain': True, 'support_level': 'none', 'attempts': 0}
    if demeaning and re.match(r"what(?: is|'s|s) wrong with\b", text, re.I) and re.search(r'\b(?:jews|jewish people)\b', text, re.I):
        return {'query_rewrite': 'Which actions or religious practices are criticized in specific biblical accounts involving Jewish people, and how does the ministry explain those passages?',
                'search_question': 'Jews religious practices criticism biblical accounts',
                'interpreted_question': 'Which actions or religious practices are criticized in specific biblical accounts involving Jewish people, and how does the ministry explain those passages?',
                'policy_notice': 'This interpretation concerns conduct in particular passages, not Jewish identity or a judgment about Jews generally.'}
    if slur:
        interpreted = 'What does this offensive term refer to, and what is respectful wording instead?'
        if re.search(r'faggot', text, re.I):
            answer = 'That is an offensive slur directed at gay men, also used as a general insult. Use “gay man” when that identity is relevant, or simply refer to the person. A question about a belief or behavior can be asked specifically without using a slur.'
        else:
            answer = 'That wording uses a derogatory label for a group of people. We can discuss identity, beliefs, history or a specific concern using respectful terms rather than an insult. Please name the topic you want to understand.'
    else:
        group = re.search(groups, text, re.I)[0]
        interpreted = 'How can ' + group + ' and their beliefs or experiences be discussed respectfully?'
        answer = 'People are not defective because they belong to a religious, ethnic or other identity group. Individuals differ in their beliefs and experiences. Ask about a specific teaching, historical question or behavior, and we can discuss that without making a negative claim about the whole group.'
    return {'answer': answer, 'interpreted_question': interpreted, 'policy_notice': 'Respectful wording guidance; this is not a quoted ministry passage.',
            'policy_intro': True, 'sources': [], 'citations': [], 'abstain': False, 'support_level': 'guidance', 'attempts': 0}
