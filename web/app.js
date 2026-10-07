const element = id => document.getElementById(id);
let modelProfiles = [];
let defaultModel = '';

function makeNode(tag, text, className) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}


function citationLink(number, prefix = 'source') {
  const link = makeNode('a', '[' + number + ']', 'citation');
  link.href = '#' + prefix + '-' + number;
  link.setAttribute('aria-label', 'Read supporting passage ' + number);
  link.addEventListener('click', () => {
    const source = element(prefix + '-' + number);
    if (source) source.focus({preventScroll: true});
  });
  return link;
}

function appendInline(node, text, sourceCount, prefix = 'source') {
  // Build DOM nodes so model text cannot inject HTML or external links.
  const pattern = /\[(\d+(?:\s*,\s*\d+)*)\]|\*\*([^*\n]+)\*\*|__([^_\n]+)__|\*([^*\n]+)\*|_([^_\n]+)_|`([^`\n]+)`/g;
  let end = 0;
  for (const match of text.matchAll(pattern)) {
    node.append(document.createTextNode(text.slice(end, match.index)));
    if (match[1]) {
      const numbers = match[1].split(',').map(Number);
      if (numbers.every(number => number >= 1 && number <= sourceCount)) {
        numbers.forEach((number, index) => {
          if (index) node.append(document.createTextNode(' '));
          node.append(citationLink(number, prefix));
        });
      } else node.append(document.createTextNode(match[0]));
    } else {
      const tag = match[2] || match[3] ? 'strong' : match[6] ? 'code' : 'em';
      const child = makeNode(tag, '');
      if (tag === 'code') child.textContent = match[6];
      else appendInline(child, match[2] || match[3] || match[4] || match[5], sourceCount, prefix);
      node.append(child);
    }
    end = match.index + match[0].length;
  }
  node.append(document.createTextNode(text.slice(end)));
}

function renderAnswer(text, sourceCount, prefix = 'source') {
  const body = makeNode('div', '', 'answer-body');
  let block = null;
  let list = null;
  let orderedList = null;
  let orderedItem = null;
  let fenced = false;
  for (const line of text.replace(/\r\n?/g, '\n').split('\n')) {
    if (/^\s*```/.test(line)) {
      fenced = !fenced;
      block = fenced ? makeNode('pre', '') : null;
      if (block) body.append(block);
      list = null;
      orderedList = null; orderedItem = null;
      continue;
    }
    if (fenced) {
      block.append(document.createTextNode(line + '\n'));
      continue;
    }
    if (!line.trim()) { block = null; list = null; continue; }
    const heading = line.match(/^\s{0,3}(#{1,6})\s+(.+?)\s*#*$/);
    const item = line.match(/^\s*(?:([-*+])|(\d+)[.)])\s+(.+)$/);
    const quote = line.match(/^\s*>\s?(.*)$/);
    if (heading) {
      const node = makeNode('h' + Math.min(heading[1].length + 2, 6), '');
      appendInline(node, heading[2], sourceCount, prefix);
      body.append(node);
      block = null; list = null;
      orderedList = null; orderedItem = null;
    } else if (item) {
      const tag = item[1] ? 'ul' : 'ol';
      if (tag === 'ol') {
        if (!orderedList) {
          orderedList = makeNode('ol', '');
          const start = Number(item[2]);
          if (start >= 1 && start <= 1000000) orderedList.start = start;
          body.append(orderedList);
        }
        list = orderedList;
      } else if (!list || list.localName !== 'ul') {
        list = makeNode('ul', '');
        // Model drafts often leave supporting bullets unindented.
        (orderedItem || body).append(list);
      }
      const node = makeNode('li', '');
      appendInline(node, item[3], sourceCount, prefix);
      list.append(node);
      if (tag === 'ol') orderedItem = node;
      block = null;
    } else {
      const tag = quote ? 'blockquote' : 'p';
      if (!block || block.localName !== tag) {
        block = makeNode(tag, '');
        body.append(block);
      } else block.append(document.createTextNode(' '));
      appendInline(block, quote ? quote[1] : line, sourceCount, prefix);
      list = null;
      orderedList = null; orderedItem = null;
    }
  }
  return body;
}

