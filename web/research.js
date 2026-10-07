let researchJob = '';
let researchOffset = 0;
let researchReportKey = '';
let researchBusy = false;

async function researchRequest(path, body) {
  const response = await fetch('/api/research' + path, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Research request failed');
  return data;
}

function researchSettings() {
  return {run_minutes: Number(element('research-minutes').value), max_batches: Number(element('research-batches').value)};
}

function researchFinding(finding, job) {
  const card = makeNode('section', '', 'source');
  card.append(makeNode('h4', finding.title + ' / ' + finding.heading),
    makeNode('p', finding.author + ' · ' + finding.kind, 'muted'), makeNode('blockquote', finding.quote));
  const link = makeNode('a', 'Read the full original section');
  link.href = '/api/research/' + encodeURIComponent(job) + '/source/' + finding.id;
  link.target = '_blank';
  link.rel = 'noopener';
  card.append(link);
  return card;
}

function renderResearchReport(job) {
  const key = job.id + ':' + job.report_root + ':' + job.report_snapshot;
  if (researchReportKey === key) return;
  researchReportKey = key;
  const container = element('research-report');
  container.replaceChildren();
  if (!job.report) return;
  const report = job.report;
  container.append(makeNode('h3', 'Research report'), makeNode('p',
    `Report snapshot: ${job.report_sections.toLocaleString()} of ${job.total_sections.toLocaleString()} sections examined. ${job.report_sections < job.total_sections ? 'Preliminary findings; the scan is incomplete.' : 'All scoped sections processed.'} Citations link to evidence groups and their original excerpts. This is a model synthesis, not an authoritative ranking.`, 'scope-warning'),
    renderAnswer(report.answer, report.sources.length, 'research-source'));
  report.sources.forEach((source, index) => {
    const card = makeNode('section', '', 'source');
    card.id = 'research-source-' + (index + 1);
    card.tabIndex = -1;
    card.append(makeNode('h4', `${index + 1}. ${source.title} / ${source.heading}`), makeNode('p', source.text));
    const button = makeNode('button', 'Read underlying excerpts');
    button.type = 'button';
    let offset = 0;
    const excerpts = makeNode('div', '');
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        const parameter = report.children_kind === 'finding' ? 'finding_id' : 'node_id';
        const data = await researchRequest('/' + job.id + '/findings?' + parameter + '=' + report.children[index] + '&limit=20&offset=' + offset);
        data.findings.forEach(finding => excerpts.append(researchFinding(finding, job.id)));
        offset += data.findings.length;
        button.textContent = offset < data.total ? `More excerpts · ${offset} / ${data.total}` : `All ${data.total} excerpts shown`;
        button.disabled = offset >= data.total;
      } catch (error) {
        excerpts.append(makeNode('p', error.message, 'error'));
        button.disabled = false;
      }
    });
    card.append(button, excerpts);
    container.append(card);
  });
}

async function refreshResearch() {
  if (!researchJob || researchBusy) return;
  researchBusy = true;
  try {
    const job = await researchRequest('/' + researchJob);
    if (job.id !== researchJob) return;
    element('research-progress').max = job.total_sections;
    element('research-progress').value = job.sections_examined;
    const seconds = job.active_seconds;
    const pace = job.batches ? Math.round(seconds / job.batches) : null;
    element('research-status').textContent = `${job.status} · ${job.phase} · ${job.sections_examined.toLocaleString()} / ${job.total_sections.toLocaleString()} sections examined (${job.coverage_percent}%) · ${job.partial_sections} partial · ${job.batches} source batches · ${job.summary_batches} summary batches · ${job.finding_count} excerpts · ${job.failures} failed runs. Scope: ${job.collection}, ${job.author}${job.book ? ', book: ' + job.book : ''}. ${pace === null ? '' : 'Recorded average: ' + pace + ' seconds per source batch, including report work.'} ${job.last_error}`;
    const active = ['running', 'pausing'].includes(job.status);
    element('research-pause').disabled = !active || job.status === 'pausing';
    element('research-resume').disabled = active || job.status === 'complete';
    element('research-summary').disabled = active || !job.finding_count;
    element('research-more').hidden = !job.finding_count || researchOffset >= job.finding_count;
    renderResearchReport(job);
  } catch (error) {
    element('research-status').textContent = error.message;
  } finally {
    researchBusy = false;
  }
}

async function loadResearchJobs(selected = '') {
  try {
    const data = await researchRequest('');
    element('research-jobs').replaceChildren();
    if (!data.jobs.length) element('research-jobs').append(makeNode('option', 'No saved jobs'));
    data.jobs.forEach(job => {
      const option = makeNode('option', job.question.slice(0, 90) + ' · ' + job.status);
      option.value = job.id;
      element('research-jobs').append(option);
    });
    researchJob = data.jobs.some(job => job.id === selected) ? selected : data.jobs[0]?.id || '';
    element('research-jobs').value = researchJob;
    researchOffset = 0;
    researchReportKey = '';
    element('research-findings').replaceChildren();
    await refreshResearch();
  } catch (error) {
    element('research-status').textContent = error.message;
  }
}

element('research-start').addEventListener('click', async () => {
  const button = element('research-start');
  button.disabled = true;
  try {
    const question = element('question').value.trim();
    if (!question) throw Error('Enter your research question above.');
    const job = await researchRequest('', {...researchSettings(), question, model: element('model').value,
      book: element('book').value, author: element('author').value, collection: element('collection').value,
      batch_words: Number(element('research-words').value)});
    await loadResearchJobs(job.id);
  } catch (error) {
    element('research-status').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

element('research-jobs').addEventListener('change', () => loadResearchJobs(element('research-jobs').value));
for (const [button, action] of [['research-pause', 'pause'], ['research-resume', 'resume'], ['research-summary', 'report']]) {
  element(button).addEventListener('click', async () => {
    element(button).disabled = true;
    try {
      await researchRequest('/' + researchJob + '/' + action, researchSettings());
      await refreshResearch();
    } catch (error) {
      element('research-status').textContent = error.message;
    }
  });
}
element('research-more').addEventListener('click', async () => {
  try {
    const data = await researchRequest('/' + researchJob + '/findings?limit=20&offset=' + researchOffset);
    data.findings.forEach(finding => element('research-findings').append(researchFinding(finding, researchJob)));
    researchOffset += data.findings.length;
    element('research-more').textContent = `More collected excerpts · ${researchOffset} / ${data.total}`;
    element('research-more').hidden = researchOffset >= data.total;
  } catch (error) {
    element('research-status').textContent = error.message;
  }
});
loadResearchJobs();
setInterval(() => {
  if (element('deep-research').open) refreshResearch();
}, 3000);
