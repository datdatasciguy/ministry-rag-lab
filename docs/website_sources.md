# Reviewed website references

The website importer adds public HTML articles to a **new** local index. It preserves your original book index, uses the same embedding model, and keeps author and collection filters intact. The reviewed seed set includes LSM's Statement of Faith and biographies, all three localchurches.org FAQ pages, its beliefs/recovery/church-life introductions, DCP introductions and responses, and A Faithful Word.

```bash
python web_sources.py --index data/books.sqlite --output data/books-web.sqlite
python app.py --index data/books-web.sqlite
```

The importer caches pages privately under `data/website-cache`, records canonical URL, publisher, UTC retrieval time and HTML hash, and reuses cached downloads on another run. It checks robots policy, waits at least one second between public requests, restricts redirects to reviewed HTTPS domains, and stops on access/rate-limit errors. It does not log in or bypass restrictions.

Add reviewed pages later with one or more `--url` arguments. Use a new output filename each time. Existing URLs are retained rather than silently refreshed. This is a bounded seed collection, not a whole-site crawl. A domain allowlist is a provenance boundary, not a guarantee that every article fits every question.

## Retrieval preference

Up to three relevant reviewed website pages are promoted ahead of ordinary book matches for recognized introductory and FAQ topics. The local model identifies introductory topics and maps those categories to the relevant FAQ/introduction pages. Questions are not mapped to canned answers. Promotion requires a lexical match and an eligible author/collection scope. Other questions use the ordinary hybrid ranking, including website articles, so a biography's incidental mention of a wife does not take priority over a teaching on finding a mate. The original book retrieval fills the remaining slots. Website priority is a user preference, not a trained relevance model or proof of authority.

Website cards display their publisher and download date, with the original page link. They belong to the ministry collection but are attributed to their website publisher, not automatically to Witness Lee or Watchman Nee. Strict individual-author filters exclude organizational pages. Identity questions can still show separately labeled official links. Bible-only and footnote-only searches exclude website articles.

Deep research includes the website sections when you start the app with the enlarged index. A saved research job from the older index cannot resume against a different index; start a new job to keep coverage and citations consistent.

## Answer style

Directly supported teaching is presented naturally: **The church life is ...**, followed by explanation and source citations. The model is instructed to preserve ministry vocabulary and qualifications, combine repeated points and respond constructively to critical wording. It should neither echo insults nor judge a questioner's motives. A personal concern is not dismissed merely because a source offers a positive introduction.

Identity and introductory questions retrieve indexed source passages and generate an answer with ordinary evidence checks. Source cards retain website publisher information. The answer presents the ministry directly, without a routine outsider-analysis or controversy notice. Answer prompting and retrieval preferences change model behavior without training or fine-tuning its weights.

For slur definitions phrased as insults and questions that demean an entire group, the answer displays **I interpreted your question as ...** with respectful wording guidance. Advanced **Exactly as asked**, or appending **Exactly as I asked**, requests the original wording. The tool refuses demeaning framing rather than generating a hostile answer. Critical ministry questions, respectful definitions and specific personal concerns are not treated as inappropriate. This is a limited explicit routing rule, not a claim to recognize every possible inappropriate question.

In this Bible/ministry study context, **What's wrong with Jews?** is interpreted as a question about actions or religious practices criticized in particular biblical accounts. That interpreted question is searched and answered from the RAG. The model must identify specific passages, actors and conduct rather than turn a local criticism into a claim about Jewish identity or Jews generally. If you mean a particular incident, naming it gives a more precise answer.

Keep caches, enlarged indexes and research results local. GitHub and code-only packages contain importer code and documentation, not downloaded articles.