function applyPreset() {
  const presets = {
    quick: {sources: 4, results: 6, length: 'short'},
    standard: {sources: 8, results: 12, length: 'medium'},
    detailed: {sources: 16, results: 24, length: 'detailed'}
  };
  const preset = presets[element('preset').value];
  if (!preset) return;
  const profile = modelProfiles.find(row => row.model === (element('model').value || defaultModel));
  element('limit').value = preset.results;
  element('answer-sources').value = Math.min(preset.sources, profile?.sources || 8);
  element('answer-length').value = preset.length === 'detailed' && profile?.words < 600 ? 'medium' : preset.length;
  element('custom-length').hidden = true;
  updatePresetHelp();
}

function updatePresetHelp() {
  const words = {short: 100, medium: 250, detailed: 600, custom: Number(element('answer-words').value)};
  element('preset-help').textContent = `${element('limit').value} search results · up to ${element('answer-sources').value} answer sources · about ${words[element('answer-length').value]} words. Presets fit the selected model.`;
}

function highlightedText(tag, text, terms = [], passage = '') {
  const node = makeNode(tag, '', 'text');
  const escape = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const patterns = [];
  if (passage) patterns.push(escape(passage));
  if (terms.length) patterns.push('\\b(?:' + terms.map(escape).join('|') + ')\\b');
  if (!patterns.length) {
    node.textContent = text;
    return node;
  }
  let end = 0;
  for (const match of text.matchAll(new RegExp(patterns.join('|'), 'gi'))) {
    node.append(document.createTextNode(text.slice(end, match.index)));
    const mark = makeNode('mark', match[0]);
    if (passage && match[0].toLowerCase() === passage.toLowerCase()) mark.className = 'retrieved';
    node.append(mark);
    end = match.index + match[0].length;
  }
  node.append(document.createTextNode(text.slice(end)));
  return node;
}

function showSource(source, number, container) {
  const card = makeNode('section', '', 'source');
  card.id = 'source-' + number;
  card.tabIndex = -1;
  card.append(highlightedText('h3', `${number}. ${source.title}`, source.matched_terms));
  const heading = highlightedText('p', source.heading, source.matched_terms);
  heading.classList.add('muted');
  card.append(heading);
  const attribution = source.web_reference ? 'Reviewed website · ' + source.publisher + ' · retrieved ' + source.fetched_at.slice(0, 10) : source.kind === 'bible' ? 'Bible text · Recovery Version' : source.kind === 'notes' ? 'Footnote commentary · Recovery Version' : 'Ministry · ' + (source.author === 'Unverified' ? 'Authorship not verified' : source.author);
  card.append(makeNode('p', attribution, 'muted'));
  const labels = {words: 'Words', meaning: 'Meaning', reference: 'Verse reference', website: 'Reviewed website priority'};
  card.append(makeNode('p', Object.entries(source.retrieval_ranks || {}).map(([kind, rank]) => `${labels[kind]} rank ${rank}`).join(' · '), 'muted'));
  const pages = (source.pages || []).filter(page => page !== null);
  if (pages.length) {
    const label = source.url ? 'Source pages' : 'Export pages';
    card.append(makeNode('p', `${label}: ${[...new Set(pages)].join('–')}`, 'muted'));
  }
  card.append(highlightedText('p', source.text, source.matched_terms));
  const expanded = makeNode('div', '', 'context');
  const expand = makeNode('button', 'Expand context');
  const collapse = makeNode('button', 'Hide context');
  collapse.type = 'button';
  collapse.hidden = true;
  collapse.addEventListener('click', () => {
    expanded.hidden = true;
    collapse.hidden = true;
    expand.textContent = 'Show context';
    expand.disabled = false;
  });
  expand.type = 'button';
  let words = 300;
  let contextLabel = 'Expand context';
  let contextComplete = false;
  expand.addEventListener('click', async () => {
    if (expanded.hidden && expanded.childNodes.length) {
      expanded.hidden = false;
      collapse.hidden = false;
      expand.textContent = contextLabel;
      expand.disabled = contextComplete;
      return;
    }
    expand.disabled = true;
    try {
      const response = await fetch(`/api/context/${encodeURIComponent(source.id)}?words=${words}`);
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || 'Context unavailable');
      expanded.replaceChildren(makeNode('p', 'Surrounding text from this book. Expanded context is for reading; it does not change the generated answer.', 'muted'));
      expanded.hidden = false;
      collapse.hidden = false;
      for (const section of data.sections) {
        expanded.append(makeNode('h4', section.heading || source.title), highlightedText('p', section.text, source.matched_terms, source.text));
      }
      const limit = words === 8100;
      words = Math.min(words * 3, 8100);
      expand.textContent = data.more ? (limit ? 'Context limit shown' : 'Show more before and after') : 'Full available context shown';
      expand.disabled = !data.more || limit;
      contextLabel = expand.textContent;
      contextComplete = expand.disabled;
    } catch (error) {
      expanded.replaceChildren(makeNode('p', error.message, 'error'));
      expand.disabled = false;
    }
  });
  card.append(expand, collapse, expanded);
  if (source.url) {
    try {
      const url = new URL(source.url, location.origin);
      if (['http:', 'https:'].includes(url.protocol)) {
        const link = makeNode('a', 'Open source');
        link.href = url.href;
        link.target = '_blank';
        link.rel = 'noreferrer noopener';
        card.append(link);
      }
    } catch { /* Keep the passage readable if its source link is invalid. */ }
  }
  container.append(card);
}

