const element = id => document.getElementById(id);

function makeNode(tag, text, className) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

function showSource(source, number) {
  const card = makeNode('section', '', 'source');
  card.append(makeNode('h3', `${number}. ${source.title}`));
  card.append(makeNode('p', source.heading, 'muted'));
  const pages = (source.pages || []).filter(page => page !== null);
  if (pages.length) {
    const label = source.url ? 'Source pages' : 'Export pages';
    card.append(makeNode('p', `${label}: ${[...new Set(pages)].join('–')}`, 'muted'));
  }
  card.append(makeNode('p', source.text, 'text'));
  if (source.url) {
    try {
      const url = new URL(source.url);
      if (['http:', 'https:'].includes(url.protocol)) {
        const link = makeNode('a', 'Open source');
        link.href = url.href;
        link.target = '_blank';
        link.rel = 'noreferrer noopener';
        card.append(link);
      }
    } catch { /* Keep the passage readable if its source link is invalid. */ }
  }
  element('results').append(card);
}

async function loadBooks() {
  try {
    const response = await fetch('/api/books');
    if (!response.ok) throw Error('Collection unavailable');
    const data = await response.json();
    element('info').textContent = `${data.books.length} books · ${data.chunks.toLocaleString()} searchable passages · ${data.model} · answers stay on this PC`;
    for (const title of data.books) {
      const option = makeNode('option', title);
      option.value = title;
      element('book').append(option);
    }
    element('hybrid').disabled = !data.hybrid;
    if (data.hybrid) element('mode').value = 'hybrid';
  } catch {
    element('info').textContent = 'Could not load the collection.';
  }
}

async function submitQuery(event) {
  event.preventDefault();
  const answer = event.submitter?.dataset.answer === 'true';
  element('status').className = '';
  element('status').textContent = answer ? 'Finding passages and writing a local answer…' : 'Finding passages…';
  element('answer').replaceChildren();
  element('results').replaceChildren();
  document.querySelectorAll('button').forEach(button => button.disabled = true);
  try {
    const response = await fetch('/api/query', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: element('question').value, book: element('book').value, mode: element('mode').value, answer})
    });
    const data = await response.json();
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Please check your question.');
    if (data.answer) {
      const panel = makeNode('section', '', 'answer');
      panel.append(makeNode('h3', data.abstain ? 'More evidence needed' : 'Answer'));
      panel.append(makeNode('p', data.answer, 'text'));
      if (data.citations?.length) panel.append(makeNode('p', 'Supporting passages: ' + data.citations.join(', '), 'muted'));
      element('answer').append(panel);
    }
    data.sources.forEach((source, index) => showSource(source, index + 1));
    element('status').textContent = `${data.sources.length} passages found. Check the sources before relying on a generated answer.`;
  } catch (error) {
    element('status').className = 'error';
    element('status').textContent = error.message;
  } finally {
    document.querySelectorAll('button').forEach(button => button.disabled = false);
  }
}

element('search').addEventListener('submit', submitQuery);
loadBooks();