function showSources(sources) {
  const groups = [
    {title: 'Bible & footnotes', kinds: ['bible', 'notes']},
    {title: 'Ministry', kinds: ['ministry']}
  ];
  const available = groups.filter(group => sources.some(source => group.kinds.includes(source.kind)));
  element('results').classList.toggle('source-columns', available.length === 2);
  for (const group of available) {
    const column = makeNode('section', '', 'source-column');
    column.setAttribute('aria-label', group.title);
    const count = sources.filter(source => group.kinds.includes(source.kind)).length;
    column.append(makeNode('h2', `${group.title} · ${count}`));
    sources.forEach((source, index) => {
      if (group.kinds.includes(source.kind)) showSource(source, index + 1, column);
    });
    element('results').append(column);
  }
}

async function loadBooks() {
  try {
    const response = await fetch('/api/books');
    if (!response.ok) throw Error('Collection unavailable');
    const data = await response.json();
    if (data.display_verse) {
      const verse = element('verse');
      verse.hidden = false;
      verse.append(makeNode('p', data.display_verse.text));
      const link = makeNode('a', data.display_verse.reference + ' · Recovery Version');
      link.href = '/api/reference/' + data.display_verse.section_id;
      verse.append(link, makeNode('small', ' · © Living Stream Ministry'));
    }
    element('info').textContent = `${data.books.length} title labels · ${data.chunks.toLocaleString()} searchable passages · ${data.model} · answers stay on this PC`;
    if (data.desktop) {
      const setup = makeNode('a', 'Setup / Quit app');
      setup.href = '/setup';
      element('info').append(document.createTextNode(' · '), setup);
    }
    for (const title of data.books) {
      const option = makeNode('option', title);
      option.value = title;
      element('book').append(option);
    }
    element('hybrid').disabled = !data.hybrid;
    if (data.hybrid) element('mode').value = 'hybrid';
    for (const kind of ['bible', 'notes']) {
      element('collection').querySelector(`option[value="${kind}"]`).disabled = !Object.values(data.collections).includes(kind);
    }
    element('collection').querySelector('option[value="balanced"]').disabled = !['bible', 'notes'].every(kind => Object.values(data.collections).includes(kind));
  } catch {
    element('info').textContent = 'Could not load the collection.';
  }
}

function selectModel() {
  const profile = modelProfiles.find(row => row.model === (element('model').value || defaultModel));
  if (!profile) return;
  element('answer-sources').max = profile.sources;
  element('answer-sources').value = Math.min(Number(element('answer-sources').value), profile.sources);
  element('answer-words').max = profile.words;
  element('answer-words').value = Math.min(Number(element('answer-words').value), profile.words);
  element('answer-length').querySelector('option[value="detailed"]').disabled = profile.words < 600;
  if (element('answer-length').value === 'detailed' && profile.words < 600) element('answer-length').value = 'medium';
  element('custom-length').hidden = element('answer-length').value !== 'custom';
  element('model-help').textContent = `${profile.hardware} ${profile.tradeoff} Budget: ${profile.sources} sources / ${profile.words} target words. Run setup.py to add another model.`;
}

async function loadModels() {
  try {
    const response = await fetch('/api/models');
    if (!response.ok) throw Error('Models unavailable');
    const data = await response.json();
    modelProfiles = data.models;
    defaultModel = data.default;
    element('model').options[0].textContent = 'Server default · ' + data.default;
    for (const profile of modelProfiles) {
      const option = makeNode('option', profile.label + ' · ' + profile.model + (profile.installed ? '' : ' · not downloaded'));
      option.value = profile.model;
      option.disabled = !profile.installed;
      element('model').append(option);
    }
    if (modelProfiles.some(profile => profile.model === data.default && profile.installed)) element('model').value = data.default;
    selectModel();
    applyPreset();
    if (data.notice) element('model-help').textContent = data.notice;
  } catch {
    element('model-help').textContent = 'Model choices unavailable. The server default remains selected.';
  }
}

async function submitQuery(event) {
  event.preventDefault();
  const answer = event.submitter?.dataset.answer === 'true';
  element('status').className = '';
  element('status').textContent = answer ? `Finding passages and writing a local answer · up to ${element('answer-attempts').value} attempts…` : 'Finding passages…';
  element('answer').replaceChildren();
  element('results').replaceChildren();
  const controls = [...element('search').querySelectorAll('button, select, textarea, input')];
  const disabled = controls.map(control => control.disabled);
  const payload = {question: element('question').value, book: element('book').value, author: element('author').value, collection: element('collection').value, mode: element('mode').value, limit: Number(element('limit').value), answer_sources: Number(element('answer-sources').value), answer_length: element('answer-length').value, answer_words: Number(element('answer-words').value), model: element('model').value, allow_extrapolation: element('allow-extrapolation').checked, answer};
  payload.max_answer_attempts = Number(element('answer-attempts').value);
  payload.allow_unverified_response = element('allow-unverified').checked;
  payload.expand_related_topics = element('expand-related').checked;
  payload.answer_original = element('answer-original').checked;
  payload.skip_wording_guidance = element('skip-wording-guidance').checked;
  payload.source_diversity = element('source-diversity').checked;
  payload.diversity_threshold = Number(element('diversity-threshold').value);
  payload.diversity_checks = Number(element('diversity-checks').value);
  controls.forEach(control => control.disabled = true);
  try {
    const response = await fetch('/api/query', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Please check your question.');
    if (data.query_correction) element('answer').append(makeNode('p', 'Search wording: ' + data.query_correction, 'muted'));
    if (!data.answer && data.interpreted_question) element('answer').append(makeNode('p', 'I interpreted your question as: ' + data.interpreted_question + ' ' + (data.policy_notice || ''), 'scope-warning'));
    if (data.answer) {
      const panel = makeNode('section', '', 'answer');
      if (data.scope_warning) {
        const warning = makeNode('aside', '', 'scope-warning');
        warning.setAttribute('role', 'note');
        warning.append(makeNode('strong', 'Broad question — limited passage sample'), makeNode('p', data.scope_warning));
        panel.append(warning);
      }
      const concerns = [...(data.evidence_warnings || []), ...(data.evidence_notes || []).map(note => 'Model-flagged concern (not independently verified): ' + note)];
      if (concerns.length) {
        const warning = makeNode('aside', '', 'scope-warning');
        warning.setAttribute('role', 'note');
        const list = makeNode('ul', '');
        concerns.forEach(concern => list.append(makeNode('li', concern)));
        warning.append(makeNode('strong', 'Evidence cautions'), list);
        panel.append(warning);
      }
      if (data.interpreted_question) panel.append(makeNode('p', 'I interpreted your question as: ' + data.interpreted_question, 'scope-warning'));
      panel.append(makeNode('h3', data.question_refused ? 'Cannot answer as framed' : data.policy_intro ? 'Respectful wording' : data.validation_failed ? 'Answer checks did not pass' : data.abstain ? 'More evidence needed' : data.scope_warning ? 'Findings from the retrieved passages' : data.support_level === 'background' ? 'Related source teachings — broader principles' : 'Answer'));
      if (data.support_level === 'background') panel.append(makeNode('p', 'These passages support related teachings. They do not directly establish an answer to your specific question; any application beyond them belongs in the separate extrapolation section.', 'muted'));
      panel.append(renderAnswer(data.answer, data.sources.length));
      if (data.policy_notice) panel.append(makeNode('p', data.policy_notice, 'muted'));
      if (data.citations?.length) {
        const citations = makeNode('p', data.support_level === 'background' ? 'Sources for these broader teachings: ' : 'Supporting passages: ', 'muted');
        data.citations.forEach((number, index) => {
          if (index) citations.append(document.createTextNode(', '));
          const link = citationLink(number);
          citations.append(link);
        });
        panel.append(citations);
      }
      if (data.answer_sources) panel.append(makeNode('p', `The model received ${data.answer_sources} passages · ${data.context_tokens.toLocaleString()} token context setting.`, 'muted'));
      if (data.source_diversity) {
        const selection = data.source_diversity;
        panel.append(makeNode('p', selection.available
          ? `Source diversity: ${selection.selected} sources from ${selection.candidates} candidates · ${selection.skipped} redundant passages replaced · ${selection.checked_pairs} close comparisons${selection.limit_reached ? ' · comparison limit reached; remaining uncertain passages retained' : ''}${selection.failed_checks ? ' · a comparison failed; both passages retained' : ''}.`
          : 'Source diversity needs an index with embeddings; ordinary ranking was used.', 'muted'));
      }
      if (data.model) panel.append(makeNode('p', 'Answer model: ' + data.model, 'muted'));
      if (data.recovery_notice) panel.append(makeNode('p', data.recovery_notice + (data.retrieval_retried ? ' Search was retried within your selected filters.' : ''), 'muted'));
      if (data.source_check_issues?.length) {
        const checks = makeNode('details', '');
        checks.append(makeNode('summary', 'Answer check details'));
        const list = makeNode('ul', '');
        data.source_check_issues.forEach(issue => list.append(makeNode('li', issue)));
        checks.append(list);
        panel.append(checks);
      }
      if (data.target_words) panel.append(makeNode('p', `${data.answer_words} words · requested about ${data.target_words}.`, 'muted'));
      element('answer').append(panel);
      if (data.extrapolation) {
        const reflection = makeNode('section', '', 'answer extrapolation');
        reflection.append(makeNode('h3', 'Extrapolation — not directly supported by the retrieved passages'));
        reflection.append(makeNode('p', 'Model speculation, not a statement of the ministry or direct source evidence.', 'muted'));
        if (data.extrapolation_warning) reflection.append(makeNode('p', data.extrapolation_warning, 'error'));
        reflection.append(renderAnswer(data.extrapolation, 0));
        element('answer').append(reflection);
      }
      if (data.unverified_response) {
        const draft = makeNode('section', '', 'answer');
        draft.append(makeNode('h3', 'Unverified model draft'), makeNode('p', 'This response failed source checks. It may be inaccurate. Citation markers were removed; do not attribute it to the ministry without checking the passages.', 'error'), renderAnswer(data.unverified_response, 0));
        element('answer').append(draft);
      }
    }
    showSources(data.sources);
    const scope = data.scope === 'all' ? 'All authors' : data.scope + (data.collection === 'balanced' ? ' · ministry authorship' : ' · verified authorship only');
    const collection = {all: 'Everything', balanced: 'Balanced sources', ministry: 'Ministry books', bible: 'Bible verses only', notes: 'Bible footnotes only'}[data.collection];
    const counts = data.source_counts || {};
    const balance = data.collection === 'balanced' ? ` · ${counts.ministry || 0} ministry / ${counts.bible || 0} Bible / ${counts.notes || 0} footnotes` : '';
    const related = data.related_topics?.length ? ` Related wording also searched: ${data.related_topics.join(', ')}. Search expansion does not establish a teaching or classification.` : '';
    element('status').textContent = data.question_refused ? 'The original question was not answered as framed.' : data.policy_intro ? 'The interpreted question is shown above. Use respectful, specific wording to search the ministry.' : `${data.sources.length} passages found · ${collection} · ${scope}${balance}.${related} Check the sources before relying on a generated answer.`;
  } catch (error) {
    element('status').className = 'error';
    element('status').textContent = error.message;
  } finally {
    controls.forEach((control, index) => control.disabled = disabled[index]);
  }
}

element('search').addEventListener('submit', submitQuery);
for (const id of ['preset', 'book', 'author', 'collection', 'mode', 'limit', 'answer-sources', 'answer-length', 'answer-words', 'model', 'allow-extrapolation', 'allow-unverified', 'expand-related', 'answer-original', 'skip-wording-guidance', 'source-diversity', 'diversity-threshold', 'diversity-checks']) {
  element(id).addEventListener('change', () => {
    element('answer').replaceChildren();
    element('results').replaceChildren();
    element('status').textContent = 'Scope changed. Find passages or request an answer to use this selection.';
  });
}
element('answer-length').addEventListener('change', () => {
  element('custom-length').hidden = element('answer-length').value !== 'custom';
});
loadBooks();
element('model').addEventListener('change', () => { selectModel(); applyPreset(); updatePresetHelp(); });
element('preset').addEventListener('change', applyPreset);
for (const id of ['mode', 'limit', 'answer-sources', 'answer-length', 'answer-words']) {
  element(id).addEventListener('change', () => {
    element('preset').value = 'custom';
    updatePresetHelp();
  });
}
applyPreset();
loadModels();
